"""Oran analizleri.

1. MS (1-0-2) oranları tek tek: her oranda (1.55 gibi) seçim kaç kez tuttu, oranın vaat ettiği olasılık neydi,
   1 TL'ye ne kadar döndü (getiri). Getiri > 1 ise o oran uzun vadede kazandırıyor demektir.
2. Koşullu İY/MS sıklıkları: ev sahibinin kazanma olasılığına (oranlardan, kâr payı ayıklanmış) göre
   9 İY/MS sonucunun gerçek sıklığı. Bu, iddaa'nın İY/MS oranlarının adil olup olmadığını ölçmeye yarar.
3. Değer adayları: bugünkü iddaa oranı × geçmişteki gerçek sıklık = beklenen dönüş.
"""
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import config, depo, gecmis
from .bulten import iso_oku, iyms_sonucu, sonuc_isareti

log = logging.getLogger("analiz")

MS = "1_1"
IYMS_SECENEKLERI = ["1/1", "1/0", "1/2", "0/1", "0/0", "0/2", "2/1", "2/0", "2/2"]
MS_SECENEKLERI = ["1", "0", "2"]
DILIM_GENISLIGI = 0.05
MIN_DILIM_ORNEGI = 500


def oran_etiketi(oran: float) -> str:
    """Oranlar tek tek, iki basamakla gruplanır: 1.55 -> "1.55"."""
    return f"{round(oran + 1e-9, 2):.2f}"


def normal_olasiliklar(o1: float, o0: float, o2: float) -> tuple[float, float, float]:
    """Oranlardan kâr payı ayıklanmış olasılıklar."""
    ters = (1 / o1, 1 / o0, 1 / o2)
    toplam = sum(ters)
    return tuple(t / toplam for t in ters)


def dilim(olasilik: float) -> str:
    alt = min(int(olasilik / DILIM_GENISLIGI), int(1 / DILIM_GENISLIGI) - 1) * DILIM_GENISLIGI
    return f"%{alt * 100:.0f}–{(alt + DILIM_GENISLIGI) * 100:.0f}"


def _bos_sayac():
    return {"ornek": 0, "tuttu": 0, "vaat": 0.0, "donus": 0.0, "donus_maks": 0.0}


def _satira_cevir(anahtar: dict, s: dict) -> dict:
    n = s["ornek"]
    return {**anahtar, "ornek": n, "tuttu": s["tuttu"],
            "tutma": round(s["tuttu"] / n, 4) if n else 0,
            "vaat": round(s["vaat"] / n, 4) if n else 0,
            "getiri": round(s["donus"] / n, 4) if n else 0,
            "getiri_maks": round(s["donus_maks"] / n, 4) if n else 0}


def _sirala(satirlar: list[dict]) -> list[dict]:
    """Sıralar ve getirinin %95 hata payını ekler: tek bir oranın örneği azsa sonuç şansa bağlıdır."""
    for r in satirlar:
        n, p = r["ornek"], r["tutma"]
        r["hata"] = round(1.96 * float(r["oran"]) * math.sqrt(p * (1 - p) / n), 4) if n else 0
    sira = {"hepsi": 0, "1": 1, "0": 2, "2": 3}
    return sorted(satirlar, key=lambda r: (sira[r["secim"]], float(r["oran"])))


# --- 1. MS oranları tek tek (geçmiş) ---

def ms_oran_tablosu(maclar: list[dict]) -> list[dict]:
    sayac = defaultdict(_bos_sayac)
    for m in maclar:
        oranlar = [m.get(f"ort_{s}") for s in MS_SECENEKLERI]
        if any(o is None for o in oranlar):
            continue
        gercek = sonuc_isareti(m["ms_ev"], m["ms_dep"])
        for secim, oran in zip(MS_SECENEKLERI, oranlar):
            maks = m.get(f"maks_{secim}") or oran
            for anahtar in ((secim, oran_etiketi(oran)), ("hepsi", oran_etiketi(oran))):
                s = sayac[anahtar]
                s["ornek"] += 1
                s["vaat"] += 1 / oran
                if secim == gercek:
                    s["tuttu"] += 1
                    s["donus"] += oran
                    s["donus_maks"] += maks
    return _sirala([_satira_cevir({"secim": k[0], "oran": k[1]}, s) for k, s in sayac.items()])


# --- 2. Koşullu İY/MS sıklıkları (geçmiş) ---

