"""Günlük kağıt üstü kuponlar. Para yatırılmaz; seçimler kaydedilir, sonuçlar gelince değerlendirilir.

İki kupon türü:
- iyms:  Önümüzdeki 24 saatte başlayacak maçlarda oranı 20–30 arası İY/MS seçenekleri. Her maçtan
         aralıktaki en yüksek oranlı seçenek aday olur; en yüksek oranlı 3 aday kupona girer.
- deger: MS 1-0-2 ve İY/MS seçenekleri içinden, geçmiş veriye göre beklenen dönüşü 1'in üstünde olanlar.
         Her maçtan en iyi seçim aday olur; beklenen dönüşü en yüksek 3 aday kupona girer.
"""
import logging
from datetime import datetime, timedelta, timezone

from . import analiz, config, depo
from .bulten import iso_oku, iyms_sonucu, sonuc_isareti

log = logging.getLogger("kupon")

KUPON_ALANLARI = ["tarih", "tur", "sira", "mac_id", "lig", "ev", "dep", "baslama_utc", "market", "secim",
                  "oran", "beklenen", "gercek", "tuttu", "toplam_oran", "tutar", "durum", "kazanc"]
TURLER = {"iyms": "İY/MS kuponu", "deger": "Değer kuponu"}
EN_ERKEN_BASLAMA = timedelta(minutes=15)
PENCERE = timedelta(hours=24)


def kupon_yolu():
    return depo.kok() / "kuponlar.csv"


def _pencerede(kayit: dict, simdi: datetime) -> bool:
    bas = iso_oku(kayit["baslama_utc"])
    return simdi + EN_ERKEN_BASLAMA <= bas <= simdi + PENCERE


# --- aday bulma ---

def iyms_adaylari(oranlar: dict, kayitlar: dict, simdi: datetime,
                  min_oran: float = config.KUPON_MIN_ORAN, max_oran: float = config.KUPON_MAX_ORAN) -> list[dict]:
    adaylar = []
    for mac_id, marketler in oranlar.items():
        kayit = kayitlar.get(mac_id)
        iyms = (marketler.get(config.IYMS) or {}).get("oranlar", {})
        if not kayit or not iyms or not _pencerede(kayit, simdi):
            continue
        uygun = [(o, s) for s, o in iyms.items() if min_oran <= o <= max_oran]
        if not uygun:
            continue
        oran, secim = max(uygun)
        adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                        "baslama_utc": kayit["baslama_utc"], "market": "İY/MS", "secim": secim, "oran": oran,
                        "beklenen": ""})
    return sorted(adaylar, key=lambda a: (-a["oran"], a["baslama_utc"], a["mac_id"]))


def deger_adaylari(oranlar: dict, kayitlar: dict, kosullu: dict, simdi: datetime) -> list[dict]:
    if not kosullu:
        return []
    en_iyi: dict[str, dict] = {}
    for a in analiz.deger_adaylari(oranlar, kayitlar, kosullu, simdi, ufuk=PENCERE):
        if a["beklenen"] <= 1 or not _pencerede(kayitlar[a["mac_id"]], simdi):
            continue
        if a["mac_id"] not in en_iyi or a["beklenen"] > en_iyi[a["mac_id"]]["beklenen"]:
            en_iyi[a["mac_id"]] = a
    return sorted(({k: a[k] for k in ("mac_id", "lig", "ev", "dep", "baslama_utc", "market", "secim", "oran",
                                      "beklenen")} for a in en_iyi.values()),
                  key=lambda a: (-a["beklenen"], a["baslama_utc"], a["mac_id"]))


def oneriler(simdi: datetime | None = None) -> dict[str, list[dict]]:
    """Şu anki oranlarla her iki kupon türünün aday listesi."""
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    kayitlar = depo.maclari_oku()
    oranlar = analiz.son_oranlar(simdi, {config.IYMS, analiz.MS})
    return {"iyms": iyms_adaylari(oranlar, kayitlar, simdi),
            "deger": deger_adaylari(oranlar, kayitlar, analiz.kosullu_oku(), simdi)}


# --- kupon oluşturma ve değerlendirme ---

def kupon_olustur(tarih: str, tur: str, adaylar: list[dict], mac_sayisi: int = config.KUPON_MAC_SAYISI,
                  tutar: float = config.KUPON_TUTARI) -> list[dict]:
    if len(adaylar) < mac_sayisi:
        return [{"tarih": tarih, "tur": tur, "sira": 0, "durum": "aday_yok", "tutar": 0, "kazanc": 0,
                 "secim": f"{len(adaylar)} aday"}]
    secilen = adaylar[:mac_sayisi]
    toplam = 1.0
    for a in secilen:
        toplam *= a["oran"]
    return [{**a, "tarih": tarih, "tur": tur, "sira": i + 1, "gercek": "", "tuttu": "",
             "toplam_oran": round(toplam, 2), "tutar": tutar, "durum": "bekliyor", "kazanc": ""}
            for i, a in enumerate(secilen)]


