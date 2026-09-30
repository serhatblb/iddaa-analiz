"""Sanal tekli bahisler: modelin değerli bulduğu her seçim 1 TL oynanmış gibi kaydedilir.

Her maç, başlamasına 20 dakika ile 4 saat kala ilk saatlik çalışmada bir kez değerlendirilir (maça yakın oranlar
daha çok bilgi taşır). Beklenen dönüşü (iddaa.com oranı × model olasılığı) eşiğin üstündeki bütün seçimler yazılır.
Sonuç gelince tuttu mu, ve kapanış oranı (maç başlamadan önceki son oran) ile karşılaştırma yapılır:
  CLV = aldığımız oran / kapanış oranı. Sürekli 1'in üstündeyse piyasadan erken ve doğru davranıyoruz demektir.
1-2 haftada kuponlardan çok daha fazla örnek birikir; modelin işe yarayıp yaramadığını asıl bu gösterir.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import analiz, depo, kalibrasyon
from .bulten import iso, iso_oku

log = logging.getLogger("tekler")

ALANLAR = ["zaman_utc", "mac_id", "lig", "mk_lig", "ev", "dep", "baslama_utc", "market", "secim", "oran",
           "olasilik", "beklenen", "mbs"]
ESIK = 1.0
PENCERE = (timedelta(minutes=20), timedelta(hours=4))
MARKET_ANAHTARLARI = {m["anahtar"].split("|")[0] for m in kalibrasyon.MARKETLER.values()}


def dizin():
    return depo.kok() / "tekler"


def oku() -> list[dict]:
    satirlar = []
    for yol in sorted(dizin().glob("*.csv")):
        satirlar += depo.csv_oku(yol)
    return satirlar


def calistir(simdi: datetime | None = None, model: dict | None = None) -> dict:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    model = kalibrasyon.model_oku() if model is None else model
    ozet = {"mac": 0, "secim": 0}
    if not model.get("marketler"):
        return ozet
    kayitlar = depo.maclari_oku()
    yakin = {m: k for m, k in kayitlar.items()
             if k.get("ev") and PENCERE[0] <= iso_oku(k["baslama_utc"]) - simdi <= PENCERE[1]}
    if not yakin:
        return ozet
    yol = dizin() / f"{simdi.strftime('%Y-%m')}.csv"
    mevcut = depo.csv_oku(yol)
    goruldu = {s["mac_id"] for s in mevcut}
    # Önceki ayın dosyasında da olabilir (ay dönümü)
    onceki = dizin() / f"{(simdi.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')}.csv"
    goruldu |= {s["mac_id"] for s in depo.csv_oku(onceki)}
    oranlar = analiz.son_oranlar(simdi, MARKET_ANAHTARLARI, geriye_gun=3)
    yeni = []
    for mac_id, kayit in yakin.items():
        if mac_id in goruldu or mac_id not in oranlar:
            continue
        ozet["mac"] += 1
        for s in kalibrasyon.mac_secenekleri(model, oranlar[mac_id], kayit.get("mk_lig") or None):
            if s["beklenen"] < ESIK:
                continue
            yeni.append({"zaman_utc": iso(simdi), "mac_id": mac_id, "lig": kayit.get("lig", ""),
                         "mk_lig": kayit.get("mk_lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                         "baslama_utc": kayit["baslama_utc"], "market": s["market"], "secim": s["secim"],
                         "oran": s["oran"], "olasilik": s["olasilik"], "beklenen": s["beklenen"],
                         "mbs": s["mbs"] or kayit.get("mbs", "")})
        if not any(y["mac_id"] == mac_id for y in yeni):
            # Değerli seçimi olmayan maç da işaretlenir ki bir daha bakılmasın
            yeni.append({"zaman_utc": iso(simdi), "mac_id": mac_id, "lig": kayit.get("lig", ""),
                         "mk_lig": kayit.get("mk_lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                         "baslama_utc": kayit["baslama_utc"], "market": "", "secim": ""})
    ozet["secim"] = sum(1 for y in yeni if y.get("market"))
    if yeni:
        depo.csv_yaz(yol, mevcut + yeni, ALANLAR)
    return ozet


def _kapanis(simdi_oncesi: dict, kayitlar: dict) -> dict[tuple, float]:
    """(mac_id, market adı, seçim) -> maç başlamadan önceki son oran."""
    anahtarlar = {m["anahtar"]: ad for ad, m in kalibrasyon.MARKETLER.items()}
    sonuc = {}
    for mac_id, marketler in simdi_oncesi.items():
        for anahtar, oranlar in marketler.items():
            ad = anahtarlar.get(anahtar)
            if ad:
                for secim, oran in oranlar.items():
                    sonuc[(mac_id, ad, secim)] = oran
    return sonuc


def degerlendir(satirlar: list[dict] | None = None) -> dict:
    """Sonuçlanan sanal teklilerin özeti: market ve beklenen dilimine göre; toplamda getiri ve CLV."""
    satirlar = [s for s in (oku() if satirlar is None else satirlar) if s.get("market")]
    sonuclar = depo.sonuclari_oku()
    kayitlar = depo.maclari_oku()
    ilgili = {s["mac_id"] for s in satirlar}
    anahtarlar = {m["anahtar"].split("|")[0] for m in kalibrasyon.MARKETLER.values()}
    kapanis = _kapanis(analiz.kapanis_oranlari({m: kayitlar[m] for m in ilgili if m in kayitlar},
                                               anahtarlar, cizgili=True), kayitlar)
    gruplar = defaultdict(lambda: {"bahis": 0, "tutan": 0, "donus": 0.0, "beklenen": 0.0, "clv": 0.0, "clv_n": 0})
    bekleyen = 0
    for s in satirlar:
        sonuc = sonuclar.get(s["mac_id"])
        if not sonuc or sonuc.get("durum") != "tamam":
            bekleyen += sonuc is None or sonuc.get("durum") not in ("iptal", "belirsiz")
            continue
        skor = tuple(int(sonuc[k]) for k in ("iy_ev", "iy_dep", "ms_ev", "ms_dep"))
        tuttu = kalibrasyon.kazanan(s["market"], *skor) == s["secim"]
        oran, beklenen = float(s["oran"]), float(s["beklenen"])
        kap = kapanis.get((s["mac_id"], s["market"], s["secim"]))
        dilim = "1.00–1.05" if beklenen < 1.05 else "1.05–1.10" if beklenen < 1.10 else "1.10+"
        for anahtar in (("hepsi", ""), (s["market"], ""), ("hepsi", dilim)):
            g = gruplar[anahtar]
            g["bahis"] += 1
            g["tutan"] += tuttu
            g["donus"] += oran if tuttu else 0.0
            g["beklenen"] += beklenen
            if kap:
                g["clv"] += oran / kap
                g["clv_n"] += 1
    ozet = []
    for (market, dilim), g in sorted(gruplar.items(), key=lambda kv: (kv[0][0] != "hepsi", kv[0])):
        n = g["bahis"]
        ozet.append({"market": market, "dilim": dilim, "bahis": n, "tutan": g["tutan"],
                     "getiri": round(g["donus"] / n, 3), "beklenen": round(g["beklenen"] / n, 3),
                     "clv": round(g["clv"] / g["clv_n"], 3) if g["clv_n"] else None})
    return {"satirlar": ozet, "bekleyen": bekleyen}