def iyms_kosullu_tablo(maclar: list[dict]) -> dict[str, dict]:
    tablo: dict[str, dict] = defaultdict(lambda: {"ornek": 0, **{s: 0 for s in IYMS_SECENEKLERI + MS_SECENEKLERI}})
    for m in maclar:
        oranlar = [m.get(f"ort_{s}") for s in MS_SECENEKLERI]
        if any(o is None for o in oranlar):
            continue
        p1 = normal_olasiliklar(*oranlar)[0]
        t = tablo[dilim(p1)]
        t["ornek"] += 1
        t[iyms_sonucu(m["iy_ev"], m["iy_dep"], m["ms_ev"], m["ms_dep"])] += 1
        t[sonuc_isareti(m["ms_ev"], m["ms_dep"])] += 1
    return dict(sorted(tablo.items(), key=lambda kv: float(kv[0].split("–")[0].lstrip("%"))))


def kosullu_satirlar(tablo: dict[str, dict]) -> list[dict]:
    satirlar = []
    for d, t in tablo.items():
        n = t["ornek"]
        satir = {"ev_olasiligi": d, "ornek": n}
        for s in IYMS_SECENEKLERI + MS_SECENEKLERI:
            satir[s] = round(t[s] / n, 4) if n else 0
        satirlar.append(satir)
    return satirlar


# --- iddaa verisi yardımcıları ---

def market_cizgi(market: str, cizgi: str) -> str:
    """Çizgili marketler (Alt/Üst gibi) çizgiyle ayrılır: '2_101|2.5'."""
    return f"{market}|{cizgi}" if cizgi else market


def son_oranlar(simdi: datetime, marketler: set[str], geriye_gun: int = 2) -> dict[str, dict[str, dict]]:
    """{mac_id: {market: {"zaman": .., "oranlar": {secenek: oran}}}} - her maç/market için son anlık.
    Çizgili marketlerin anahtarı market_cizgi() ile oluşur (ör. '2_101|2.5')."""
    son: dict[str, dict[str, dict]] = defaultdict(dict)
    for dosya in depo.oran_dosyalari(simdi - timedelta(days=geriye_gun)):
        for satir in depo.gz_csv_oku(dosya):
            if satir["market"] not in marketler:
                continue
            anahtar = market_cizgi(satir["market"], satir.get("cizgi", ""))
            kayit = son[satir["mac_id"]].get(anahtar)
            if kayit is None or satir["zaman_utc"] > kayit["zaman"]:
                kayit = son[satir["mac_id"]][anahtar] = {"zaman": satir["zaman_utc"], "oranlar": {},
                                                         "mbs": (kayit or {}).get("mbs", "")}
            if satir["zaman_utc"] == kayit["zaman"]:
                kayit["oranlar"][satir["secenek"]] = float(satir["oran"])
                kayit["mbs"] = satir.get("mbs") or kayit["mbs"]
    return dict(son)


def kapanis_oranlari(kayitlar: dict, marketler: set[str],
                     cizgili: bool = False) -> dict[str, dict[str, dict[str, float]]]:
    """Her maç ve market için başlamadan önceki son oranlar: {mac_id: {market: {secenek: oran}}}.
    cizgili=True ise çizgili marketler ayrı anahtar alır ('2_101|2.5')."""
    son: dict[tuple[str, str], tuple[str, dict]] = {}
    ilk = min((k["baslama_utc"] for k in kayitlar.values() if k.get("baslama_utc")), default="")
    baslangic = iso_oku(ilk) - timedelta(days=5) if ilk else None
    for dosya in depo.oran_dosyalari(baslangic):
        for satir in depo.gz_csv_oku(dosya):
            if satir["market"] not in marketler:
                continue
            kayit = kayitlar.get(satir["mac_id"])
            if not kayit or satir["zaman_utc"] >= kayit["baslama_utc"]:
                continue
            market = market_cizgi(satir["market"], satir.get("cizgi", "")) if cizgili else satir["market"]
            anahtar = (satir["mac_id"], market)
            mevcut = son.get(anahtar)
            if mevcut is None or satir["zaman_utc"] > mevcut[0]:
                mevcut = son[anahtar] = (satir["zaman_utc"], {})
            if satir["zaman_utc"] == mevcut[0]:
                mevcut[1][satir["secenek"]] = float(satir["oran"])
    sonuc: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for (mac_id, market), (_, oranlar) in son.items():
        sonuc[mac_id][market] = oranlar
    return dict(sonuc)


