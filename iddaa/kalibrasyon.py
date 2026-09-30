"""iddaa'nın kendi geçmiş oranlarıyla kalibrasyon ve geriye dönük testler.

Soru: "iddaa bu seçeneğe (kâr payı ayıklanınca) %q şans veriyordu; gerçekte ne sıklıkla tuttu?"

Veri: Mackolik arşivi (skorlar, lig; `arsiv.py`) + maç sayfalarındaki oranlar (`arsiv_oran.py`). Oranlar
standart iddaa oranıdır; iddaa.com'daki Kral Oran bunların ~1.04 katı.

Model (market ve seçenek başına):
  q = seçeneğin marketteki normalleştirilmiş olasılığı (1/oran, market toplamına bölünür)
  logit(p) = a + b·x + c·x²  (x = logit q)   + lig düzeltmesi u (az veride sıfıra çekilir)
  Aynı marketin seçenekleri sonra toplamı 1 olacak şekilde normalleştirilir.
Beklenen dönüş = oran × p. 1'in üstü: uzun vadede kazandırır.

Geriye dönük test: model son 12 aydan önceki veriyle kurulur, son 12 ayda "beklenen > eşik" olan her seçime
1 TL oynanmış gibi sayılır (sadece o dönemin oranlarıyla, geleceği görmeden).
"""
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timezone

from . import arsiv, arsiv_oran, config, depo
from .bulten import iyms_sonucu, sonuc_isareti
from .sonuc import lig_anahtari

log = logging.getLogger("kalibrasyon")

KRAL_KATSAYI = 1.04          # iddaa.com / bayi Kral Oran ≈ standart oran × 1.04
Q_DILIM = 0.005              # kalibrasyon dilimi (olasılık)
LIG_Q_DILIM = 0.02           # lig düzeltmesi için kaba dilim
EGITIM_AY = 36               # canlı model son kaç ayla kurulur
TEST_AY = 12                 # geriye dönük test dönemi

# Görünen ad -> iddaa market anahtarı (toplanan veride) ve arşiv sütunları (seçenek adı iddaa'daki gibi)
MARKETLER: dict[str, dict] = {
    "MS": {"anahtar": "1_1", "secenekler": {"1": "ms_1", "0": "ms_0", "2": "ms_2"}},
    "İY/MS": {"anahtar": "2_90", "secenekler": {
        "1/1": "iyms_11", "1/0": "iyms_10", "1/2": "iyms_12", "0/1": "iyms_01", "0/0": "iyms_00",
        "0/2": "iyms_02", "2/1": "iyms_21", "2/0": "iyms_20", "2/2": "iyms_22"}},
    "Toplam gol": {"anahtar": "2_4", "secenekler": {"0-1 gol": "tg_01", "2-3 gol": "tg_23", "4-5 gol": "tg_45",
                                                   "6+ gol": "tg_6"}},
    "KG": {"anahtar": "2_89", "secenekler": {"Var": "kg_var", "Yok": "kg_yok"}},
    "İY": {"anahtar": "2_88", "secenekler": {"1": "iy_1", "0": "iy_0", "2": "iy_2"}},
    "1.5 A/Ü": {"anahtar": "2_101|1.5", "secenekler": {"Alt": "au15_alt", "Üst": "au15_ust"}},
    "2.5 A/Ü": {"anahtar": "2_101|2.5", "secenekler": {"Alt": "au25_alt", "Üst": "au25_ust"}},
    "3.5 A/Ü": {"anahtar": "2_101|3.5", "secenekler": {"Alt": "au35_alt", "Üst": "au35_ust"}},
}
ANAHTARDAN_MARKET = {m["anahtar"]: ad for ad, m in MARKETLER.items()}
# Arşiv satırında sayfa oranı yoksa kullanılacak yedek sütunlar (günlük veriden)
YEDEK_SUTUNLAR = {"MS": {"1": "o1", "0": "o0", "2": "o2"}, "2.5 A/Ü": {"Alt": "alt25", "Üst": "ust25"}}


