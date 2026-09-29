"""Biten maçların İY ve MS (90 dakika) skorlarını yazar.

Kaynak: Mackolik'in günlük canlı sonuç verisi (`vd.mackolik.com/livedata?date=GG/AA/YYYY`).
Her satırda iddaa maç kimliği de bulunur, böylece maçlar doğrudan eşleşir. iddaa'nın kendi
servislerinde biten maçın skoru tutulmuyor: `recent-matches` maç öncesi bir anlık görüntü,
canlı akış ise maç biter bitmez skoru siliyor ve canlı yayınlanmayan maçları hiç göstermiyor.

Mackolik satır alanları (futbol):
  [5] durum kodu: 0 başlamadı, 1 ilk yarı, 2 devre arası, 3 ikinci yarı, 4 maç sonu,
      6 uzatmalar sonrası, 8 penaltılar sonrası, 9 ertelendi, 10 hükmen, 11 yarıda kaldı
  [2]/[4] ev/deplasman adı, [14] iddaa maç kimliği, [16] başlama saati (TR),
  [29]/[30] normal süre (90 dk) skoru, [31]/[32] ilk yarı skoru, [35] tarih, [36][11] spor (1 = futbol)
"""
import logging
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

from . import config, depo
from .bulten import iso, iso_oku

log = logging.getLogger("sonuc")

KAYNAK = "https://vd.mackolik.com/livedata"
BITTI = {4, 6, 8}                 # 90 dakika tamamlandı (uzatma/penaltı dahil)
IPTAL = {9: "ertelendi", 10: "hükmen", 11: "yarıda kaldı"}
ISIM_ESLESME_PENCERESI = timedelta(minutes=20)


class SonucHatasi(Exception):
    pass


def gunluk_veri(tarih: str, oturum: requests.Session | None = None) -> list[list]:
    """tarih: 'GG/AA/YYYY' (Türkiye günü). Satır listesi döner."""
    oturum = oturum or requests.Session()
    try:
        yanit = oturum.get(KAYNAK, params={"date": tarih}, timeout=30,
                           headers={"User-Agent": "Mozilla/5.0 (compatible; iddaa-analiz personal research)",
                                    "Referer": "https://arsiv.mackolik.com/Canli-Sonuclar"})
        yanit.raise_for_status()
        return yanit.json().get("m") or []
    except (requests.RequestException, ValueError) as hata:
        raise SonucHatasi(f"{tarih}: {hata}") from hata


def _tam(deger) -> int | None:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return None


def _normal(ad: str) -> str:
    ad = (ad or "").replace("İ", "i").replace("I", "ı").casefold()
    ad = unicodedata.normalize("NFKD", ad)
    return "".join(c for c in ad if c.isalnum())


def satiri_coz(satir: list) -> dict | None:
    """Futbol satırını sözlüğe çevirir; futbol değilse None."""
    try:
        if len(satir) < 37 or not isinstance(satir[36], list) or satir[36][11] != 1:
            return None
        return {"iddaa_id": str(satir[14] or ""), "durum": _tam(satir[5]), "durum_metni": str(satir[6] or ""),
                "ev": satir[2], "dep": satir[4], "saat": str(satir[16] or ""), "tarih": str(satir[35] or ""),
                "ms_ev": _tam(satir[29]), "ms_dep": _tam(satir[30]),
                "iy_ev": _tam(satir[31]), "iy_dep": _tam(satir[32])}
    except (IndexError, TypeError):
        return None


def sonuca_cevir(mac: dict) -> dict | None:
    """Bitmiş veya iptal edilmiş maç için sonuç kaydı; devam ediyorsa None."""
    if mac["durum"] in BITTI:
        skorlar = (mac["iy_ev"], mac["iy_dep"], mac["ms_ev"], mac["ms_dep"])
        if any(s is None for s in skorlar):
            return None
        return {"iy_ev": skorlar[0], "iy_dep": skorlar[1], "ms_ev": skorlar[2], "ms_dep": skorlar[3],
                "durum": "tamam", "kaynak": "mackolik" + ("" if mac["durum"] == 4 else f"-{mac['durum_metni']}")}
    if mac["durum"] in IPTAL:
        return {"iy_ev": "", "iy_dep": "", "ms_ev": "", "ms_dep": "", "durum": "iptal",
                "kaynak": f"mackolik-{IPTAL[mac['durum']]}"}
    return None


