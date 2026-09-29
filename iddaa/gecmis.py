"""Geçmiş veri: football-data.co.uk'tan lig maçlarının İY/MS skorları ve maç sonucu oranları.

Kaynak ücretsiz CSV'ler sunar (https://www.football-data.co.uk/data.php). İY/MS oranı yoktur ama
İY ve MS skorları ile 1-0-2 oranları vardır. Bu veriyle:
- MS oran aralıklarının gerçek tutma oranı ve getirisi,
- favorinin gücüne göre İY/MS sonuçlarının gerçek sıklıkları
hesaplanır. Oranlar yabancı bahis şirketlerinden gelir; iddaa genelde daha düşük oran verir.
"""
import csv
import io
import logging
import time
from datetime import datetime

import requests

from . import depo

log = logging.getLogger("gecmis")

KAYNAK = "https://www.football-data.co.uk/mmz4281/{sezon}/{lig}.csv"
LIGLER = {
    "E0": "İngiltere Premier Lig", "E1": "İngiltere Championship", "E2": "İngiltere League One",
    "E3": "İngiltere League Two", "EC": "İngiltere National League",
    "SC0": "İskoçya Premiership", "SC1": "İskoçya Championship", "SC2": "İskoçya League One",
    "SC3": "İskoçya League Two",
    "D1": "Almanya Bundesliga", "D2": "Almanya 2. Bundesliga",
    "I1": "İtalya Serie A", "I2": "İtalya Serie B",
    "SP1": "İspanya La Liga", "SP2": "İspanya Segunda",
    "F1": "Fransa Ligue 1", "F2": "Fransa Ligue 2",
    "N1": "Hollanda Eredivisie", "B1": "Belçika Pro Lig", "P1": "Portekiz Primeira Liga",
    "T1": "Türkiye Süper Lig", "G1": "Yunanistan Süper Lig",
}
ILK_SEZON = 2012

ALANLAR = ["lig", "sezon", "tarih", "ev", "dep", "iy_ev", "iy_dep", "ms_ev", "ms_dep",
           "ort_1", "ort_0", "ort_2", "maks_1", "maks_0", "maks_2", "ps_1", "ps_0", "ps_2",
           "ort_ust25", "ort_alt25"]

# Her alan için öncelik sırasıyla aranacak sütunlar (kapanış > açılış > eski format)
ORAN_SUTUNLARI = {
    "ort_1": ["AvgCH", "AvgH", "BbAvH"], "ort_0": ["AvgCD", "AvgD", "BbAvD"], "ort_2": ["AvgCA", "AvgA", "BbAvA"],
    "maks_1": ["MaxCH", "MaxH", "BbMxH"], "maks_0": ["MaxCD", "MaxD", "BbMxD"], "maks_2": ["MaxCA", "MaxA", "BbMxA"],
    "ps_1": ["PSCH", "PSH"], "ps_0": ["PSCD", "PSD"], "ps_2": ["PSCA", "PSA"],
    "ort_ust25": ["AvgC>2.5", "Avg>2.5", "BbAv>2.5"], "ort_alt25": ["AvgC<2.5", "Avg<2.5", "BbAv<2.5"],
}


def sezon_kodlari(bugun: datetime | None = None) -> list[str]:
    bugun = bugun or datetime.now()
    son = bugun.year if bugun.month >= 7 else bugun.year - 1
    return [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(ILK_SEZON, son + 1)]


def _sayi(deger: str | None) -> float | None:
    try:
        sayi = float((deger or "").strip())
    except ValueError:
        return None
    return sayi if sayi > 1.0 else None


def _tam(deger: str | None) -> int | None:
    try:
        return int(float((deger or "").strip()))
    except ValueError:
        return None


def _tarih(metin: str) -> str | None:
    for bicim in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(metin.strip(), bicim).date().isoformat()
        except ValueError:
            continue
    return None