def iddaa_ms_tablosu(kapanis: dict, sonuclar: dict) -> list[dict]:
    """Toplanan iddaa verisinden MS oran aralığı tablosu (sonuçlar geldikçe büyür)."""
    sayac = defaultdict(_bos_sayac)
    for mac_id, marketler in kapanis.items():
        oranlar = marketler.get(MS)
        sonuc = sonuclar.get(mac_id)
        if not oranlar or not sonuc or sonuc.get("durum") != "tamam":
            continue
        gercek = sonuc_isareti(int(sonuc["ms_ev"]), int(sonuc["ms_dep"]))
        for secim, oran in oranlar.items():
            if secim not in MS_SECENEKLERI:
                continue
            for anahtar in ((secim, oran_etiketi(oran)), ("hepsi", oran_etiketi(oran))):
                s = sayac[anahtar]
                s["ornek"] += 1
                s["vaat"] += 1 / oran
                if secim == gercek:
                    s["tuttu"] += 1
                    s["donus"] += oran
                    s["donus_maks"] += oran
    return _sirala([_satira_cevir({"secim": k[0], "oran": k[1]}, s) for k, s in sayac.items()])


# --- 3. Değer adayları ---

def deger_adaylari(oranlar: dict, kayitlar: dict, kosullu: dict[str, dict], simdi: datetime,
                   ufuk: timedelta = timedelta(hours=24), min_ornek: int = MIN_DILIM_ORNEGI) -> list[dict]:
    """Bugünkü iddaa oranları × geçmiş sıklık. Beklenen dönüş > 1 olanlar değerli görünür."""
    adaylar = []
    for mac_id, marketler in oranlar.items():
        kayit = kayitlar.get(mac_id)
        ms = (marketler.get(MS) or {}).get("oranlar", {})
        if not kayit or not all(s in ms for s in MS_SECENEKLERI):
            continue
        bas = iso_oku(kayit["baslama_utc"])
        if not (simdi < bas <= simdi + ufuk):
            continue
        p1 = normal_olasiliklar(ms["1"], ms["0"], ms["2"])[0]
        d = dilim(p1)
        satir = kosullu.get(d)
        if not satir or satir["ornek"] < min_ornek:
            continue
        adaylar_mac = [("MS", s, ms[s]) for s in MS_SECENEKLERI]
        iyms = (marketler.get(config.IYMS) or {}).get("oranlar", {})
        adaylar_mac += [("İY/MS", s, o) for s, o in iyms.items() if s in IYMS_SECENEKLERI]
        for market, secim, oran in adaylar_mac:
            siklik = satir[secim] / satir["ornek"]
            adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"],
                            "dep": kayit["dep"], "baslama_utc": kayit["baslama_utc"], "market": market,
                            "secim": secim, "oran": oran, "gecmis_siklik": round(siklik, 4),
                            "adil_oran": round(1 / siklik, 2) if siklik else None,
                            "beklenen": round(oran * siklik, 3), "ev_olasiligi": d, "ornek": satir["ornek"]})
    return sorted(adaylar, key=lambda a: -a["beklenen"])


# --- 4. MS 1-0-2: oranı geçmişte ne sıklıkla tuttu (kâr payı ayıklanmış olasılıkla eşleştirme) ---
#
# iddaa ile yabancı şirketlerin kâr payı farklıdır: iddaa'da 1.55 olan bir seçim, kâr payı düşük bir şirkette
# ~1.70 olur. Bu yüzden oranlar doğrudan değil, kâr payı ayıklanmış olasılık üzerinden eşleştirilir:
# bugünkü iddaa seçiminin adil olasılığı %60 ise, geçmişte adil olasılığı %58–62 olan seçimlere bakılır.

MS_OLASILIK_PENCERESI = 2   # ± yüzde puan
MS_MIN_ORNEK = 300


def ms_olasilik_tablosu(maclar: list[dict]) -> dict[str, list[list[int]]]:
    """{seçim: [[örnek, tuttu] × 100]} — indeks = adil olasılık yüzdesi (0–99)."""
    tablo = {s: [[0, 0] for _ in range(100)] for s in MS_SECENEKLERI}
    for m in maclar:
        oranlar = [m.get(f"ort_{s}") for s in MS_SECENEKLERI]
        if any(o is None for o in oranlar):
            continue
        gercek = sonuc_isareti(m["ms_ev"], m["ms_dep"])
        for secim, q in zip(MS_SECENEKLERI, normal_olasiliklar(*oranlar)):
            hucre = tablo[secim][min(int(q * 100), 99)]
            hucre[0] += 1
            hucre[1] += secim == gercek
    return tablo


