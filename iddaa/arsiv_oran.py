"""Geçmiş maçların bütün önemli iddaa oranları: Mackolik maç sayfalarından.

Mackolik'in arşiv maç sayfası (arsiv.mackolik.com/Match/Default.aspx?id=<mk_id>) maçın iddaa marketlerini son
(kapanış) oranları ve MBS'leriyle gösterir. Buradan İY/MS, toplam gol aralığı, karşılıklı gol, ilk yarı sonucu,
1.5/2.5/3.5 alt/üst ve çifte şans oranları alınır; skorlar ve lig `arsiv.py` dosyalarından gelir (mk_id ile).

Oranlar Mackolik'in gösterdiği standart iddaa oranlarıdır (iddaa.com'daki Kral Oran bunların ~1.04 katı).
Dosyalar: data/arsiv_oran/YYYY-MM.csv.gz, maç başına bir satır. Sayfada iddaa bölümü yoksa satır boş oranlarla
yazılır ki tekrar istenmesin.

İY/MS sadece büyük liglerde açılıyor ve sayfalar yavaş. Bu yüzden öncelik sırası (lig = Mackolik lig anahtarı):
  0) İY/MS'si olduğu bilinen ligler (indirilen sayfaların en az %30'unda İY/MS var),
  1) henüz tanınmayan ligler: her birinden en yeni 3 maç (lig sınıflandırılsın diye),
  2) İY/MS'siz ligler (en az 3 sayfada hiç yok): sadece `hepsi=True` ile.
"""
import argparse
import html
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import requests

from . import arsiv, config, depo
from .sonuc import lig_anahtari

log = logging.getLogger("arsiv_oran")

SAYFA = "https://arsiv.mackolik.com/Match/Default.aspx"
BASLIK = {"User-Agent": "Mozilla/5.0 (compatible; iddaa-analiz personal research)",
          "Referer": "https://arsiv.mackolik.com/Canli-Sonuclar"}

# Sayfadaki market adı -> (sütun öneki, {sayfadaki seçenek adı: sütun soneki})
MARKETLER = {
    "Maç Sonucu": ("ms", {"1": "1", "X": "0", "2": "2"}),
    "İlk Yarı/Maç Sonucu": ("iyms", {"1/1": "11", "1/X": "10", "1/2": "12", "X/1": "01", "X/X": "00", "X/2": "02",
                                     "2/1": "21", "2/X": "20", "2/2": "22"}),
    "Toplam Gol Aralığı": ("tg", {"0-1 Gol": "01", "2-3 Gol": "23", "4-5 Gol": "45", "6+ Gol": "6"}),
    "Karşılıklı Gol": ("kg", {"Var": "var", "Yok": "yok"}),
    "1. Yarı Sonucu": ("iy", {"1": "1", "X": "0", "2": "2"}),
    "1,5 Alt/Üst": ("au15", {"Alt": "alt", "Üst": "ust"}),
    "2,5 Alt/Üst": ("au25", {"Alt": "alt", "Üst": "ust"}),
    "3,5 Alt/Üst": ("au35", {"Alt": "alt", "Üst": "ust"}),
    "Çifte Şans": ("cs", {"1-X": "1x", "1-2": "12", "X-2": "x2"}),
}
ORAN_SUTUNLARI = [f"{onek}_{son}" for onek, secenekler in MARKETLER.values() for son in secenekler.values()]
MBS_SUTUNLARI = [f"{onek}_mbs" for onek, _ in MARKETLER.values()]
ALANLAR = ["mk_id", "iddaa_id", "market_sayisi"] + ORAN_SUTUNLARI + MBS_SUTUNLARI

_DIYALOG = re.compile(r"openOddsDialog\('\d+',\s*'([^']*)',\s*\[([^\]]*)\],\s*\[([^\]]*)\],\s*'[^']*',\s*'[^']*',"
                      r"\s*'(\d*)',\s*'(\d+)'")
_MBS = re.compile(r'class="detail-title"[^>]*>\s*([^<]+?)\s*<span[^>]*>[^<]*<img[^>]*mbs(\d)\.png')


def _liste(metin: str) -> list[str]:
    return [html.unescape(x.strip().strip("'")) for x in metin.split(",")]


def _oran(metin: str) -> str:
    try:
        sayi = float(metin)
    except ValueError:
        return ""
    return f"{sayi:.2f}" if sayi >= 1.0 else ""


