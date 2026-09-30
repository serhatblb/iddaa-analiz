"""Mackolik arşivi: 2019 sonbaharından bu yana iddaa bültenindeki bitmiş futbol maçları.

Kaynak, sonuçlar için de kullanılan günlük veri: `vd.mackolik.com/livedata?date=GG/AA/YYYY`. Bitmiş her maç için
İY ve MS (90 dk) skoru, lig, takım numaraları, iddaa maç numarası ve Mackolik'in gösterdiği iddaa oranları
(MS 1/0/2 ile 2.5 Alt/Üst) alınır.

Oranlar iddaa sitesindeki kapanış oranlarının yaklaşık 0.96 katı (Mackolik'in gösterimi). Analizde olasılıklar
kâr payı ayıklanarak (oranlar normalize edilerek) kullanıldığı için bu ölçek farkı sadeleşir.

Dosyalar aylık: data/arsiv/YYYY-MM.csv.gz. Biten aylar bir kez indirilir, son ay her çalışmada yenilenir.
"""
import argparse
import csv
import gzip
import io
import logging
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import config, depo, sonuc

log = logging.getLogger("arsiv")

ILK_GUN = date(2019, 1, 1)
BITTI = {4, 6, 8}
ALANLAR = ["tarih", "saat", "mk_id", "iddaa_id", "ulke_id", "ulke", "lig_id", "lig", "lig_kodu", "sezon",
           "ev_id", "ev", "dep_id", "dep", "durum", "iy_ev", "iy_dep", "ms_ev", "ms_dep",
           "o1", "o0", "o2", "alt25", "ust25"]
ORAN_ALANLARI = ["o1", "o0", "o2", "alt25", "ust25"]


def dizin():
    return depo.kok() / "arsiv"


def _tam(deger) -> int | None:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return None


def _oran(deger) -> str:
    try:
        sayi = float(str(deger).strip())
    except (TypeError, ValueError):
        return ""
    return f"{sayi:.2f}" if sayi >= 1.0 else ""


def satir_kaydi(s: list) -> dict | None:
    """Bitmiş, iddaa'da olan futbol maçı satırını kayda çevirir; diğerleri için None."""
    try:
        lig = s[36]
        if len(s) < 37 or not isinstance(lig, list) or len(lig) < 12 or lig[11] != 1:
            return None
        durum = _tam(s[5])
        if durum not in BITTI:
            return None
        oranlar = [_oran(s[i]) for i in range(18, 23)]
        iddaa_id = _tam(s[14]) or 0
        if not iddaa_id and not oranlar[0]:
            return None
        skor = [_tam(s[i]) for i in (31, 32, 29, 30)]
        if any(x is None for x in skor):
            return None
        gun, ay, yil = str(s[35]).split("/")
        kayit = {"tarih": f"{yil}-{ay}-{gun}", "saat": s[16], "mk_id": s[0], "iddaa_id": iddaa_id or "",
                 "ulke_id": lig[0], "ulke": lig[1], "lig_id": lig[2], "lig": lig[3], "lig_kodu": lig[9],
                 "sezon": lig[5], "ev_id": s[1], "ev": s[2], "dep_id": s[3], "dep": s[4], "durum": durum,
                 "iy_ev": skor[0], "iy_dep": skor[1], "ms_ev": skor[2], "ms_dep": skor[3]}
        kayit.update(zip(ORAN_ALANLARI, oranlar))
        return kayit
    except (IndexError, TypeError, ValueError):
        return None


def gun_indir(gun: date, oturum: requests.Session, deneme: int = 3) -> list[dict] | None:
    for sira in range(deneme):
        try:
            satirlar = sonuc.gunluk_veri(gun.strftime("%d/%m/%Y"), oturum)
            return [k for k in (satir_kaydi(s) for s in satirlar) if k]
        except sonuc.SonucHatasi as hata:
            log.warning("%s alınamadı (%d): %s", gun, sira + 1, hata)
            time.sleep(5 * (sira + 1))
    return None