def ms_tahmin(tablo: dict, secim: str, olasilik: float, pencere: int = MS_OLASILIK_PENCERESI) -> tuple[int, float]:
    """Adil olasılığı benzer geçmiş seçimlerde (örnek, tutma oranı)."""
    merkez = min(int(olasilik * 100), 99)
    n = t = 0
    for i in range(max(0, merkez - pencere), min(99, merkez + pencere) + 1):
        n += tablo[secim][i][0]
        t += tablo[secim][i][1]
    return n, (t / n if n else 0.0)


def ms_adaylari(oranlar: dict, kayitlar: dict, tablo: dict, simdi: datetime,
                ufuk: timedelta = timedelta(hours=24), min_ornek: int = MS_MIN_ORNEK) -> list[dict]:
    """Bugünkü iddaa MS seçimleri: geçmişte tutma oranı ve 1 TL'ye beklenen dönüş."""
    adaylar = []
    if not tablo:
        return adaylar
    for mac_id, marketler in oranlar.items():
        kayit = kayitlar.get(mac_id)
        ms = (marketler.get(MS) or {}).get("oranlar", {})
        if not kayit or not all(s in ms for s in MS_SECENEKLERI):
            continue
        if not (simdi < iso_oku(kayit["baslama_utc"]) <= simdi + ufuk):
            continue
        for secim, q in zip(MS_SECENEKLERI, normal_olasiliklar(ms["1"], ms["0"], ms["2"])):
            n, tutma = ms_tahmin(tablo, secim, q)
            if n < min_ornek:
                continue
            oran = ms[secim]
            adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                            "baslama_utc": kayit["baslama_utc"], "market": "MS", "secim": secim, "oran": oran,
                            "tutma": round(tutma, 4), "ornek": n, "beklenen": round(oran * tutma, 3),
                            "hata": round(1.96 * oran * math.sqrt(tutma * (1 - tutma) / n), 3)})
    return sorted(adaylar, key=lambda a: -a["beklenen"])


# --- 5. Toplam gol (0-1 / 2-3 / 4-5 / 6+) ---
#
# Geçmiş maçlar, 2.5 Alt/Üst oranlarından (kâr payı ayıklanmış) "Üst" olasılığına göre %5'lik dilimlere ayrılır;
# her dilimde toplam gol dağılımı sayılır. Bugünkü iddaa maçı, kendi 2.5 Alt/Üst oranıyla dilimine yerleşir.

TOPLAM_GOL = "2_4"
ALT_UST = "2_101"
ALT_UST_25 = market_cizgi(ALT_UST, "2.5")
GOL_UST_SINIR = 10  # 10 ve üstü tek hücrede


def gol_tablosu(maclar: list[dict]) -> dict[str, dict]:
    """{dilim: {"ornek": n, "goller": [0 gol, 1 gol, ..., 10+ gol]}}"""
    tablo: dict[str, dict] = {}
    for m in maclar:
        ust, alt = m.get("ort_ust25"), m.get("ort_alt25")
        if not ust or not alt:
            continue
        p_ust = (1 / ust) / (1 / ust + 1 / alt)
        d = tablo.setdefault(dilim(p_ust), {"ornek": 0, "goller": [0] * (GOL_UST_SINIR + 1)})
        d["ornek"] += 1
        d["goller"][min(m["ms_ev"] + m["ms_dep"], GOL_UST_SINIR)] += 1
    return dict(sorted(tablo.items(), key=lambda kv: float(kv[0].split("–")[0].lstrip("%"))))


def gol_araligi(secenek: str) -> tuple[int, int] | None:
    """'2-3 gol' -> (2, 3), '6+ gol' -> (6, 99), '1 gol' -> (1, 1)."""
    metin = secenek.lower().replace("gol", "").strip()
    try:
        if metin.endswith("+"):
            return int(metin[:-1]), 99
        if "-" in metin:
            a, b = metin.split("-", 1)
            return int(a), int(b)
        return int(metin), int(metin)
    except ValueError:
        return None


