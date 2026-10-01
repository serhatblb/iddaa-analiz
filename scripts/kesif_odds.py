"""The Odds API erişim ve kota kontrolü (anahtar GitHub secret'tan; ekrana yazılmaz)."""
import argparse
import os

from iddaa.pinnacle import OddsApi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    ap.parse_args()
    anahtar = os.environ.get("ODDS_API_KEY", "")
    if not anahtar:
        print("ODDS_API_KEY tanımlı değil")
        return
    api = OddsApi(anahtar)
    sporlar = api.getir("/sports")
    futbol = [s for s in sporlar if s.get("group") == "Soccer" and s.get("active") and not s.get("has_outrights")]
    print("aktif futbol ligi:", len(futbol), "kalan kredi:", api.kalan)
    print([s["key"] for s in futbol])


if __name__ == "__main__":
    main()