def tr_tarih(zaman: datetime) -> str:
    return zaman.astimezone(config.TR).strftime("%d/%m/%Y")


def bekleyenler(kayitlar: dict, sonuclar: dict, simdi: datetime) -> list[dict]:
    liste = []
    for mac_id, kayit in kayitlar.items():
        if not kayit.get("ev"):
            continue
        bas = iso_oku(kayit["baslama_utc"])
        if simdi - bas < timedelta(minutes=100) or simdi - bas > config.SONUC_ARAMA_UFKU:
            continue
        if (sonuclar.get(mac_id) or {}).get("durum") in ("tamam", "iptal"):
            continue
        liste.append(kayit)
    return sorted(liste, key=lambda k: k["baslama_utc"])


def eslestir(kayit: dict, idye_gore: dict, gunluk: list[dict]) -> dict | None:
    mac = idye_gore.get(kayit["mac_id"])
    if mac:
        return mac
    # Kimlik yoksa: aynı gün, başlama saati yakın ve iki takım adı da tutan tek maç
    bas = iso_oku(kayit["baslama_utc"]).astimezone(config.TR)
    ev, dep = _normal(kayit["ev"]), _normal(kayit["dep"])
    adaylar = []
    for m in gunluk:
        try:
            saat, dakika = (int(x) for x in m["saat"].split(":"))
            gun, ay, yil = (int(x) for x in m["tarih"].split("/"))
        except ValueError:
            continue
        zaman = datetime(yil, ay, gun, saat, dakika, tzinfo=config.TR)
        if abs(zaman - bas) > ISIM_ESLESME_PENCERESI:
            continue
        if _normal(m["ev"]) == ev and _normal(m["dep"]) == dep:
            adaylar.append(m)
    return adaylar[0] if len(adaylar) == 1 else None


def calistir(simdi: datetime | None = None, veri_getir=gunluk_veri) -> dict:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()
    liste = bekleyenler(kayitlar, sonuclar, simdi)
    ozet = {"bekleyen": len(liste), "bulunan": 0, "iptal": 0, "belirsiz": 0, "devam": 0, "gun": 0}
    if not liste:
        return ozet

    # Gece yarısına yakın maçlar için başlama gününün bir öncesi ve sonrası da okunur
    tarihler = set()
    for k in liste:
        bas = iso_oku(k["baslama_utc"])
        for fark in (-1, 0, 1):
            gun = bas + timedelta(days=fark)
            if gun <= simdi + timedelta(hours=1):
                tarihler.add(tr_tarih(gun))
    gunluk: list[dict] = []
    for tarih in sorted(tarihler, key=lambda t: t[6:] + t[3:5] + t[:2]):
        try:
            satirlar = veri_getir(tarih)
        except SonucHatasi as hata:
            log.warning("sonuç verisi alınamadı: %s", hata)
            continue
        gunluk += [m for m in (satiri_coz(s) for s in satirlar) if m]
        ozet["gun"] += 1
    idye_gore = {m["iddaa_id"]: m for m in gunluk if m["iddaa_id"] and m["iddaa_id"] != "0"}

    degisenler: set[str] = set()
    for kayit in liste:
        mac_id = kayit["mac_id"]
        mac = eslestir(kayit, idye_gore, gunluk)
        sonuc = sonuca_cevir(mac) if mac else None
        if sonuc:
            sonuclar[mac_id] = {"mac_id": mac_id, **sonuc, "guncelleme_utc": iso(simdi)}
            ozet["iptal" if sonuc["durum"] == "iptal" else "bulunan"] += 1
            degisenler.add(mac_id)
        elif simdi - iso_oku(kayit["baslama_utc"]) > config.IPTAL_SURESI:
            sonuclar[mac_id] = {"mac_id": mac_id, "iy_ev": "", "iy_dep": "", "ms_ev": "", "ms_dep": "",
                                "durum": "belirsiz", "kaynak": "sonuc-bulunamadi", "guncelleme_utc": iso(simdi)}
            ozet["belirsiz"] += 1
            degisenler.add(mac_id)
        else:
            ozet["devam"] += 1

    if degisenler:
        depo.sonuclari_yaz(sonuclar, kayitlar, degisenler)
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ozet = calistir()
    log.info("özet: %s", ozet)
    if ozet["bekleyen"] and not ozet["gun"]:
        log.error("Sonuç kaynağına hiç ulaşılamadı.")
        sys.exit(2)


if __name__ == "__main__":
    main()