def gol_sikligi(dilim_verisi: dict, aralik: tuple[int, int]) -> float:
    n = dilim_verisi["ornek"]
    toplam = sum(c for g, c in enumerate(dilim_verisi["goller"]) if aralik[0] <= g <= aralik[1])
    return toplam / n if n else 0.0


def gol_adaylari(oranlar: dict, kayitlar: dict, tablo: dict, simdi: datetime,
                 ufuk: timedelta = timedelta(hours=24), min_ornek: int = MIN_DILIM_ORNEGI) -> list[dict]:
    adaylar = []
    if not tablo:
        return adaylar
    for mac_id, marketler in oranlar.items():
        kayit = kayitlar.get(mac_id)
        au = (marketler.get(ALT_UST_25) or {}).get("oranlar", {})
        tg = (marketler.get(TOPLAM_GOL) or {}).get("oranlar", {})
        if not kayit or "Alt" not in au or "Üst" not in au or not tg:
            continue
        if not (simdi < iso_oku(kayit["baslama_utc"]) <= simdi + ufuk):
            continue
        p_ust = (1 / au["Üst"]) / (1 / au["Üst"] + 1 / au["Alt"])
        d = tablo.get(dilim(p_ust))
        if not d or d["ornek"] < min_ornek:
            continue
        for secenek, oran in tg.items():
            aralik = gol_araligi(secenek)
            if not aralik:
                continue
            siklik = gol_sikligi(d, aralik)
            if not siklik:
                continue
            adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                            "baslama_utc": kayit["baslama_utc"], "market": "Toplam gol", "secim": secenek,
                            "oran": oran, "tutma": round(siklik, 4), "ornek": d["ornek"],
                            "beklenen": round(oran * siklik, 3)})
    return sorted(adaylar, key=lambda a: -a["beklenen"])


# --- Kaydetme / okuma ---

def analiz_yolu(ad: str):
    return depo.kok() / "analiz" / ad


def gecmis_analizi_yaz(maclar: list[dict]) -> dict:
    ms_tablo = ms_oran_tablosu(maclar)
    kosullu = iyms_kosullu_tablo(maclar)
    ms_alan = ["secim", "oran", "ornek", "tuttu", "tutma", "vaat", "getiri", "hata", "getiri_maks"]
    depo.csv_yaz(analiz_yolu("gecmis_ms_oran.csv"), ms_tablo, ms_alan)
    depo.csv_yaz(analiz_yolu("gecmis_iyms_kosullu.csv"), kosullu_satirlar(kosullu),
                 ["ev_olasiligi", "ornek"] + IYMS_SECENEKLERI + MS_SECENEKLERI)
    depo.json_yaz(analiz_yolu("gecmis_iyms_kosullu.json"), kosullu)
    depo.json_yaz(analiz_yolu("gecmis_ms_olasilik.json"), ms_olasilik_tablosu(maclar))
    depo.json_yaz(analiz_yolu("gecmis_gol.json"), gol_tablosu(maclar))
    ozet = {"mac": len(maclar), "lig": len({m["lig"] for m in maclar}),
            "ilk": min((m["tarih"] for m in maclar), default=""),
            "son": max((m["tarih"] for m in maclar), default="")}
    depo.json_yaz(analiz_yolu("gecmis_ozet.json"), ozet)
    return ozet


def gol_tablosu_oku() -> dict:
    return depo.json_oku(analiz_yolu("gecmis_gol.json")) or {}


def ms_olasilik_oku() -> dict:
    return depo.json_oku(analiz_yolu("gecmis_ms_olasilik.json")) or {}


def kosullu_oku() -> dict[str, dict]:
    return depo.json_oku(analiz_yolu("gecmis_iyms_kosullu.json")) or {}


def ms_tablosu_oku() -> list[dict]:
    satirlar = depo.csv_oku(analiz_yolu("gecmis_ms_oran.csv"))
    for s in satirlar:
        for k in ("ornek", "tuttu"):
            s[k] = int(s[k])
        for k in ("tutma", "vaat", "getiri", "getiri_maks", "hata"):
            s[k] = float(s.get(k) or 0)
    return satirlar


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    maclar = gecmis.oku()
    if not maclar:
        raise SystemExit("Önce geçmiş veriyi indir: python -m iddaa.gecmis")
    log.info("geçmiş analiz: %s", gecmis_analizi_yaz(maclar))


if __name__ == "__main__":
    main()
