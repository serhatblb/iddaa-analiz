"""Pinnacle karşılaştırması (The Odds API): iddaa oranı, Pinnacle'ın adil fiyatından yüksek mi?

Geçmiş testte (scripts/yabanci_karsilastirma.py) maç önü son oranlarda iddaa'nın Pinnacle'ın adil fiyatını geçtiği seçim
binde birden azdı. Açık kalan soru: iddaa oranları gün içinde geç güncelleniyorsa sabah saatlerinde fark var mı?
Bunu ölçmek için her gün bir kez (kuponlarla aynı çalışmada, 09:40'tan sonra) bugünün maçları için Pinnacle MS (1-0-2)
oranları alınır ve aynı andaki iddaa oranlarıyla yan yana yazılır:
  beklenen = iddaa oranı × Pinnacle'ın kâr payı ayıklanmış olasılığı   (>1 ise iddaa fazla veriyor)

Kota: ücretsiz planda ayda 500 kredi. /sports ve /events ücretsiz; /odds çağrısı lig başına 1 kredi (1 market × 1 bölge).
Sadece iddaa'da eşleşen maçı olan liglerin oranı istenir ve günlük kredi, ayın kalan günlerine bölünerek sınırlanır.
Anahtar ODDS_API_KEY ortam değişkeninden okunur (GitHub secret); yoksa adım sessizce atlanır.
"""
import calendar
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from . import analiz, config, depo, isim
from .bulten import iso, iso_oku

log = logging.getLogger("pinnacle")

API = "https://api.the-odds-api.com/v4"
ALANLAR = ["zaman_utc", "lig", "olay_id", "baslama_utc", "ev_en", "dep_en", "mac_id", "ev", "dep",
           "p_1", "p_0", "p_2", "i_1", "i_0", "i_2", "b_1", "b_0", "b_2"]
ZAMAN_FARKI = timedelta(minutes=20)


class OddsApi:
    def __init__(self, anahtar: str):
        self.anahtar = anahtar
        self.oturum = requests.Session()
        self.kalan: int | None = None

    def getir(self, yol: str, **params):
        yanit = self.oturum.get(f"{API}{yol}", params={"apiKey": self.anahtar, **params}, timeout=30)
        if yanit.headers.get("x-requests-remaining") is not None:
            try:
                self.kalan = int(float(yanit.headers["x-requests-remaining"]))
            except ValueError:
                pass
        yanit.raise_for_status()
        return yanit.json()


def dizin():
    return depo.kok() / "pinnacle"


