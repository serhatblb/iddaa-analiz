"""Mackolik maç sayfası: yanıt süreleri ve hata oranı (arşivden rastgele iddaa maçları, sırayla)."""
import argparse
import random
import time
from collections import Counter
from pathlib import Path

import requests

from iddaa import arsiv

BASLIK = {"User-Agent": "Mozilla/5.0 (compatible; iddaa-analiz personal research)",
          "Referer": "https://arsiv.mackolik.com/Canli-Sonuclar"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--adet", type=int, default=25)
    args = ap.parse_args()
    maclar = [m for m in arsiv.oku("2025-10", "2026-09") if m["iddaa_id"]]
    random.seed(1)
    ornek = random.sample(maclar, args.adet)
    oturum = requests.Session()
    kodlar, sureler = Counter(), []
    for m in ornek:
        bas = time.monotonic()
        try:
            y = oturum.get("https://arsiv.mackolik.com/Match/Default.aspx", params={"id": m["mk_id"]},
                           headers=BASLIK, timeout=60)
            kod = y.status_code
            boy = len(y.content)
        except requests.RequestException as hata:
            kod, boy = type(hata).__name__, 0
        sure = time.monotonic() - bas
        kodlar[kod] += 1
        sureler.append(sure)
        print(m["tarih"], m["mk_id"], kod, boy, f"{sure:.1f}s", "İY/MS" if kod == 200 and "Yarı/Maç" in y.text else "")
        time.sleep(0.5)
    sureler.sort()
    print("kodlar:", dict(kodlar), "medyan süre %.1fs" % sureler[len(sureler) // 2], "en uzun %.1fs" % sureler[-1])
    (Path(args.cikti) / "ozet.txt").write_text(str(dict(kodlar)))


if __name__ == "__main__":
    main()