def sayfayi_coz(sayfa: str, mk_id) -> dict:
    """Maç sayfasından seçili marketlerin oranlarını ve MBS'lerini çıkarır."""
    kayit = {"mk_id": mk_id, "iddaa_id": "", "market_sayisi": 0}
    goruldu = set()
    for ad, adlar, oranlar, iddaa_id, market_no in _DIYALOG.findall(sayfa):
        if market_no in goruldu:
            continue
        goruldu.add(market_no)
        kayit["iddaa_id"] = kayit["iddaa_id"] or iddaa_id
        ad = html.unescape(ad).strip()
        if ad not in MARKETLER:
            continue
        onek, secenekler = MARKETLER[ad]
        for secenek, oran in zip(_liste(adlar), _liste(oranlar)):
            if secenek in secenekler:
                kayit[f"{onek}_{secenekler[secenek]}"] = _oran(oran)
    kayit["market_sayisi"] = len(goruldu)
    for ad, mbs in _MBS.findall(sayfa):
        ad = html.unescape(ad).strip()
        if ad in MARKETLER:
            kayit.setdefault(f"{MARKETLER[ad][0]}_mbs", mbs)
    return kayit


class Engellendi(Exception):
    pass


def sayfa_getir(mk_id, oturum: requests.Session) -> str | None:
    for deneme in range(3):
        try:
            yanit = oturum.get(SAYFA, params={"id": mk_id}, headers=BASLIK, timeout=45)
        except requests.RequestException as hata:
            log.warning("%s: %s", mk_id, hata)
            time.sleep(3 * (deneme + 1))
            continue
        if yanit.status_code in (403, 429):
            raise Engellendi(f"HTTP {yanit.status_code}")
        if yanit.status_code == 200:
            return yanit.text
        if yanit.status_code == 404:
            return ""  # sayfa yok: oransız kayıt olarak yazılır, bir daha istenmez
        if deneme < 2:
            time.sleep(2 * (deneme + 1))  # 502 sık geliyor: kısa bekleyip yeniden dene
    return None


def dizin():
    return depo.kok() / "arsiv_oran"


def mevcut_idler() -> set[str]:
    return {s["mk_id"] for yol in dizin().glob("*.csv.gz") for s in depo.gz_csv_oku(yol)}


def _ay_yaz(ay: str, yeni: list[dict]) -> None:
    yol = dizin() / f"{ay}.csv.gz"
    satirlar = {s["mk_id"]: s for s in (depo.gz_csv_oku(yol) if yol.exists() else [])}
    satirlar.update({str(s["mk_id"]): s for s in yeni})
    depo.gz_csv_yaz(yol, sorted(satirlar.values(), key=lambda s: int(s["mk_id"])), ALANLAR)


ORNEK_SAYISI = 3        # tanınmayan ligden sınıflandırma için indirilen maç
IYMS_ORANI_ESIGI = 0.3


def _lig(m: dict) -> str:
    return lig_anahtari(m["ulke"], m.get("lig_kodu") or m["lig"])


def lig_istatistikleri(maclar: list[dict]) -> dict[str, list[int]]:
    """{lig: [indirilen sayfa, İY/MS'li sayfa]} (bütün aylar)."""
    lig_of = {m["mk_id"]: _lig(m) for m in maclar}
    istat: dict[str, list[int]] = {}
    for yol in dizin().glob("*.csv.gz"):
        for s in depo.gz_csv_oku(yol):
            lig = lig_of.get(s["mk_id"])
            if lig is None:
                continue
            t = istat.setdefault(lig, [0, 0])
            t[0] += 1
            t[1] += bool(s.get("iyms_11"))
    return istat


def oncelikli_adaylar(adaylar: list[dict], istat: dict[str, list[int]], hepsi: bool = False) -> list[dict]:
    """Adayları öncelik sırasına dizer (bkz. modül açıklaması); her öncelikte en yeniden eskiye."""
    adaylar = sorted(adaylar, key=lambda m: (m["tarih"], m["saat"]), reverse=True)
    sirali: list[list[dict]] = [[], [], []]
    ornek: dict[str, int] = {}
    for m in adaylar:
        lig = _lig(m)
        n, iyms = istat.get(lig, (0, 0))
        if n >= ORNEK_SAYISI:
            sirali[0 if iyms / n >= IYMS_ORANI_ESIGI else 2].append(m)
        elif ornek.get(lig, n) < ORNEK_SAYISI:
            ornek[lig] = ornek.get(lig, n) + 1
            sirali[1].append(m)
        else:
            sirali[2].append(m)  # örneği tamamlanınca bir sonraki çalışmada sınıflanır
    return sirali[0] + sirali[1] + (sirali[2] if hepsi else [])


