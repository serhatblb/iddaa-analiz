"""Mackolik: günlük iddaa programı sayfaları geçmiş tarihlerde oranları (İY/MS dahil) veriyor mu? Maç sayfası ne kadar yavaş?"""
import argparse
import re
import time
from pathlib import Path

import requests

BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36",
          "Referer": "https://arsiv.mackolik.com/Canli-Sonuclar"}
ADAYLAR = [
    "https://arsiv.mackolik.com/Iddaa-Programi",
    "https://arsiv.mackolik.com/Genis-Iddaa-Programi",
    "https://arsiv.mackolik.com/Iddaa-Programi?date=15/09/2026",
    "https://arsiv.mackolik.com/Genis-Iddaa-Programi?date=15/09/2026",
    "https://arsiv.mackolik.com/Iddaa-Programi/15-09-2026",
    "https://arsiv.mackolik.com/Genis-Iddaa-Programi/15-09-2026",
    "https://arsiv.mackolik.com/Iddaa/Program.aspx?date=15/09/2026",
    "https://arsiv.mackolik.com/SearchWithOdds.aspx",
]
MAC_SAYFALARI = ["4445135", "4445134", "3562540", "4436000", "4440000"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)
    oturum = requests.Session()
    for url in ADAYLAR:
        bas = time.monotonic()
        try:
            y = oturum.get(url, headers=BASLIK, timeout=60)
            sure = time.monotonic() - bas
            ad = re.sub(r"[^A-Za-z0-9]+", "_", url)[:120]
            (cikti / f"{ad}.html").write_text(y.text, encoding="utf-8")
            ipucu = [k for k in ("İY/MS", "IY/MS", "1/1", "2/1", "Yarı/Maç", "openOddsDialog", "iddaa", "MBS", "mbs")
                     if k in y.text]
            linkler = sorted(set(re.findall(r'(?:href|src|action)="([^"]*(?:Iddaa|iddaa|Program|Odds|odds)[^"]*)"',
                                            y.text)))[:40]
            print(y.status_code, len(y.text), f"{sure:.1f}s", url, ipucu)
            for l in linkler:
                print("     ", l)
        except requests.RequestException as hata:
            print("HATA", url, hata)
    for mk in MAC_SAYFALARI:
        bas = time.monotonic()
        try:
            y = oturum.get("https://arsiv.mackolik.com/Match/Default.aspx", params={"id": mk}, headers=BASLIK,
                           timeout=60)
            print("maç", mk, y.status_code, len(y.content), f"{time.monotonic() - bas:.1f}s",
                  y.headers.get("Content-Encoding"), y.headers.get("Server"), y.headers.get("X-Cache", ""),
                  "İY/MS" if "Yarı/Maç" in y.text else "")
        except requests.RequestException as hata:
            print("HATA maç", mk, hata)


if __name__ == "__main__":
    main()
