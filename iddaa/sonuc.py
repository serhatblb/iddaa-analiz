"""Biten maçların İY ve MS skorlarını yazar.

Kaynak: statisticsv2 `recent-matches/{maçId}`. Yanıtta ev sahibinin son maçları İY (fhs) ve
normal süre (rs) skorlarıyla gelir; biten maçın kendisi başlama zamanı ve takım adlarıyla eşleştirilir.
"""
import logging
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

from . import config, depo
from .api import EngellendiHatasi, IddaaHatasi, IddaaIstemci
from .bulten import iso, iso_oku

log = logging.getLogger("sonuc")
AZAMI_ISTEK = 400
ESLESME_PENCERESI = 3 * 3600  # saniye
TEKRAR_DENEME = timedelta(hours=3)


def _normal(ad: str) -> str:
    ad = (ad or "").replace("İ", "i").replace("I", "ı").casefold()
    ad = unicodedata.normalize("NFKD", ad)
    return "".join(c for c in ad if c.isalnum())


def sonucu_bul(veri: dict | None, kayit: dict) -> tuple[int, int, int, int] | None:
    """recent-matches yanıtında maçı bulur: (iy_ev, iy_dep, ms_ev, ms_dep)."""
    if not veri:
        return None
    bas = int(iso_oku(kayit["baslama_utc"]).timestamp())
    ev, dep = _normal(kayit["ev"]), _normal(kayit["dep"])
    adaylar = []
    for mac in veri.get("m") or []:
        t = mac.get("t")
        h, a = mac.get("h") or {}, mac.get("a") or {}
        if t is None or abs(int(t) - bas) > ESLESME_PENCERESI:
            continue
        skor = (h.get("fhs"), a.get("fhs"), h.get("rs"), a.get("rs"))
        if any(s is None for s in skor):
            continue
        skor = tuple(int(s) for s in skor)
        if _normal(h.get("n")) == ev and _normal(a.get("n")) == dep:
            return skor
        if _normal(h.get("n")) == ev or _normal(a.get("n")) == dep:
            adaylar.append(skor)
    # İsim yazımı farklıysa: zaman penceresinde ve bir takımı tutan tek aday varsa kabul et
    return adaylar[0] if len(adaylar) == 1 else None


def bekleyenler(kayitlar: dict, sonuclar: dict, simdi: datetime) -> list[dict]:
    liste = []
    for mac_id, kayit in kayitlar.items():
        bas = iso_oku(kayit["baslama_utc"])
        if simdi - bas < config.SONUC_BEKLEME or simdi - bas > config.SONUC_ARAMA_UFKU:
            continue
        mevcut = sonuclar.get(mac_id)
        if mevcut and mevcut.get("durum") in ("tamam", "iptal"):
            continue
        if mevcut and mevcut.get("durum") == "bekliyor" and \
                simdi - iso_oku(mevcut["guncelleme_utc"]) < TEKRAR_DENEME:
            continue
        liste.append(kayit)
    return sorted(liste, key=lambda k: k["baslama_utc"])


def calistir(istemci: IddaaIstemci | None = None, simdi: datetime | None = None) -> dict:
    istemci = istemci or IddaaIstemci()
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()
    degisenler: set[str] = set()
    ozet = {"bekleyen": 0, "bulunan": 0, "iptal": 0, "bulunamayan": 0}

    liste = bekleyenler(kayitlar, sonuclar, simdi)
    ozet["bekleyen"] = len(liste)
    for kayit in liste[:AZAMI_ISTEK]:
        mac_id = kayit["mac_id"]
        try:
            veri = istemci.son_maclar(int(mac_id))
        except EngellendiHatasi:
            raise
        except IddaaHatasi as hata:
            log.warning("maç %s sonucu alınamadı: %s", mac_id, hata)
            veri = None
        skor = sonucu_bul(veri, kayit)
        if skor:
            sonuclar[mac_id] = {"mac_id": mac_id, "iy_ev": skor[0], "iy_dep": skor[1],
                                "ms_ev": skor[2], "ms_dep": skor[3], "durum": "tamam",
                                "kaynak": "recent-matches", "guncelleme_utc": iso(simdi)}
            degisenler.add(mac_id)
            ozet["bulunan"] += 1
        elif simdi - iso_oku(kayit["baslama_utc"]) > config.IPTAL_SURESI:
            sonuclar[mac_id] = {"mac_id": mac_id, "iy_ev": "", "iy_dep": "", "ms_ev": "", "ms_dep": "",
                                "durum": "iptal", "kaynak": "sonuc-yok", "guncelleme_utc": iso(simdi)}
            degisenler.add(mac_id)
            ozet["iptal"] += 1
        else:
            sonuclar[mac_id] = {"mac_id": mac_id, "iy_ev": "", "iy_dep": "", "ms_ev": "", "ms_dep": "",
                                "durum": "bekliyor", "kaynak": "", "guncelleme_utc": iso(simdi)}
            degisenler.add(mac_id)
            ozet["bulunamayan"] += 1

    if degisenler:
        depo.sonuclari_yaz(sonuclar, kayitlar, degisenler)
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