def cozumle(icerik: bytes, lig: str, sezon: str) -> list[dict]:
    try:
        metin = icerik.decode("utf-8-sig")
    except UnicodeDecodeError:
        metin = icerik.decode("latin-1")
    satirlar = []
    for ham in csv.DictReader(io.StringIO(metin)):
        ham = {(k or "").strip(): v for k, v in ham.items()}
        skorlar = [_tam(ham.get(s)) for s in ("HTHG", "HTAG", "FTHG", "FTAG")]
        tarih = _tarih(ham.get("Date") or "")
        if tarih is None or any(s is None for s in skorlar):
            continue
        satir = {"lig": lig, "sezon": sezon, "tarih": tarih,
                 "ev": (ham.get("HomeTeam") or ham.get("Home") or "").strip(),
                 "dep": (ham.get("AwayTeam") or ham.get("Away") or "").strip(),
                 "iy_ev": skorlar[0], "iy_dep": skorlar[1], "ms_ev": skorlar[2], "ms_dep": skorlar[3]}
        for alan, sutunlar in ORAN_SUTUNLARI.items():
            satir[alan] = next((v for v in (_sayi(ham.get(s)) for s in sutunlar) if v is not None), "")
        satirlar.append(satir)
    return satirlar


def indir(ligler: dict = LIGLER, sezonlar: list[str] | None = None, bekleme: float = 0.3) -> list[dict]:
    oturum = requests.Session()
    oturum.headers["User-Agent"] = "iddaa-analiz (kişisel analiz projesi)"
    tum = []
    for sezon in sezonlar or sezon_kodlari():
        for lig in ligler:
            url = KAYNAK.format(sezon=sezon, lig=lig)
            try:
                yanit = oturum.get(url, timeout=30)
            except requests.RequestException as hata:
                log.warning("%s alınamadı: %s", url, hata)
                continue
            time.sleep(bekleme)
            if yanit.status_code != 200:
                log.info("%s yok (%s)", url, yanit.status_code)
                continue
            satirlar = cozumle(yanit.content, lig, sezon)
            log.info("%s %s: %d maç", sezon, lig, len(satirlar))
            tum += satirlar
    return tum


def dizin():
    return depo.kok() / "gecmis"


def oku() -> list[dict]:
    maclar = []
    for dosya in sorted(dizin().glob("*.csv.gz")):
        maclar += _satirlari_cevir(depo.gz_csv_oku(dosya))
    return maclar


def _satirlari_cevir(satirlar: list[dict]) -> list[dict]:
    maclar = []
    for s in satirlar:
        for k in ("iy_ev", "iy_dep", "ms_ev", "ms_dep"):
            s[k] = int(s[k])
        for k in ORAN_SUTUNLARI:
            s[k] = float(s[k]) if s[k] else None
        maclar.append(s)
    return maclar


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # Biten sezonlar bir kez indirilir; sonraki çalışmalarda sadece eksikler ve güncel sezon
    kodlar = sezon_kodlari()
    istenen = [s for s in kodlar if s == kodlar[-1] or not (dizin() / f"{s}.csv.gz").exists()]
    maclar = indir(sezonlar=istenen)
    if not maclar:
        if any(dizin().glob("*.csv.gz")):
            log.warning("Yeni geçmiş veri indirilemedi, mevcut dosyalar kullanılacak.")
            return
        raise SystemExit("Hiç geçmiş maç indirilemedi.")
    # Sezon başına ayrı dosya: biten sezonların dosyası bayt bayt aynı kalır, git'te değişiklik oluşmaz
    sezonlar: dict[str, list[dict]] = {}
    for m in maclar:
        sezonlar.setdefault(m["sezon"], []).append(m)
    for sezon, satirlar in sezonlar.items():
        satirlar.sort(key=lambda m: (m["tarih"], m["lig"], m["ev"]))
        depo.gz_csv_yaz(dizin() / f"{sezon}.csv.gz", satirlar, ALANLAR)
    log.info("toplam %d geçmiş maç, %d sezon yazıldı", len(maclar), len(sezonlar))


if __name__ == "__main__":
    main()
