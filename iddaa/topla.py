"""Saatlik toplayıcı: bülten, oranlar, en çok oynananlar.

Kurallar:
- Maç ilk kez görülünce tüm maç önü marketler 'acilis' olarak kaydedilir.
- İY/MS'si olan maçların İY/MS oranları her çalışmada 'saatlik' olarak kaydedilir.
- Başlamaya 75 dakika kala tüm marketler bir kez 'kapanis' olarak kaydedilir.
- İY/MS'si olmayan yakın maçlar 6 saatte bir tekrar kontrol edilir (market sonradan açılabilir).
"""
import logging
import sys
from datetime import datetime, timedelta, timezone

from . import config, depo
from .api import EngellendiHatasi, IddaaHatasi, IddaaIstemci
from .bulten import (baslama, iso, iso_oku, iyms_var, lig_satirlari, mac_oynanma_satirlari,
                     oran_satirlari, secenek_oynanma_satirlari)

log = logging.getLogger("topla")


def _ayarlari_tazele(istemci: IddaaIstemci, simdi: datetime) -> dict[str, dict]:
    """Market isimleri ve ligler günde bir tazelenir. Lig sözlüğünü döner."""
    kok = depo.kok()
    ayar_yolu = kok / "market_ayarlari.json"
    lig_yolu = kok / "ligler.csv"
    damga_yolu = kok / "ayar_zamani.txt"
    damga = damga_yolu.read_text().strip() if damga_yolu.exists() else ""
    if not damga or simdi - iso_oku(damga) > timedelta(hours=24) or not lig_yolu.exists():
        ayarlar = istemci.market_ayarlari() or {}
        isimler = {k: v.get("n", "") for k, v in (ayarlar.get("m") or {}).items()}
        depo.json_yaz(ayar_yolu, isimler)
        mevcut = {s["lig_id"]: s for s in depo.csv_oku(lig_yolu)}
        for lig in lig_satirlari(istemci.ligler()):
            mevcut[str(lig["lig_id"])] = {k: str(v) for k, v in lig.items()}
        depo.csv_yaz(lig_yolu, sorted(mevcut.values(), key=lambda s: int(s["lig_id"])), depo.LIG_ALANLARI)
        damga_yolu.write_text(iso(simdi))
    return {s["lig_id"]: s for s in depo.csv_oku(lig_yolu)}


def detay_gerekli_mi(kayit: dict | None, liste_iyms: bool, bas: datetime, simdi: datetime) -> str | None:
    """Maç için detay çekilmeli mi, çekilecekse anlık tipi ne olmalı?"""
    if kayit is None or kayit.get("acilis") != "1":
        return "acilis"
    if kayit.get("kapanis") != "1" and bas - simdi <= config.KAPANIS_ONCESI:
        return "kapanis"
    if kayit.get("iyms_var") == "1" or liste_iyms:
        return "saatlik"
    if bas - simdi <= config.IYMS_KONTROL_UFKU:
        son = kayit.get("son_detay_utc")
        if not son or simdi - iso_oku(son) >= config.IYMS_TEKRAR_KONTROL:
            return "kontrol"
    return None


def calistir(istemci: IddaaIstemci | None = None, simdi: datetime | None = None) -> dict:
    istemci = istemci or IddaaIstemci()
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    ligler = _ayarlari_tazele(istemci, simdi)
    kayitlar = depo.maclari_oku()
    degisenler: set[str] = set()
    oran_satirlari_tum: list[dict] = []
    ozet = {"bulten": 0, "detay": 0, "iyms_mac": 0, "yeni": 0, "kapanis": 0, "hata": 0}

    bulten = istemci.bulten() or {}
    maclar = [m for m in bulten.get("events") or [] if not m.get("il")]
    ozet["bulten"] = len(maclar)

    for mac in maclar:
        mac_id = str(mac["i"])
        bas = baslama(mac)
        if bas <= simdi:
            continue
        kayit = kayitlar.get(mac_id)
        tip = detay_gerekli_mi(kayit, iyms_var(mac), bas, simdi)
        if tip is None:
            continue
        try:
            detay = istemci.mac(mac["i"])
        except EngellendiHatasi:
            raise
        except IddaaHatasi as hata:
            log.warning("maç %s detayı alınamadı: %s", mac_id, hata)
            ozet["hata"] += 1
            continue
        if not detay:
            continue
        ozet["detay"] += 1
        detay_iyms = iyms_var(detay)

        if tip in ("acilis", "kapanis"):
            oran_satirlari_tum += oran_satirlari(detay, tip, simdi)
        elif detay_iyms:
            oran_satirlari_tum += oran_satirlari(detay, "saatlik", simdi, sadece={config.IYMS})

        lig = ligler.get(str(mac.get("ci")), {})
        yeni_kayit = dict(kayit or {})
        yeni_kayit.update({
            "mac_id": mac_id,
            "lig_id": mac.get("ci", ""),
            "lig": lig.get("ad", yeni_kayit.get("lig", "")),
            "ulke": lig.get("ulke", yeni_kayit.get("ulke", "")),
            "ev": mac.get("hn", ""),
            "dep": mac.get("an", ""),
            "baslama_utc": iso(bas),
            "ilk_gorulme_utc": yeni_kayit.get("ilk_gorulme_utc") or iso(simdi),
            "acilis": "1",
            "kapanis": "1" if tip == "kapanis" or yeni_kayit.get("kapanis") == "1"
                       or (tip == "acilis" and bas - simdi <= config.KAPANIS_ONCESI) else "0",
            "iyms_var": "1" if detay_iyms or yeni_kayit.get("iyms_var") == "1" else "0",
            "son_detay_utc": iso(simdi),
        })
        if tip == "acilis":
            ozet["yeni"] += 1
        if tip == "kapanis":
            ozet["kapanis"] += 1
        if detay_iyms:
            ozet["iyms_mac"] += 1
        kayitlar[mac_id] = yeni_kayit
        degisenler.add(mac_id)

    depo.gz_csv_yaz(depo.anlik_yolu("oranlar", simdi), oran_satirlari_tum, depo.ORAN_ALANLARI)
    depo.maclari_yaz(kayitlar, degisenler)

    # En çok oynananlar: sadece başlamamış, takip edilen maçlar
    takip = {m for m, k in kayitlar.items() if iso_oku(k["baslama_utc"]) > simdi}
    try:
        secenek = secenek_oynanma_satirlari(istemci.secenek_oynanma(), takip, simdi)
        mac_pay = mac_oynanma_satirlari(istemci.mac_oynanma(), takip, simdi)
        depo.gz_csv_yaz(depo.anlik_yolu("oynanma/secenek", simdi), secenek, depo.SECENEK_OYNANMA_ALANLARI)
        depo.gz_csv_yaz(depo.anlik_yolu("oynanma/mac", simdi), mac_pay, depo.MAC_OYNANMA_ALANLARI)
        ozet["oynanma"] = len(secenek)
    except IddaaHatasi as hata:
        log.warning("oynanma yüzdeleri alınamadı: %s", hata)

    ozet["oran_satiri"] = len(oran_satirlari_tum)
    ozet["istek"] = istemci.istek_sayisi
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        ozet = calistir()
    except EngellendiHatasi as hata:
        log.error("iddaa erişimi engelledi: %s", hata)
        sys.exit(2)
    log.info("özet: %s", ozet)


if __name__ == "__main__":
    main()