PARTI = 200


def calistir(baslangic: str = "2019-01-01", bitis: str = "9999-12-31", sure_dk: float = 300, is_parcacigi: int = 2,
             bekleme: float = 0.4, getir=sayfa_getir, hepsi: bool = False) -> dict:
    """Arşivdeki iddaa maçlarının sayfalarını öncelik sırasıyla indirir; süre dolunca durur.
    Öncelikler her partiden sonra yeniden hesaplanır: örneklenen lig hemen sınıflanır."""
    son_zaman = time.monotonic() + sure_dk * 60
    mevcut = mevcut_idler()
    tum = arsiv.oku()
    kalan = {m["mk_id"]: m for m in tum
             if baslangic <= m["tarih"] <= bitis and m["mk_id"] not in mevcut and m["iddaa_id"] and m["o1"]}
    istat = lig_istatistikleri(tum)
    ozet = {"aday": len(oncelikli_adaylar(list(kalan.values()), istat, hepsi)), "indirilen": 0, "iddaasiz": 0,
            "hata": 0, "durdu": ""}
    kilit = threading.Lock()
    biriken: dict[str, list[dict]] = {}
    dur = threading.Event()
    yerel = threading.local()

    def is_(mac):
        if dur.is_set() or time.monotonic() > son_zaman:
            dur.set()
            return
        if not hasattr(yerel, "oturum"):
            yerel.oturum = requests.Session()
        try:
            sayfa = getir(mac["mk_id"], yerel.oturum)
        except Engellendi as hata:
            ozet["durdu"] = str(hata)
            dur.set()
            return
        with kilit:
            kalan.pop(mac["mk_id"], None)  # hatalı sayfa bir sonraki çalışmada yeniden denenir
            if sayfa is None:
                ozet["hata"] += 1
                return
            kayit = sayfayi_coz(sayfa, mac["mk_id"])
            kayit["iddaa_id"] = kayit["iddaa_id"] or mac["iddaa_id"]
            biriken.setdefault(mac["tarih"][:7], []).append(kayit)
            t = istat.setdefault(_lig(mac), [0, 0])
            t[0] += 1
            t[1] += bool(kayit.get("iyms_11"))
            ozet["indirilen"] += 1
            ozet["iddaasiz"] += kayit["market_sayisi"] == 0
            if ozet["indirilen"] % 500 == 0:
                log.info("%d indirildi (%s)", ozet["indirilen"], mac["tarih"])
        if bekleme:
            time.sleep(bekleme)

    with ThreadPoolExecutor(max_workers=is_parcacigi) as havuz:
        while not dur.is_set():
            parti = oncelikli_adaylar(list(kalan.values()), istat, hepsi)[:PARTI]
            if not parti:
                break
            list(havuz.map(is_, parti))
            with kilit:
                for ay, yeni in biriken.items():
                    _ay_yaz(ay, yeni)
                biriken.clear()
    if not ozet["durdu"] and dur.is_set():
        ozet["durdu"] = "süre doldu"
    return ozet


def oku(baslangic: str = "", bitis: str = "9999") -> dict[str, dict]:
    """mk_id -> oran kaydı (oranlar float ya da None)."""
    kayitlar = {}
    for yol in sorted(dizin().glob("*.csv.gz")):
        if not (baslangic[:7] <= yol.name[:7] <= bitis[:7]):
            continue
        for s in depo.gz_csv_oku(yol):
            for k in ORAN_SUTUNLARI:
                s[k] = float(s[k]) if s.get(k) else None
            kayitlar[s["mk_id"]] = s
    return kayitlar


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Mackolik maç sayfalarından geçmiş iddaa oranları")
    ap.add_argument("--baslangic", default="2019-01-01")
    ap.add_argument("--bitis", default="9999-12-31")
    ap.add_argument("--sure", type=float, default=300, help="dakika")
    ap.add_argument("--is-parcacigi", type=int, default=2)
    ap.add_argument("--hepsi", action="store_true", help="İY/MS'siz ligleri de indir")
    args = ap.parse_args()
    ozet = calistir(args.baslangic, args.bitis, args.sure, args.is_parcacigi, hepsi=args.hepsi)
    log.info("özet: %s", ozet)
    # Çıkış kodları workflow döngüsü için: 3 = aralıkta indirilecek maç kalmadı, 4 = site istekleri reddetti
    if ozet["durdu"].startswith("HTTP"):
        raise SystemExit(4)
    if ozet["aday"] == 0:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
