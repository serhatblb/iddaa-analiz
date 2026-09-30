"""Dosya tabanlı depo.

GitHub Actions'ta kalıcı disk olmadığı için veri repoya commit edilir:
- Anlık veriler (oranlar, oynanma yüzdeleri) çalışma başına ayrı, değişmeyen .csv.gz dosyaları.
- Güncellenen kayıtlar (maçlar, sonuçlar) aylık, düz metin CSV dosyaları (git farkları küçük kalır).
Analiz tarafında bu dosyalar DuckDB/PostgreSQL'e SQL ile yüklenebilir.
"""
import csv
import gzip
import io
import json
import os
from datetime import datetime
from pathlib import Path

from . import config

MAC_ALANLARI = [
    "mac_id", "lig_id", "lig", "ulke", "ev", "dep", "baslama_utc",
    "ilk_gorulme_utc", "acilis", "kapanis", "iyms_var", "son_detay_utc", "mbs", "kral",
]
# oran: iddaa.com ve bayilerde geçerli (Kral Oran), wodd: diğer sitelerdeki standart oran (~%4 düşük)
ORAN_ALANLARI = [
    "mac_id", "market", "market_id", "cizgi", "secenek_no", "secenek",
    "oran", "wodd", "tip", "zaman_utc", "mbs",
]
SECENEK_OYNANMA_ALANLARI = ["mac_id", "market_id", "secenek_no", "yuzde", "zaman_utc"]
MAC_OYNANMA_ALANLARI = ["mac_id", "yuzde", "zaman_utc"]
SONUC_ALANLARI = ["mac_id", "iy_ev", "iy_dep", "ms_ev", "ms_dep", "durum", "kaynak", "guncelleme_utc"]
LIG_ALANLARI = ["lig_id", "ulke", "ad", "kisa_ad"]


def kok() -> Path:
    return Path(os.environ.get("IDDAA_VERI", str(config.VERI_DIZINI)))


# --- düşük seviye yardımcılar ---

def csv_oku(yol: Path) -> list[dict]:
    if not yol.exists():
        return []
    with open(yol, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def csv_yaz(yol: Path, satirlar: list[dict], alanlar: list[str]) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(yol.suffix + ".tmp")
    with open(gecici, "w", newline="", encoding="utf-8") as f:
        yazici = csv.DictWriter(f, fieldnames=alanlar, extrasaction="ignore")
        yazici.writeheader()
        yazici.writerows(satirlar)
    gecici.replace(yol)


def gz_csv_yaz(yol: Path, satirlar: list[dict], alanlar: list[str]) -> None:
    if not satirlar:
        return
    yol.parent.mkdir(parents=True, exist_ok=True)
    tampon = io.StringIO()
    yazici = csv.DictWriter(tampon, fieldnames=alanlar, extrasaction="ignore")
    yazici.writeheader()
    yazici.writerows(satirlar)
    # mtime=0: aynı içerik aynı baytları üretir
    with open(yol, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(tampon.getvalue().encode("utf-8"))


def gz_csv_oku(yol: Path) -> list[dict]:
    with gzip.open(yol, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def json_oku(yol: Path):
    if not yol.exists():
        return None
    return json.loads(yol.read_text(encoding="utf-8"))


def json_yaz(yol: Path, veri) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def ay_anahtari(iso_zaman: str) -> str:
    return iso_zaman[:7]


def anlik_yolu(tur: str, zaman: datetime) -> Path:
    return kok() / tur / zaman.strftime("%Y/%m/%d") / f"{zaman.strftime('%H%M')}.csv.gz"


# --- maç kayıtları ---

def maclari_oku() -> dict[str, dict]:
    kayitlar = {}
    for yol in sorted((kok() / "maclar").glob("*.csv")):
        for satir in csv_oku(yol):
            kayitlar[satir["mac_id"]] = satir
    return kayitlar


def maclari_yaz(kayitlar: dict[str, dict], degisenler: set[str]) -> None:
    aylar = {ay_anahtari(kayitlar[m]["baslama_utc"]) for m in degisenler if m in kayitlar}
    for ay in aylar:
        satirlar = sorted(
            (k for k in kayitlar.values() if ay_anahtari(k["baslama_utc"]) == ay),
            key=lambda k: (k["baslama_utc"], int(k["mac_id"])),
        )
        csv_yaz(kok() / "maclar" / f"{ay}.csv", satirlar, MAC_ALANLARI)


# --- sonuçlar ---

def sonuclari_oku() -> dict[str, dict]:
    sonuclar = {}
    for yol in sorted((kok() / "sonuclar").glob("*.csv")):
        for satir in csv_oku(yol):
            sonuclar[satir["mac_id"]] = satir
    return sonuclar


def sonuclari_yaz(sonuclar: dict[str, dict], kayitlar: dict[str, dict], degisenler: set[str]) -> None:
    def ay(mac_id):
        kayit = kayitlar.get(mac_id)
        return ay_anahtari(kayit["baslama_utc"]) if kayit else "bilinmeyen"

    aylar = {ay(m) for m in degisenler}
    for hedef in aylar:
        satirlar = sorted(
            (s for m, s in sonuclar.items() if ay(m) == hedef),
            key=lambda s: int(s["mac_id"]),
        )
        csv_yaz(kok() / "sonuclar" / f"{hedef}.csv", satirlar, SONUC_ALANLARI)


# --- oran anlıkları ---

def oran_dosyalari(baslangic: datetime | None = None) -> list[Path]:
    dosyalar = sorted((kok() / "oranlar").glob("*/*/*/*.csv.gz"))
    if baslangic is None:
        return dosyalar
    esik = baslangic.strftime("%Y/%m/%d")
    return [d for d in dosyalar if "/".join(d.parts[-4:-1]) >= esik]
