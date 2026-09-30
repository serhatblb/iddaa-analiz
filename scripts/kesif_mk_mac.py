"""Mackolik maç sayfasında iddaa oranları (İY/MS dahil) için bir uç nokta var mı?"""
import argparse
import re
import time
from pathlib import Path

import requests

BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36",
          "Referer": "https://arsiv.mackolik.com/Canli-Sonuclar"}
MACLAR = {"4445135": "Ispanya-Hirvatistan", "3562540": "Fatih-Karagumruk-Basaksehir"}
ADAYLAR = [
    "https://arsiv.mackolik.com/Mac/{id}/{ad}",
    "https://arsiv.mackolik.com/Match/Default.aspx?id={id}",
    "https://arsiv.mackolik.com/Match/MatchData.aspx?t=iddaa&id={id}",
    "https://arsiv.mackolik.com/Match/MatchData.aspx?t=dtl&id={id}&s=0",
    "https://arsiv.mackolik.com/AjaxHandlers/MatchHandler.aspx?command=optimizedoddsdata&id={id}",
    "https://arsiv.mackolik.com/Iddaa/MacDetay/{id}",
    "https://vd.mackolik.com/iddaadata?id={id}",
    "https://vd.mackolik.com/matchdata?id={id}",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)
    oturum = requests.Session()
    oturum.headers.update(BASLIK)
    bulunan = set()
    for mac_id, ad in MACLAR.items():
        for sablon in ADAYLAR:
            url = sablon.format(id=mac_id, ad=ad)
            try:
                y = oturum.get(url, timeout=30, allow_redirects=True)
            except requests.RequestException as hata:
                print("HATA", url, hata)
                continue
            govde = y.text
            ipucu = [k for k in ("İY/MS", "IY/MS", "iyms", "1/1", "2/1", "Kral", "oran", "odd") if k in govde]
            print(y.status_code, len(govde), y.url, "ipucu:", ipucu)
            dosya = re.sub(r"[^A-Za-z0-9]+", "_", url)[-80:]
            (cikti / f"{dosya}.txt").write_text(govde[:400000])
            for u in re.findall(r"""["'](/[A-Za-z]+/[A-Za-z]+\.aspx[^"']*|https?://[^"']*(?:aspx|ashx|json|data)[^"']*)["']""",
                                govde):
                bulunan.add(u)
            time.sleep(1)
    (cikti / "bulunan_url.txt").write_text("\n".join(sorted(bulunan)))
    print("\n".join(sorted(bulunan))[:6000])


if __name__ == "__main__":
    main()
