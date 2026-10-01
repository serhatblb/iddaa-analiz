"""E-Futbol keşfi: iddaa'daki e-futbol bülteni (spor 137) ve geçmiş sonuç kaynaklarına erişim."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import requests

from iddaa.api import SPORTSBOOK, IddaaIstemci

E_FUTBOL = 137
BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36", "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
KAYNAKLAR = [
    "https://www.totalcorner.com/league/view/12995",            # Esoccer Battle 8 dk
    "https://www.totalcorner.com/league/view/12985",            # Esoccer GT Leagues 12 dk
    "https://www.totalcorner.com/league/view/12995/end/page:5",
    "https://footystats.org/esports/esoccer-battle",
    "https://esoccerbet.org/fifa-8-minutes/",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)
    ist = IddaaIstemci()

    ligler = [l for l in (ist.getir(f"{SPORTSBOOK}/competitions") or []) if str(l.get("si")) == str(E_FUTBOL)]
    print("iddaa e-futbol ligleri:", len(ligler))
    for l in ligler[:40]:
        print("   ", l.get("i"), l.get("n"), "|", l.get("sn"), "|", l.get("cid"))
    (cikti / "ligler.json").write_text(json.dumps(ligler, ensure_ascii=False, indent=1))

    for canli in (False, True):
        params = {"st": E_FUTBOL, "type": 0, "version": 0}
        if canli:
            params["live"] = "true"
        veri = ist.getir(f"{SPORTSBOOK}/events", params) or {}
        maclar = veri.get("events") or []
        print(f"\nbülten canlı={canli}: {len(maclar)} maç")
        markets = Counter()
        for m in maclar:
            for mk in m.get("m") or []:
                markets[f"{mk.get('t')}_{mk.get('st')}"] += 1
        print("  marketler:", markets.most_common(15))
        for m in maclar[:12]:
            ms = [mk for mk in m.get("m") or [] if mk.get("st") in (1, 101) or mk.get("t") == 1]
            ozet = [(f"{mk.get('t')}_{mk.get('st')}", mk.get("sov"), [(o.get("n"), o.get("odd")) for o in mk.get("o") or []])
                    for mk in ms[:3]]
            print("   ", m.get("i"), m.get("d"), m.get("ci"), "|", m.get("hn"), "-", m.get("an"), "|", ozet,
                  "| sc:", m.get("sc"))
        (cikti / f"bulten_{'canli' if canli else 'on'}.json").write_text(json.dumps(maclar[:30], ensure_ascii=False, indent=1))
        if maclar and not canli:
            detay = ist.getir(f"{SPORTSBOOK}/event/{maclar[0]['i']}")
            (cikti / "ornek_detay.json").write_text(json.dumps(detay, ensure_ascii=False, indent=1))
            if detay:
                print("  detay marketleri:", sorted({f"{x.get('t')}_{x.get('st')}" for x in detay.get("m") or []}))

    oturum = requests.Session()
    for url in KAYNAKLAR:
        try:
            y = oturum.get(url, headers=BASLIK, timeout=30)
            ad = re.sub(r"[^A-Za-z0-9]+", "_", url)[:90]
            (cikti / f"{ad}.html").write_text(y.text, encoding="utf-8")
            satir = re.findall(r"\((?:[A-Za-z0-9_\-\.]{2,20})\)", y.text)
            print(f"\n{y.status_code} {len(y.text)} {url} | oyuncu etiketi örnekleri: {Counter(satir).most_common(8)}")
        except requests.RequestException as hata:
            print("HATA", url, hata)


if __name__ == "__main__":
    main()
