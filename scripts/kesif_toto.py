"""Spor Toto veri kaynakları keşfi: program, oynanma yüzdeleri, hasılat/kolon, kazanan sayıları, devreden.

Sayfaları ve JS dosyalarını indirir, içlerindeki toto ile ilgili API adreslerini arar, bulunan adresleri dener.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36",
          "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8", "Accept": "text/html,application/json,*/*"}
SAYFALAR = [
    "https://www.sportoto.gov.tr/",
    "https://www.sportoto.gov.tr/spor-toto-listeler",
    "https://www.sportoto.gov.tr/spor-toto-sonuclari",
    "https://www.iddaa.com/spor-toto",
    "https://www.iddaa.com/spor-toto/sonuclar",
    "https://www.sportotolistesi.com/",
    "https://www.misli.com/spor-toto",
    "https://www.misli.com/spor-toto/mac-sonuclari",
    "https://www.bilyoner.com/spor-toto/sonuclar",
    "https://www.nesine.com/spor-toto",
]
API_DESEN = re.compile(r"""["'`]((?:https?://[a-z0-9.\-]+)?/[A-Za-z0-9_\-/.]*(?:[Tt]oto|[Pp]ool|[Hh]afta|[Ww]eek|[Ii]kramiye|"""
                       r"""[Dd]evreden|[Pp]rogram)[A-Za-z0-9_\-/.{}$?=&]*)["'`]""")
MUTLAK = re.compile(r"https?://[a-z0-9.\-]*(?:api|toto|webapi)[a-z0-9.\-]*\.[a-z]{2,}[A-Za-z0-9_\-/.?=&{}$]*")


def ad(url):
    return re.sub(r"[^A-Za-z0-9]+", "_", url)[-100:]


def getir(oturum, url, cikti, sinir=400):
    try:
        y = oturum.get(url, headers=BASLIK, timeout=30)
    except requests.RequestException as hata:
        print("HATA", url, hata)
        return None
    (cikti / f"{ad(url)}.txt").write_text(y.text[:3_000_000], encoding="utf-8")
    print(f"{y.status_code} {len(y.text):>8} {url} | {y.text[:sinir]!r}")
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--ek", default="", help="virgülle ayrılmış, ayrıca denenecek adresler")
    a = ap.parse_args()
    cikti = Path(a.cikti)
    oturum = requests.Session()
    bulunanlar: dict[str, set] = {}

    for sayfa in SAYFALAR:
        print("\n=====", sayfa)
        y = getir(oturum, sayfa, cikti, 200)
        if y is None:
            continue
        html = y.text
        for etiket in ("__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__APOLLO_STATE__"):
            if etiket in html:
                print("   gömülü veri:", etiket)
        for m in re.finditer(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S):
            (cikti / f"{ad(sayfa)}_next.json").write_text(m.group(1), encoding="utf-8")
            print("   __NEXT_DATA__ boyutu", len(m.group(1)), m.group(1)[:600])
        betikler = []
        for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
            tam = urljoin(sayfa, src)
            if urlparse(tam).netloc.split(".")[-2:] == urlparse(sayfa).netloc.split(".")[-2:] or "_next" in tam:
                betikler.append(tam)
        print("   betik sayısı:", len(betikler))
        site = urlparse(sayfa).netloc
        for kaynak in [html] + [None] * 0:
            for m in API_DESEN.findall(kaynak):
                bulunanlar.setdefault(site, set()).add(m)
            for m in MUTLAK.findall(kaynak):
                bulunanlar.setdefault(site, set()).add(m)
        for b in betikler[:60]:
            try:
                js = oturum.get(b, headers=BASLIK, timeout=30).text
            except requests.RequestException:
                continue
            for m in API_DESEN.findall(js):
                bulunanlar.setdefault(site, set()).add(m)
            for m in MUTLAK.findall(js):
                bulunanlar.setdefault(site, set()).add(m)
            if re.search(r"toto", js, re.I):
                for parca in re.findall(r".{0,160}[Tt]oto.{0,160}", js)[:25]:
                    if "api" in parca.lower() or "url" in parca.lower() or "fetch" in parca.lower():
                        print("   [js]", b.split("/")[-1][:40], parca.replace("\n", " ")[:320])

    print("\n===== bulunan adresler")
    denenecek = []
    for site, kume in bulunanlar.items():
        print(site)
        for u in sorted(kume)[:150]:
            print("   ", u)
            if "{" in u or "$" in u or u.endswith((".js", ".css", ".png", ".svg", ".jpg", ".webp")):
                continue
            tam = u if u.startswith("http") else None
            if tam and ("toto" in tam.lower() or "api" in tam.lower()):
                denenecek.append(tam)
    denenecek += [u for u in a.ek.split(",") if u]
    print("\n===== denemeler")
    for u in sorted(set(denenecek))[:80]:
        getir(oturum, u, cikti, 500)


if __name__ == "__main__":
    main()