# --- sonuçlar ---

def toplam_gol_araligi(toplam: int) -> str:
    return "0-1 gol" if toplam <= 1 else "2-3 gol" if toplam <= 3 else "4-5 gol" if toplam <= 5 else "6+ gol"


def kazanan(market: str, iy_ev: int, iy_dep: int, ms_ev: int, ms_dep: int) -> str:
    toplam = ms_ev + ms_dep
    if market == "MS":
        return sonuc_isareti(ms_ev, ms_dep)
    if market == "İY/MS":
        return iyms_sonucu(iy_ev, iy_dep, ms_ev, ms_dep)
    if market == "Toplam gol":
        return toplam_gol_araligi(toplam)
    if market == "KG":
        return "Var" if ms_ev and ms_dep else "Yok"
    if market == "İY":
        return sonuc_isareti(iy_ev, iy_dep)
    if market.endswith("A/Ü"):
        return "Üst" if toplam > float(market.split()[0]) else "Alt"
    raise ValueError(market)


# --- yardımcılar ---

def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x)) if x > -35 else 0.0


def normallestir(oranlar: dict[str, float]) -> dict[str, float]:
    ters = {s: 1 / o for s, o in oranlar.items()}
    toplam = sum(ters.values())
    return {s: t / toplam for s, t in ters.items()}


def q_dilimi(q: float) -> int:
    return min(int(q / Q_DILIM), int(1 / Q_DILIM) - 1)


def oran_etiketi(oran: float) -> str:
    return f"{round(oran + 1e-9, 2):.2f}"


def ay_ekle(ay: str, fark: int) -> str:
    yil, a = int(ay[:4]), int(ay[5:7])
    toplam = yil * 12 + (a - 1) + fark
    return f"{toplam // 12}-{toplam % 12 + 1:02d}"


# --- veri akışı ---

def mac_akisi(baslangic: str = "", bitis: str = "9999-12"):
    """Ay ay arşiv maçları: (tarih, lig, skorlar, {market: {seçenek: oran}}). Bellekte tek ay tutulur."""
    for yol in sorted(arsiv.dizin().glob("*.csv.gz")):
        ay = yol.name[:7]
        if not (baslangic[:7] <= ay <= bitis[:7]):
            continue
        sayfa = arsiv_oran.oku(ay, ay)
        for m in arsiv.oku(ay, ay):
            oran_kaydi = sayfa.get(m["mk_id"]) or {}
            marketler = {}
            for market, tanim in MARKETLER.items():
                oranlar = {s: oran_kaydi.get(sutun) for s, sutun in tanim["secenekler"].items()}
                if not all(oranlar.values()) and market in YEDEK_SUTUNLAR:
                    oranlar = {s: m.get(sutun) for s, sutun in YEDEK_SUTUNLAR[market].items()}
                if all(o and o > 1.0 for o in oranlar.values()):
                    marketler[market] = oranlar
            if marketler:
                lig = lig_anahtari(m["ulke"], m.get("lig_kodu") or m["lig"])
                yield m["tarih"], lig, (m["iy_ev"], m["iy_dep"], m["ms_ev"], m["ms_dep"]), marketler


# --- model ---

ONCUL = [0.0, 1.0, 0.0]          # öncül: iddaa'nın olasılığı doğru (p = q)
CEZA = [1.0, 10.0, 200.0]         # öncüle çekme gücü; eğrilik (c) en çok: az veride eğri bükülmesin


