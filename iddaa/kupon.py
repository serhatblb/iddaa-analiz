"""Günlük kağıt üstü kupon: oranı 20–30 arası İY/MS seçeneklerinden 3'lü.

Para yatırılmaz; seçimler kaydedilir, sonuçlar gelince değerlendirilir.
Kural: önümüzdeki 24 saatte başlayacak maçlarda, en son alınan İY/MS oranlarına bakılır.
Her maçtan aralıktaki en yüksek oranlı seçenek aday olur; en yüksek oranlı 3 aday kupona girer.
"""
import logging
from datetime import datetime, timedelta, timezone

from . import config, depo
from .bulten import iso_oku, iyms_sonucu

log = logging.getLogger("kupon")

KUPON_ALANLARI = ["tarih", "sira", "mac_id", "lig", "ev", "dep", "baslama_utc", "secim", "oran",
                  "gercek", "tuttu", "toplam_oran", "tutar", "durum", "kazanc"]
EN_ERKEN_BASLAMA = timedelta(minutes=15)
PENCERE = timedelta(hours=24)


def kupon_yolu():
    return depo.kok() / "kuponlar.csv"


def son_iyms_oranlari(simdi: datetime, geriye_gun: int = 2) -> dict[str, dict]:
    """Her maç için en son İY/MS anlığı: {mac_id: {"zaman": .., "oranlar": {secenek: oran}}}."""
    son: dict[str, dict] = {}
    for dosya in depo.oran_dosyalari(simdi - timedelta(days=geriye_gun)):
        for satir in depo.gz_csv_oku(dosya):
            if satir["market"] != config.IYMS:
                continue
            kayit = son.get(satir["mac_id"])
            if kayit is None or satir["zaman_utc"] > kayit["zaman"]:
                kayit = son[satir["mac_id"]] = {"zaman": satir["zaman_utc"], "oranlar": {}}
            if satir["zaman_utc"] == kayit["zaman"]:
                kayit["oranlar"][satir["secenek"]] = float(satir["oran"])
    return son


def adaylari_bul(son_oranlar: dict, kayitlar: dict, simdi: datetime,
                 min_oran: float = config.KUPON_MIN_ORAN, max_oran: float = config.KUPON_MAX_ORAN) -> list[dict]:
    adaylar = []
    for mac_id, veri in son_oranlar.items():
        kayit = kayitlar.get(mac_id)
        if not kayit:
            continue
        bas = iso_oku(kayit["baslama_utc"])
        if not (simdi + EN_ERKEN_BASLAMA <= bas <= simdi + PENCERE):
            continue
        uygun = [(o, s) for s, o in veri["oranlar"].items() if min_oran <= o <= max_oran]
        if not uygun:
            continue
        oran, secim = max(uygun)
        adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"],
                        "dep": kayit["dep"], "baslama_utc": kayit["baslama_utc"],
                        "secim": secim, "oran": oran})
    return sorted(adaylar, key=lambda a: (-a["oran"], a["baslama_utc"], a["mac_id"]))


def kupon_olustur(tarih: str, adaylar: list[dict], mac_sayisi: int = config.KUPON_MAC_SAYISI,
                  tutar: float = config.KUPON_TUTARI) -> list[dict]:
    if len(adaylar) < mac_sayisi:
        return [{"tarih": tarih, "sira": 0, "durum": "aday_yok", "tutar": 0, "kazanc": 0,
                 "secim": f"{len(adaylar)} aday"}]
    secilen = adaylar[:mac_sayisi]
    toplam = 1.0
    for a in secilen:
        toplam *= a["oran"]
    return [{**a, "tarih": tarih, "sira": i + 1, "gercek": "", "tuttu": "",
             "toplam_oran": round(toplam, 2), "tutar": tutar, "durum": "bekliyor", "kazanc": ""}
            for i, a in enumerate(secilen)]


def kupon_degerlendir(satirlar: list[dict], sonuclar: dict) -> None:
    """Aynı tarihe ait kupon satırlarını yerinde günceller."""
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
        elif sonuc["durum"] == "tamam":
            gercek = iyms_sonucu(int(sonuc["iy_ev"]), int(sonuc["iy_dep"]),
                                 int(sonuc["ms_ev"]), int(sonuc["ms_dep"]))
            s["gercek"] = gercek
            s["tuttu"] = "1" if gercek == s["secim"] else "0"
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
    else:
        return
    for s in satirlar:
        s["durum"], s["kazanc"] = durum, kazanc


def gunlere_ayir(satirlar: list[dict]) -> dict[str, list[dict]]:
    gunler: dict[str, list[dict]] = {}
    for s in satirlar:
        gunler.setdefault(s["tarih"], []).append(s)
    return gunler


def calistir(simdi: datetime | None = None) -> dict:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    tarih = simdi.astimezone(config.TR).date().isoformat()
    satirlar = depo.csv_oku(kupon_yolu())
    sonuclar = depo.sonuclari_oku()

    for gun_satirlari in gunlere_ayir(satirlar).values():
        kupon_degerlendir(gun_satirlari, sonuclar)

    ozet = {"tarih": tarih}
    if not any(s["tarih"] == tarih for s in satirlar):
        adaylar = adaylari_bul(son_iyms_oranlari(simdi), depo.maclari_oku(), simdi)
        yeni = kupon_olustur(tarih, adaylar)
        satirlar += yeni
        ozet["aday"] = len(adaylar)
        ozet["kupon"] = yeni[0]["durum"]
        depo.json_yaz(depo.kok() / "adaylar" / f"{tarih}.json", adaylar)
    depo.csv_yaz(kupon_yolu(), satirlar, KUPON_ALANLARI)
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("özet: %s", calistir())


if __name__ == "__main__":
    main()