def _yaz(yol, satirlar: list[dict]) -> None:
    """Boş ay da (sadece başlık) yazılır ki tekrar indirilmesin; mtime=0 ile aynı içerik aynı bayt."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    tampon = io.StringIO()
    yazici = csv.DictWriter(tampon, fieldnames=ALANLAR, extrasaction="ignore")
    yazici.writeheader()
    yazici.writerows(satirlar)
    with open(yol, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(tampon.getvalue().encode("utf-8"))


def aylar(baslangic: date, bitis: date) -> list[tuple[int, int]]:
    liste, yil, ay = [], baslangic.year, baslangic.month
    while (yil, ay) <= (bitis.year, bitis.month):
        liste.append((yil, ay))
        yil, ay = (yil + 1, 1) if ay == 12 else (yil, ay + 1)
    return liste


def calistir(baslangic: date = ILK_GUN, bitis: date | None = None, bekleme: float = 0.8,
             getir=gun_indir) -> dict:
    """baslangic..bitis (dahil) arası ayları indirir. Bitmiş ve dosyası olan aylar atlanır."""
    bugun = datetime.now(timezone.utc).astimezone(config.TR).date()
    bitis = min(bitis or bugun - timedelta(days=1), bugun - timedelta(days=1))
    oturum = requests.Session()
    ozet = {"ay": 0, "atlanan": 0, "mac": 0, "eksik_gun": 0}
    for yil, ay in aylar(baslangic, bitis):
        yol = dizin() / f"{yil}-{ay:02d}.csv.gz"
        ay_sonu = (date(yil + (ay == 12), ay % 12 + 1, 1) - timedelta(days=1))
        # Ay bitmiş ve üstünden 3 gün geçmişse (gece yarısını geçen maçlar dahil) bir kez indirmek yeter
        if yol.exists() and ay_sonu + timedelta(days=3) < bugun:
            ozet["atlanan"] += 1
            continue
        satirlar, eksik = {}, 0
        gun = max(date(yil, ay, 1), baslangic)
        while gun <= min(ay_sonu, bitis):
            gunluk = getir(gun, oturum)
            if gunluk is None:
                eksik += 1
            else:
                for k in gunluk:
                    satirlar[k["mk_id"]] = k
            gun += timedelta(days=1)
            if bekleme:
                time.sleep(bekleme)
        if eksik:
            # Eksik günlü ay yazılmaz; bir sonraki çalışmada baştan denenir
            log.warning("%d-%02d: %d gün alınamadı, ay yazılmadı", yil, ay, eksik)
            ozet["eksik_gun"] += eksik
            continue
        liste = sorted(satirlar.values(), key=lambda k: (k["tarih"], k["saat"], int(k["mk_id"])))
        _yaz(yol, liste)
        ozet["ay"] += 1
        ozet["mac"] += len(liste)
        log.info("%d-%02d: %d maç", yil, ay, len(liste))
    return ozet


def oku(baslangic: str = "", bitis: str = "9999") -> list[dict]:
    """Arşiv maçları; skorlar tamsayı, oranlar float (yoksa None)."""
    maclar = []
    for yol in sorted(dizin().glob("*.csv.gz")):
        if not (baslangic[:7] <= yol.name[:7] <= bitis[:7]):
            continue
        for s in depo.gz_csv_oku(yol):
            for k in ("iy_ev", "iy_dep", "ms_ev", "ms_dep"):
                s[k] = int(s[k])
            for k in ORAN_ALANLARI:
                s[k] = float(s[k]) if s[k] else None
            maclar.append(s)
    return maclar


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Mackolik arşivini indirir")
    ap.add_argument("--baslangic", default=ILK_GUN.isoformat())
    ap.add_argument("--bitis", default="")
    ap.add_argument("--bekleme", type=float, default=0.8)
    args = ap.parse_args()
    ozet = calistir(date.fromisoformat(args.baslangic),
                    date.fromisoformat(args.bitis) if args.bitis else None, args.bekleme)
    log.info("özet: %s", ozet)


if __name__ == "__main__":
    main()