def _irls(dilimler: list[tuple[float, float, float]], derece: int = 2, tur: int = 25,
          ceza: list[float] = CEZA) -> list[float]:
    """Gruplanmış veride lojistik regresyon: [(x, n, tutan)] -> katsayılar (a, b, c).
    Katsayılar öncüle (p = q) doğru cezalandırılır (ridge); çok veride etkisi yok, az veride eğriyi düzleştirir."""
    k = derece + 1
    beta = ONCUL[:k]
    for _ in range(tur):
        H = [[(ceza[i] if i < len(ceza) else 0.0) * (i == j) + 1e-9 * (i == j) for j in range(k)] for i in range(k)]
        g = [-(ceza[i] if i < len(ceza) else 0.0) * (beta[i] - ONCUL[i]) for i in range(k)]
        for x, n, y in dilimler:
            ozellik = [x ** i for i in range(k)]
            p = sigmoid(sum(b * f for b, f in zip(beta, ozellik)))
            w = n * p * (1 - p)
            for i in range(k):
                g[i] += (y - n * p) * ozellik[i]
                for j in range(k):
                    H[i][j] += w * ozellik[i] * ozellik[j]
        adim = _coz(H, g)
        beta = [b + a for b, a in zip(beta, adim)]
        if max(abs(a) for a in adim) < 1e-7:
            break
    return beta