def _z(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def gunluk_kredi(kalan: int | None, bugun) -> int:
    """Ayın kalan günlerine eşit bölünmüş günlük kredi (en az 1)."""
    if kalan is None:
        return 10
    gun_kalan = calendar.monthrange(bugun.year, bugun.month)[1] - bugun.day + 1
    return max(1, kalan // max(gun_kalan, 1))


def adil(oranlar: dict[str, float]) -> dict[str, float]:
    ters = {s: 1 / o for s, o in oranlar.items()}
    toplam = sum(ters.values())
    return {s: t / toplam for s, t in ters.items()}


def calistir(simdi: datetime | None = None, anahtar: str | None = None, api=None) -> dict:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    anahtar = anahtar if anahtar is not None else os.environ.get("ODDS_API_KEY", "")
    if not anahtar and api is None:
        return {"durum": "anahtar yok"}
    yerel = simdi.astimezone(config.TR)
    yol = dizin() / f"{yerel.date().isoformat()}.csv"
    if yol.exists():
        return {"durum": "bugün alındı"}
    api = api or OddsApi(anahtar)
    gun_sonu = datetime.combine(yerel.date() + timedelta(days=1), datetime.min.time(), tzinfo=config.TR)

    # iddaa: bugün başlayacak, MS oranı olan maçlar
    kayitlar = depo.maclari_oku()
    oranlar = analiz.son_oranlar(simdi, {analiz.MS})
    iddaa = []
    for mac_id, k in kayitlar.items():
        ms = (oranlar.get(mac_id, {}).get(analiz.MS) or {}).get("oranlar", {})
        if k.get("ev") and all(s in ms for s in "102") and simdi < iso_oku(k["baslama_utc"]) < gun_sonu:
            iddaa.append((k, ms))
    ozet = {"durum": "tamam", "iddaa_mac": len(iddaa), "lig": 0, "eslesen": 0, "kredi": 0}
    if not iddaa:
        ozet["durum"] = "maç yok"
        return ozet

    # Ücretsiz: futbol ligleri ve bugünkü maçları; iddaa maçlarıyla eşleştir
    ligler = [s["key"] for s in api.getir("/sports") if s.get("group") == "Soccer" and s.get("active")
              and not s.get("has_outrights")]
    eslesme: dict[str, dict[str, tuple]] = {}
    for lig in ligler:
        try:
            olaylar = api.getir(f"/sports/{lig}/events", commenceTimeFrom=_z(simdi), commenceTimeTo=_z(gun_sonu))
        except requests.RequestException as hata:
            log.warning("%s olayları alınamadı: %s", lig, hata)
            continue
        for o in olaylar or []:
            bas = datetime.fromisoformat(o["commence_time"].replace("Z", "+00:00"))
            adaylar = [(k["ev"], k["dep"], (k, ms)) for k, ms in iddaa
                       if abs(iso_oku(k["baslama_utc"]) - bas) <= ZAMAN_FARKI]
            bulunan = isim.en_iyi_eslesme(o["home_team"], o["away_team"], adaylar)
            if bulunan:
                eslesme.setdefault(lig, {})[o["id"]] = bulunan

    # Ücretli: eşleşen maçı en çok olan ligler, günlük kredi kadar
    sirali = sorted(eslesme, key=lambda l: -len(eslesme[l]))
    hak = gunluk_kredi(api.kalan, yerel)
    satirlar = []
    for lig in sirali:
        if ozet["kredi"] >= hak:
            break
        try:
            veriler = api.getir(f"/sports/{lig}/odds", regions="eu", markets="h2h", bookmakers="pinnacle",
                                oddsFormat="decimal", eventIds=",".join(eslesme[lig]))
        except requests.RequestException as hata:
            log.warning("%s oranları alınamadı: %s", lig, hata)
            continue
        ozet["kredi"] += 1
        ozet["lig"] += 1
        for o in veriler or []:
            if o["id"] not in eslesme[lig]:
                continue
            k, ms = eslesme[lig][o["id"]]
            pin = {}
            for b in o.get("bookmakers") or []:
                for m in b.get("markets") or []:
                    if b.get("key") == "pinnacle" and m.get("key") == "h2h":
                        for c in m.get("outcomes") or []:
                            s = "1" if c["name"] == o["home_team"] else "2" if c["name"] == o["away_team"] else "0"
                            pin[s] = float(c["price"])
            if set(pin) != {"1", "0", "2"}:
                continue
            p = adil(pin)
            satir = {"zaman_utc": iso(simdi), "lig": lig, "olay_id": o["id"], "baslama_utc": k["baslama_utc"],
                     "ev_en": o["home_team"], "dep_en": o["away_team"], "mac_id": k["mac_id"], "ev": k["ev"],
                     "dep": k["dep"]}
            for s in "102":
                satir[f"p_{s}"] = pin[s]
                satir[f"i_{s}"] = ms[s]
                satir[f"b_{s}"] = round(ms[s] * p[s], 4)
            satirlar.append(satir)
    ozet["eslesen"] = len(satirlar)
    ozet["kalan_kredi"] = api.kalan
    depo.csv_yaz(yol, satirlar, ALANLAR)  # boş da yazılır ki gün içinde tekrar kredi harcanmasın
    return ozet


def oku() -> list[dict]:
    satirlar = []
    for yol in sorted(dizin().glob("*.csv")):
        satirlar += depo.csv_oku(yol)
    return satirlar


def firsatlar(tarih: str, esik: float = 1.0) -> list[dict]:
    """O günün iddaa oranı Pinnacle'ın adil fiyatını geçen seçimleri: [{maç, seçim, iddaa oranı, beklenen}]."""
    yol = dizin() / f"{tarih}.csv"
    cikti = []
    for s in depo.csv_oku(yol):
        for secim in "102":
            b = float(s[f"b_{secim}"])
            if b >= esik:
                cikti.append({"ev": s["ev"], "dep": s["dep"], "baslama_utc": s["baslama_utc"], "secim": secim,
                              "oran": float(s[f"i_{secim}"]), "pinnacle": float(s[f"p_{secim}"]), "beklenen": b})
    return sorted(cikti, key=lambda x: -x["beklenen"])


def degerlendir(esik: float = 1.0) -> dict:
    """Sonuçlanan maçlarda: beklenen ≥ eşik olan seçimlere 1 TL oynansaydı. Ayrıca bütün seçimlerde ortalama."""
    sonuclar = depo.sonuclari_oku()
    gruplar = {"firsat": [0, 0, 0.0], "hepsi": [0, 0, 0.0]}
    gun = set()
    for s in oku():
        sonuc = sonuclar.get(s["mac_id"])
        if not sonuc or sonuc.get("durum") != "tamam":
            continue
        gun.add(s["zaman_utc"][:10])
        ev, dep = int(sonuc["ms_ev"]), int(sonuc["ms_dep"])
        gercek = "1" if ev > dep else "2" if dep > ev else "0"
        for secim in "102":
            oran, tuttu = float(s[f"i_{secim}"]), secim == gercek
            anahtarlar = ["hepsi"] + (["firsat"] if float(s[f"b_{secim}"]) >= esik else [])
            for a in anahtarlar:
                g = gruplar[a]
                g[0] += 1
                g[1] += tuttu
                g[2] += oran if tuttu else 0.0
    return {a: {"bahis": n, "tutan": t, "getiri": round(d / n, 3) if n else None} for a, (n, t, d) in gruplar.items()} | {
        "gun": len(gun)}