def gercek_sonuc(market: str, sonuc: dict) -> str:
    iy_ev, iy_dep, ms_ev, ms_dep = (int(sonuc[k]) for k in ("iy_ev", "iy_dep", "ms_ev", "ms_dep"))
    if market == "MS":
        return sonuc_isareti(ms_ev, ms_dep)
    return iyms_sonucu(iy_ev, iy_dep, ms_ev, ms_dep)


def kupon_degerlendir(satirlar: list[dict], sonuclar: dict) -> None:
    """Aynı kupona ait satırları yerinde günceller."""
    if not satirlar or satirlar[0]["durum"] == "aday_yok":
        return
    for s in satirlar:
        if s["tuttu"] in ("1", "0", "iptal"):
            continue
        sonuc = sonuclar.get(str(s["mac_id"]))
        if not sonuc:
            continue
        if sonuc["durum"] == "iptal":
            s["tuttu"], s["gercek"] = "iptal", "iptal"
        elif sonuc["durum"] == "belirsiz":
            s["tuttu"], s["gercek"] = "?", "sonuç yok"
        elif sonuc["durum"] == "tamam":
            s["gercek"] = gercek_sonuc(s.get("market") or "İY/MS", sonuc)
            s["tuttu"] = "1" if s["gercek"] == s["secim"] else "0"
    tutar = float(satirlar[0]["tutar"])
    if any(s["tuttu"] == "0" for s in satirlar):
        durum, kazanc = "kaybetti", 0.0
    elif all(s["tuttu"] in ("1", "iptal") for s in satirlar):
        toplam = 1.0
        for s in satirlar:
            toplam *= 1.0 if s["tuttu"] == "iptal" else float(s["oran"])
        durum, kazanc = "kazandi", round(tutar * toplam, 2)
        for s in satirlar:
            s["toplam_oran"] = round(toplam, 2)
    elif all(s["tuttu"] for s in satirlar):
        durum, kazanc = "belirsiz", 0.0
    else:
        return
    for s in satirlar:
        s["durum"], s["kazanc"] = durum, kazanc


def kuponlari_oku() -> list[dict]:
    satirlar = depo.csv_oku(kupon_yolu())
    for s in satirlar:
        s["tur"] = s.get("tur") or "iyms"
        s["market"] = s.get("market") or ("İY/MS" if s["durum"] != "aday_yok" else "")
    return satirlar


def kuponlara_ayir(satirlar: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """{(tarih, tur): satırlar}"""
    kuponlar: dict[tuple[str, str], list[dict]] = {}
    for s in satirlar:
        kuponlar.setdefault((s["tarih"], s["tur"]), []).append(s)
    return kuponlar


def kasa(kuponlar: dict, tur: str) -> dict:
    oynanan = [g for (_, t), g in kuponlar.items() if t == tur and g[0]["durum"] not in ("aday_yok", "belirsiz")]
    yatirilan = sum(float(g[0]["tutar"]) for g in oynanan)
    donen = sum(float(g[0]["kazanc"] or 0) for g in oynanan if g[0]["durum"] == "kazandi")
    return {"kupon": len(oynanan), "kazanan": sum(1 for g in oynanan if g[0]["durum"] == "kazandi"),
            "sonuclanan": sum(1 for g in oynanan if g[0]["durum"] in ("kazandi", "kaybetti")),
            "yatirilan": yatirilan, "donen": donen, "net": donen - yatirilan,
            "kalan": config.KUPON_BUTCE - yatirilan + donen}


def calistir(simdi: datetime | None = None) -> dict:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    tarih = simdi.astimezone(config.TR).date().isoformat()
    satirlar = kuponlari_oku()
    sonuclar = depo.sonuclari_oku()
    for grup in kuponlara_ayir(satirlar).values():
        kupon_degerlendir(grup, sonuclar)

    ozet = {"tarih": tarih}
    mevcut = {(s["tarih"], s["tur"]) for s in satirlar}
    eksik = [t for t in TURLER if (tarih, t) not in mevcut]
    if eksik:
        adaylar = oneriler(simdi)
        for tur in eksik:
            yeni = kupon_olustur(tarih, tur, adaylar[tur])
            satirlar += yeni
            ozet[tur] = f"{yeni[0]['durum']} ({len(adaylar[tur])} aday)"
        depo.json_yaz(depo.kok() / "adaylar" / f"{tarih}.json", adaylar)
    depo.csv_yaz(kupon_yolu(), satirlar, KUPON_ALANLARI)
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("özet: %s", calistir())


if __name__ == "__main__":
    main()