def _coz(A: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[pivot] = M[pivot], M[i]
        if abs(M[i][i]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, n + 1):
                    M[r][c] -= f * M[i][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def egrisel_olasilik(katsayi: list[float], q: float, u: float = 0.0, aralik: list[float] | None = None) -> float:
    """Kalibrasyon eğrisi. Verinin görüldüğü aralığın (logit q) dışında eğri uzatılmaz: kenardaki
    düzeltme (logit p − logit q) sabit tutulur, yani iddaa'nın olasılığıyla aynı eğimle devam edilir."""
    x = logit(q)
    xk = min(max(x, aralik[0]), aralik[1]) if aralik else x
    return sigmoid(sum(b * xk ** i for i, b in enumerate(katsayi)) + (x - xk) + u)


def _agirlikli_yuzdelik(degerler: list[tuple[float, float]], oran: float) -> float:
    """[(değer, ağırlık)] içinde ağırlıklı yüzdelik."""
    degerler = sorted(degerler)
    toplam = sum(w for _, w in degerler)
    birikim = 0.0
    for d, w in degerler:
        birikim += w
        if birikim >= oran * toplam:
            return d
    return degerler[-1][0]


class Sayaclar:
    """Kalibrasyon ve oran tabloları için toplu sayımlar."""

    def __init__(self):
        self.dilim = defaultdict(lambda: [0, 0, 0.0])        # (market, seçenek, q_dilimi) -> [n, tutan, Σq]
        self.lig_dilim = defaultdict(lambda: [0, 0, 0.0])     # (market, seçenek, lig, kaba dilim) -> [n, tutan, Σq]
        self.oran = defaultdict(lambda: [0, 0])               # (market, seçenek, oran etiketi) -> [n, tutan]
        self.mac = 0

    def ekle(self, lig: str, skor: tuple, marketler: dict) -> None:
        self.mac += 1
        for market, oranlar in marketler.items():
            gercek = kazanan(market, *skor)
            qs = normallestir(oranlar)
            for secenek, oran in oranlar.items():
                tuttu = int(secenek == gercek)
                d = q_dilimi(qs[secenek])
                s = self.dilim[(market, secenek, d)]
                s[0] += 1
                s[1] += tuttu
                s[2] += qs[secenek]
                s = self.lig_dilim[(market, secenek, lig, int(qs[secenek] / LIG_Q_DILIM))]
                s[0] += 1
                s[1] += tuttu
                s[2] += qs[secenek]
                s = self.oran[(market, secenek, oran_etiketi(oran))]
                s[0] += 1
                s[1] += tuttu


MIN_MODEL_MAC = 2000   # bir market modele en az bu kadar maçla girer; azsa kuponlar eski tablolarla seçilir


def model_kur(sayac: Sayaclar, min_lig_ornek: int = 200, min_mac: int = MIN_MODEL_MAC) -> dict:
    """Global eğriler + lig düzeltmeleri (ampirik Bayes ile sıfıra çekilmiş). Az maçlı marketler atlanır."""
    model: dict = {"marketler": {}}
    gruplar = defaultdict(list)
    for (market, secenek, d), (n, y, sq) in sayac.dilim.items():
        gruplar[(market, secenek)].append((logit(sq / n), n, y))
    for (market, secenek), dilimler in gruplar.items():
        if sum(n for _, n, _ in dilimler) < min_mac:
            continue
        katsayi = _irls(dilimler) if sum(n for _, n, _ in dilimler) >= 300 else [0.0, 1.0, 0.0]
        aralik = [round(_agirlikli_yuzdelik([(x, n) for x, n, _ in dilimler], 0.01), 4),
                  round(_agirlikli_yuzdelik([(x, n) for x, n, _ in dilimler], 0.99), 4)]
        model["marketler"].setdefault(market, {})[secenek] = {"katsayi": [round(k, 6) for k in katsayi],
                                                              "aralik": aralik, "lig": {}}
    # Lig düzeltmesi: u_ham = (O - E) / V, örnekleme varyansı 1/V; τ² momentlerden
    lig_toplam = defaultdict(lambda: [0.0, 0.0, 0.0, 0])   # (market, seçenek, lig) -> [O, E, V, n]
    for (market, secenek, lig, _), (n, y, sq) in sayac.lig_dilim.items():
        if secenek not in model["marketler"].get(market, {}):
            continue
        egri = model["marketler"][market][secenek]
        p = egrisel_olasilik(egri["katsayi"], sq / n, aralik=egri.get("aralik"))
        t = lig_toplam[(market, secenek, lig)]
        t[0] += y
        t[1] += n * p
        t[2] += n * p * (1 - p)
        t[3] += n
    ham = defaultdict(list)
    for (market, secenek, lig), (O, E, V, n) in lig_toplam.items():
        if n >= min_lig_ornek and V > 0:
            ham[(market, secenek)].append((lig, (O - E) / V, V, O, E))
    for (market, secenek), liste in ham.items():
        agirlik = sum(V for _, _, V, _, _ in liste)
        tau2 = max(0.0, sum(V * (u * u - 1 / V) for _, u, V, _, _ in liste) / agirlik) if agirlik else 0.0
        if tau2 <= 0:
            continue
        ligler = model["marketler"][market][secenek]["lig"]
        for lig, u, V, O, E in liste:
            ligler[lig] = round((O - E) / (V + 1 / tau2), 4)
        model["marketler"][market][secenek]["tau"] = round(math.sqrt(tau2), 4)
    return model


def olasiliklar(model: dict, market: str, oranlar: dict[str, float], lig: str | None = None) -> dict[str, float]:
    """Bir marketin bütün seçenekleri için model olasılıkları (toplamı 1)."""
    tanim = model.get("marketler", {}).get(market)
    if not tanim or not oranlar or not all(o and o > 1.0 for o in oranlar.values()):
        return {}
    qs = normallestir(oranlar)
    ham = {}
    for secenek, q in qs.items():
        s = tanim.get(secenek)
        if not s:
            return {}
        ham[secenek] = egrisel_olasilik(s["katsayi"], q, s["lig"].get(lig, 0.0) if lig else 0.0, s.get("aralik"))
    toplam = sum(ham.values())
    return {s: p / toplam for s, p in ham.items()} if toplam else {}


def mac_secenekleri(model: dict, marketler: dict[str, dict], lig: str | None = None) -> list[dict]:
    """Bir maçın toplanan son oranlarından ({market anahtarı: {"oranlar": {...}, "mbs": ..}}) model olasılıkları.
    Oranlar iddaa.com'daki (Kral) oranlardır; beklenen = oran × olasılık."""
    secimler = []
    for ad, tanim in MARKETLER.items():
        kayit = marketler.get(tanim["anahtar"])
        if not kayit:
            continue
        oranlar = {s: kayit["oranlar"].get(s) for s in tanim["secenekler"]}
        p = olasiliklar(model, ad, oranlar, lig)
        if not p:
            continue
        lig_etkisi = bool(lig) and any(lig in (model["marketler"][ad].get(s) or {}).get("lig", {}) for s in p)
        for secim, oran in oranlar.items():
            secimler.append({"market": ad, "secim": secim, "oran": oran, "olasilik": round(p[secim], 4),
                             "beklenen": round(oran * p[secim], 3), "mbs": str(kayit.get("mbs") or ""),
                             "lig_etkisi": lig_etkisi})
    return secimler


# --- geriye dönük test ---

ESIKLER = [0.0, 0.9, 1.0, 1.05, 1.1]
HAYAL_ARALIGI = (20.0, 30.0)   # İY/MS hayal kuponu oran aralığı (Kral oran)


def _test_sayaci():
    return defaultdict(lambda: {"bahis": 0, "tutan": 0, "donus": 0.0})


def _say(sonuc, anahtar, oran: float, tuttu: bool) -> None:
    s = sonuc[anahtar]
    s["bahis"] += 1
    if tuttu:
        s["tutan"] += 1
        s["donus"] += oran


def geriye_test(model: dict, baslangic: str, bitis: str, sadece: set[str] | None = None) -> dict:
    """Test döneminde (model bu dönemi görmeden kuruldu) 1 TL'lik bahisler; oranlar o dönemin oranları.

    Stratejiler (market başına):
      hepsi     : beklenen >= eşik olan her seçim
      mac_basi  : her maçın beklenen dönüşü en yüksek seçimi, beklenen >= eşik ise
      hayal_*   : İY/MS, Kral oranı 20-30 arası; 'model' en yüksek beklenen, 'oran' en yüksek oran (eski kural)
    Getiri: 1 TL'ye dönen para (standart oran ve Kral oran ile). 1'in altı zarar demek.
    """
    sonuc = _test_sayaci()
    for _, lig, skor, marketler in mac_akisi(baslangic, bitis):
        for market, oranlar in marketler.items():
            if sadece is not None and market not in sadece:
                continue
            p = olasiliklar(model, market, oranlar, lig)
            if not p:
                continue
            gercek = kazanan(market, *skor)
            beklenen = {s: o * KRAL_KATSAYI * p[s] for s, o in oranlar.items()}
            for secenek, oran in oranlar.items():
                for esik in ESIKLER:
                    if beklenen[secenek] >= esik:
                        _say(sonuc, ("hepsi", market, esik), oran, secenek == gercek)
            en_iyi = max(beklenen, key=beklenen.get)
            for esik in ESIKLER:
                if beklenen[en_iyi] >= esik:
                    _say(sonuc, ("mac_basi", market, esik), oranlar[en_iyi], en_iyi == gercek)
            if market == "İY/MS":
                aralikta = [s for s, o in oranlar.items()
                            if HAYAL_ARALIGI[0] <= o * KRAL_KATSAYI <= HAYAL_ARALIGI[1]]
                if aralikta:
                    s_model = max(aralikta, key=beklenen.get)
                    s_oran = max(aralikta, key=oranlar.get)
                    _say(sonuc, ("hayal_model", market, 0.0), oranlar[s_model], s_model == gercek)
                    _say(sonuc, ("hayal_oran", market, 0.0), oranlar[s_oran], s_oran == gercek)
    cikti = []
    for (strateji, market, esik), s in sorted(sonuc.items()):
        n = s["bahis"]
        cikti.append({"strateji": strateji, "market": market, "esik": esik, "bahis": n, "tutan": s["tutan"],
                      "getiri": round(s["donus"] / n, 4) if n else 0,
                      "getiri_kral": round(s["donus"] * KRAL_KATSAYI / n, 4) if n else 0,
                      "hata": hata_payi(n, s["tutan"], s["donus"] * KRAL_KATSAYI)})
    return {"baslangic": baslangic, "bitis": bitis, "satirlar": cikti}


def hata_payi(bahis: int, tutan: int, donus: float) -> float:
    """Getirinin %95 hata payı (yaklaşık): tutan bahislerin ortalama oranı × √(p(1-p)/n) × 1.96.
    Az tutan bahiste (yüksek oran) getiri şansa çok bağlıdır; 1'in üstü bile tesadüf olabilir."""
    if not bahis or not tutan:
        return 0.0
    p = tutan / bahis
    return round(1.96 * (donus / tutan) * math.sqrt(p * (1 - p) / bahis), 4)


# İY/MS ve MS için oran bantları (Kral oran): "bu aralıkta oynasaydın ne olurdu"
BANTLAR = {
    "İY/MS": [(1.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, 30.0), (30.0, 1000.0)],
    "MS": [(1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 1000.0)],
    "Toplam gol": [(1.0, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 1000.0)],
}


def senaryolar(sayac: "Sayaclar") -> dict:
    """Bütün geçmiş: market ve seçenek başına ve oran bandına göre her seçime 1 TL oynansaydı (Kral oranla)."""
    toplam = defaultdict(lambda: [0, 0, 0.0])   # (market, seçenek|'hepsi', bant) -> [n, tutan, dönüş]
    for (market, secenek, etiket), (n, y) in sayac.oran.items():
        kral = float(etiket) * KRAL_KATSAYI
        bant = next((f"{a:g}–{b:g}" if b < 1000 else f"{a:g}+" for a, b in BANTLAR.get(market, [])
                     if a <= kral < b or (b == 30.0 and kral == 30.0)), "")
        anahtarlar = {(market, secenek, ""), (market, "hepsi", "")}
        if bant:
            anahtarlar |= {(market, "hepsi", bant), (market, secenek, bant)}
        for anahtar in anahtarlar:
            t = toplam[anahtar]
            t[0] += n
            t[1] += y
            t[2] += y * kral
    satirlar = []
    for (market, secenek, bant), (n, y, donus) in toplam.items():
        if n:
            satirlar.append({"market": market, "secenek": secenek, "bant": bant, "bahis": n, "tutan": y,
                             "tutma": round(y / n, 4), "getiri_kral": round(donus / n, 4),
                             "hata": hata_payi(n, y, donus)})
    sira = {m: i for i, m in enumerate(MARKETLER)}
    satirlar.sort(key=lambda r: (sira.get(r["market"], 99), r["secenek"] != "hepsi", r["secenek"],
                                 float(r["bant"].split("–")[0].rstrip("+")) if r["bant"] else -1))
    return {"satirlar": satirlar, "mac": sayac.mac}


def hayal_kuponu(baslangic: str = "", bitis: str = "9999-12", tutar: float = 20.0) -> dict:
    """Her gün 3 maçlık İY/MS kuponu (Kral oranı 20–30, eski kural: her maçtan aralıktaki en yüksek oranlı seçim,
    günün en yüksek oranlı 3 seçimi) oynansaydı. Ayrıca aynı seçimler tek tek 1 TL oynansaydı."""
    gunluk: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for tarih, _, skor, marketler in mac_akisi(baslangic, bitis):
        oranlar = marketler.get("İY/MS")
        if not oranlar:
            continue
        gercek = kazanan("İY/MS", *skor)
        aralikta = [(o * KRAL_KATSAYI, s == gercek) for s, o in oranlar.items()
                    if HAYAL_ARALIGI[0] <= o * KRAL_KATSAYI <= HAYAL_ARALIGI[1]]
        if aralikta:
            gunluk[tarih].append(max(aralikta))
    sonuc = {"gun": 0, "harcanan": 0.0, "kazanan": 0, "donen": 0.0, "iki_tutan": 0,
             "tek_bahis": 0, "tek_tutan": 0, "tek_donus": 0.0, "kazanan_gunler": []}
    for tarih, liste in sorted(gunluk.items()):
        if len(liste) < 3:
            continue
        secilen = sorted(liste, reverse=True)[:3]
        tutan = sum(t for _, t in secilen)
        sonuc["gun"] += 1
        sonuc["harcanan"] += tutar
        sonuc["iki_tutan"] += tutan == 2
        if tutan == 3:
            kazanc = tutar * math.prod(o for o, _ in secilen)
            sonuc["kazanan"] += 1
            sonuc["donen"] += kazanc
            sonuc["kazanan_gunler"].append([tarih, round(kazanc, 2)])
        for o, t in secilen:
            sonuc["tek_bahis"] += 1
            sonuc["tek_tutan"] += t
            sonuc["tek_donus"] += o if t else 0.0
    sonuc["ilk"] = min(gunluk, default="")
    sonuc["son"] = max(gunluk, default="")
    sonuc["tek_getiri"] = round(sonuc["tek_donus"] / sonuc["tek_bahis"], 4) if sonuc["tek_bahis"] else 0
    sonuc["tek_hata"] = hata_payi(sonuc["tek_bahis"], sonuc["tek_tutan"], sonuc["tek_donus"])
    return sonuc


def oran_tablosu(sayac: Sayaclar, min_ornek: int = 20) -> dict:
    """{market: {seçenek: [[Kral oran, n, tutan], ...]}} - 'bu oran geçmişte ne sıklıkla tuttu'.
    Geçmiş oranlar standart orandır; iddaa.com'da görülen Kral orana (×1.04) çevrilip gruplanır."""
    birlesik = defaultdict(lambda: [0, 0])
    for (market, secenek, etiket), (n, y) in sayac.oran.items():
        t = birlesik[(market, secenek, oran_etiketi(float(etiket) * KRAL_KATSAYI))]
        t[0] += n
        t[1] += y
    tablo: dict = defaultdict(lambda: defaultdict(list))
    for (market, secenek, etiket), (n, y) in sorted(birlesik.items(), key=lambda kv: float(kv[0][2])):
        if n >= min_ornek:
            tablo[market][secenek].append([float(etiket), n, y])
    return {m: dict(v) for m, v in tablo.items()}


def kalibrasyon_tablosu(sayac: Sayaclar, model: dict) -> list[dict]:
    """Rapor için: market/seçenek başına iddaa olasılığı dilimleri, gerçek sıklık ve model."""
    satirlar = []
    for (market, secenek, d), (n, y, sq) in sorted(sayac.dilim.items()):
        if n < 200 or secenek not in model["marketler"].get(market, {}):
            continue
        egri = model["marketler"][market][secenek]
        satirlar.append({"market": market, "secenek": secenek, "q": round(sq / n, 4), "ornek": n,
                         "siklik": round(y / n, 4),
                         "model": round(egrisel_olasilik(egri["katsayi"], sq / n, aralik=egri.get("aralik")), 4)})
    return satirlar


def model_yolu():
    return depo.kok() / "analiz" / "kalibrasyon.json"


def model_oku() -> dict:
    return depo.json_oku(model_yolu()) or {}


MIN_EGITIM_MAC = 3000   # bir market için standart eğitim döneminde bundan az maç varsa eldeki veri ikiye bölünür


def bolme_plani(sayim: dict[str, dict[str, int]], bu_ay: str) -> dict[str, tuple[str, str, str, str]]:
    """Market başına (eğitim başı, eğitim sonu, test başı, test sonu). Standart: son 12 ay test, öncesindeki
    36 ay eğitim. O markette eğitim dönemi verisi azsa (ör. maç sayfası oranları henüz inmemişse) marketin veri
    olan ayları ortadan ikiye bölünür: ilk yarı eğitim, ikinci yarı test."""
    test_bas = ay_ekle(bu_ay, -(TEST_AY - 1))
    egitim_bas, egitim_bit = ay_ekle(test_bas, -EGITIM_AY), ay_ekle(test_bas, -1)
    plan = {}
    for market, aylar in sayim.items():
        if sum(n for a, n in aylar.items() if egitim_bas <= a <= egitim_bit) >= MIN_EGITIM_MAC:
            plan[market] = (egitim_bas, egitim_bit, test_bas, bu_ay)
            continue
        dolu = sorted(a for a, n in aylar.items() if n)
        if len(dolu) >= 4 and sum(aylar.values()) >= 2 * MIN_MODEL_MAC:
            orta = dolu[len(dolu) // 2]
            plan[market] = (dolu[0], ay_ekle(orta, -1), orta, dolu[-1])
    return plan


def calistir(bugun: date | None = None) -> dict:
    bugun = bugun or datetime.now(timezone.utc).astimezone(config.TR).date()
    bu_ay = bugun.strftime("%Y-%m")
    canli_bas = ay_ekle(bu_ay, -EGITIM_AY)

    # 1) Canlı model ve tablolar: son EGITIM_AY ay (tablolar tüm veri); market/ay sayımı
    canli, tum = Sayaclar(), Sayaclar()
    sayim: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    tum_ilk, tum_son = "", ""
    for tarih, lig, skor, marketler in mac_akisi():
        tum.ekle(lig, skor, marketler)
        tum_ilk, tum_son = tum_ilk or tarih, tarih
        for market in marketler:
            sayim[market][tarih[:7]] += 1
        if tarih[:7] >= canli_bas:
            canli.ekle(lig, skor, marketler)
    model = model_kur(canli)
    model.update({"olusturma": bugun.isoformat(), "egitim_baslangic": canli_bas, "mac": canli.mac,
                  "kral_katsayi": KRAL_KATSAYI})

    # 2) Geriye dönük test: her plan için model sadece eğitim dönemiyle kurulur, test dönemini hiç görmez
    planlar = bolme_plani(sayim, bu_ay)
    gruplar: dict[tuple, set[str]] = defaultdict(set)
    for market, plan in planlar.items():
        gruplar[plan].add(market)
    test_satirlari, plan_ozeti = [], {}
    for (e_bas, e_bit, t_bas, t_bit), marketler_ in sorted(gruplar.items()):
        egitim = Sayaclar()
        for _, lig, skor, marketler in mac_akisi(e_bas, e_bit):
            secili = {m: o for m, o in marketler.items() if m in marketler_}
            if secili:
                egitim.ekle(lig, skor, secili)
        sonuc = geriye_test(model_kur(egitim), t_bas, t_bit, marketler_)
        for satir in sonuc["satirlar"]:
            satir.update({"egitim": f"{e_bas} → {e_bit}", "test": f"{t_bas} → {t_bit}"})
        test_satirlari += sonuc["satirlar"]
        for market in marketler_:
            plan_ozeti[market] = {"egitim": f"{e_bas} → {e_bit}", "test": f"{t_bas} → {t_bit}",
                                  "egitim_mac": sum(n for a, n in sayim[market].items() if e_bas <= a <= e_bit)}
    standart = (ay_ekle(ay_ekle(bu_ay, -(TEST_AY - 1)), -EGITIM_AY), ay_ekle(bu_ay, -(TEST_AY - 1)))

    depo.json_yaz(model_yolu(), model)
    depo.json_yaz(depo.kok() / "analiz" / "iddaa_oran_tablosu.json", oran_tablosu(tum))
    depo.json_yaz(depo.kok() / "analiz" / "iddaa_senaryolar.json",
                  {**senaryolar(tum), "ilk": tum_ilk, "son": tum_son, "olusturma": bugun.isoformat(),
                   "hayal_kuponu": hayal_kuponu()})
    depo.json_yaz(depo.kok() / "analiz" / "iddaa_kalibrasyon_tablosu.json", kalibrasyon_tablosu(canli, model))
    depo.json_yaz(depo.kok() / "analiz" / "geriye_test.json",
                  {"satirlar": test_satirlari, "planlar": plan_ozeti, "egitim_baslangic": standart[0],
                   "baslangic": standart[1], "bitis": bu_ay})
    ozet = {"tum_mac": tum.mac, "canli_mac": canli.mac, "planlar": plan_ozeti,
            "test": [s for s in test_satirlari if s["esik"] in (0.0, 1.0) and s["strateji"] != "hepsi"]}
    log.info("özet: %s", ozet)
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    calistir()


if __name__ == "__main__":
    main()
