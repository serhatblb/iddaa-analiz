"""Spor Toto keşfi 2: iddaa (sportotov2.iddaa.com) ve sportoto.gov.tr (webapi) uç noktalarını JS'ten çıkar ve dene."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36",
          "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "application/json, text/plain, */*"}
IDDAA = {**BASLIK, "Origin": "https://www.iddaa.com", "Referer": "https://www.iddaa.com/"}
GOV = {**BASLIK, "Origin": "https://www.sportoto.gov.tr", "Referer": "https://www.sportoto.gov.tr/"}


def ad(url):
    return re.sub(r"[^A-Za-z0-9]+", "_", url)[-110:]


def betikleri_indir(oturum, sayfa, cikti, klasor):
    (cikti / klasor).mkdir(exist_ok=True)
    html = oturum.get(sayfa, headers=BASLIK, timeout=30).text
    srcler = [urljoin(sayfa, s) for s in re.findall(r'<script[^>]+src="([^"]+)"', html)]
    # Next.js sayfa parçaları build manifest'te
    manifest = [s for s in srcler if "_buildManifest" in s]
    if manifest:
        m = oturum.get(manifest[0], headers=BASLIK, timeout=30).text
        kok = manifest[0].split("/_next/")[0] + "/_next/"
        for parca in re.findall(r'"(static/chunks/[^"]+\.js)"', m):
            if re.search(r"toto|sonuc|liste|program|hafta", parca, re.I):
                srcler.append(kok + parca)
    metinler = {}
    for s in dict.fromkeys(srcler):
        try:
            js = oturum.get(s, headers=BASLIK, timeout=30).text
        except requests.RequestException:
            continue
        metinler[s] = js
        (cikti / klasor / ad(s)).write_text(js, encoding="utf-8")
    print(klasor, "betik:", len(metinler))
    return metinler


def baglam(metinler, desen, genislik=220, sinir=40):
    say = 0
    for s, js in metinler.items():
        for m in re.finditer(desen, js):
            print("   [", s.split("/")[-1][:35], "]", js[max(0, m.start() - genislik): m.end() + genislik].replace("\n", " "))
            say += 1
            if say >= sinir:
                return


def dene(oturum, url, cikti, baslik, params=None, yontem="GET", govde=None):
    try:
        if yontem == "GET":
            y = oturum.get(url, headers=baslik, params=params, timeout=30)
        else:
            y = oturum.post(url, headers={**baslik, "Content-Type": "application/json"}, json=govde, timeout=30)
    except requests.RequestException as hata:
        print("HATA", url, hata)
        return None
    (cikti / f"y_{ad(url + json.dumps(params or govde or ''))}.txt").write_text(y.text, encoding="utf-8")
    print(f"{y.status_code} {len(y.text):>8} {yontem} {url} {params or govde or ''} | {y.text[:700]!r}")
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)
    oturum = requests.Session()

    print("===== iddaa JS")
    ijs = betikleri_indir(oturum, "https://www.iddaa.com/spor-toto", cikti, "iddaa_js")
    baglam(ijs, r"sportotov2|SporToto/|gameCycle|last_result|dateFilter")

    print("\n===== sportoto.gov.tr JS")
    gjs = {}
    for sayfa in ("https://www.sportoto.gov.tr/", "https://www.sportoto.gov.tr/spor-toto-listeler"):
        gjs.update(betikleri_indir(oturum, sayfa, cikti, "gov_js"))
    baglam(gjs, r'\.(?:get|post)\("[^"]*"|concat\("api/|"api/[A-Za-z/]+', 160, 60)

    print("\n===== iddaa denemeler")
    for kok in ("https://sportotov2.iddaa.com", "https://sportotov2.iddaa.com/api", "https://sportotov2.iddaa.com/sportoto"):
        for yol in ("/SporToto", "/SporToto/last_result", "/SporToto/dateFilter", "/SporToto/result?gameCycleNo=1"):
            dene(oturum, kok + yol, cikti, IDDAA)

    print("\n===== gov denemeler")
    for yol in ("api/Program", "api/program/getall", "api/SporToto", "api/Week", "api/weeks", "api/SporTotoList",
                "api/Result", "api/results", "api/Setting", "api/Program/GetProgramYears"):
        dene(oturum, "https://webapi.sportoto.gov.tr/" + yol, cikti, GOV)


if __name__ == "__main__":
    main()
