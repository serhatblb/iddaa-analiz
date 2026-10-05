"""Spor Toto geçmişi: sportotov2.iddaa.com'dan bütün dönemleri (1..güncel) indir -> donemler.jsonl"""
import argparse
import json
import time
from pathlib import Path

import requests

API = "https://sportotov2.iddaa.com/SporToto"
BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36",
          "Accept": "application/json, text/plain, */*", "Origin": "https://www.iddaa.com",
          "Referer": "https://www.iddaa.com/"}


def getir(oturum, url, params=None):
    for deneme in range(4):
        try:
            y = oturum.get(url, params=params, headers=BASLIK, timeout=30)
            if y.status_code == 200:
                return y.json()
            print("durum", y.status_code, url, params)
        except (requests.RequestException, ValueError) as hata:
            print("hata", hata)
        time.sleep(2 + 3 * deneme)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)
    oturum = requests.Session()
    guncel = getir(oturum, API)
    (cikti / "guncel.json").write_text(json.dumps(guncel, ensure_ascii=False, indent=1), encoding="utf-8")
    son = guncel["data"]["gameCycleNo"]
    print("güncel dönem", son, guncel["data"].get("programName"))
    with open(cikti / "donemler.jsonl", "w", encoding="utf-8") as f:
        for no in range(1, son + 1):
            veri = getir(oturum, f"{API}/result", {"gameCycleNo": no})
            if not veri or not veri.get("data"):
                print("boş", no, (veri or {}).get("message"))
                continue
            f.write(json.dumps(veri["data"], ensure_ascii=False) + "\n")
            if no % 25 == 0:
                d = veri["data"]
                print(no, d.get("programName"), [(x["winners"], x["amount"]) for x in d.get("dividends") or []])
            time.sleep(0.3)


if __name__ == "__main__":
    main()
