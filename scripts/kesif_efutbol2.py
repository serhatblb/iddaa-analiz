"""E-futbol sonuç kaynağı: Mackolik canlı veride e-futbol var mı, iddaa'nın sonuç servisleri ne veriyor?"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from iddaa.api import BASLIKLAR, SPORTSBOOK, IddaaIstemci
from iddaa.config import TR
from iddaa.sonuc import gunluk_veri

E_FUTBOL = 137


def dene(oturum, url, cikti, params=None):
    try:
        y = oturum.get(url, params=params, headers=BASLIKLAR, timeout=30)
        ad = re.sub(r"[^A-Za-z0-9]+", "_", url)[-90:]
        (cikti / f"{ad}.txt").write_text(y.text[:200000], encoding="utf-8")
        print(f"{y.status_code} {len(y.text):>7} {url} {params or ''} | {y.text[:300]!r}")
        return y
    except requests.RequestException as hata:
        print("HATA", url, hata)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)

    # 1) Mackolik günlük veride spor türleri ve parantezli (oyunculu) takım adları
    bugun = datetime.now(timezone.utc).astimezone(TR)
    for fark in (0, 1):
        tarih = (bugun - timedelta(days=fark)).strftime("%d/%m/%Y")
        satirlar = gunluk_veri(tarih)
        spor = Counter((s[36][11] if isinstance(s[36], list) and len(s[36]) > 11 else "?") for s in satirlar)
        oyunculu = [s for s in satirlar if "(" in str(s[2]) and ")" in str(s[2])]
        ligler = Counter(str(s[36][1]) + " | " + str(s[36][3]) for s in oyunculu if isinstance(s[36], list))
        print(f"Mackolik {tarih}: {len(satirlar)} satır, spor türleri {dict(spor)}, oyunculu {len(oyunculu)}")
        print("   ligler:", ligler.most_common(10))
        for s in oyunculu[:5]:
            print("   ", s[:8], s[14], s[29:33])
        esport = [s for s in satirlar if isinstance(s[36], list) and len(s[36]) > 11 and s[36][11] not in (1,)]
        print("   futbol dışı örnek:", [(s[2], s[4], s[36][1], s[36][11]) for s in esport[:8]])

    # 2) iddaa: güncel e-futbol maçları, biten bir maç için olası sonuç servisleri
    ist = IddaaIstemci()
    veri = ist.getir(f"{SPORTSBOOK}/events", {"st": E_FUTBOL, "type": 0, "version": 0, "live": "true"}) or {}
    canli = [m for m in veri.get("events") or [] if m.get("sc")]
    print("\ncanlı e-futbol, skor alanı dolu:", len(canli))
    for m in canli[:5]:
        print("   ", m.get("i"), m.get("hn"), "-", m.get("an"), "sc:", json.dumps(m.get("sc"), ensure_ascii=False)[:300])
    oturum = requests.Session()
    ornek = 3277083  # dün öğleden sonra bitmiş bir e-futbol maçı
    for url in [f"https://statisticsv2.iddaa.com/statistics/eventsummary/{E_FUTBOL}/{ornek}",
                f"https://statisticsv2.iddaa.com/statistics/eventsummary/1/{ornek}",
                f"https://statisticsv2.iddaa.com/statistics/event-result/{ornek}",
                f"{SPORTSBOOK}/event/{ornek}",
                f"{SPORTSBOOK}/results",
                "https://sportsbookv2.iddaa.com/sportsbook/result",
                "https://www.iddaa.com/sonuclar/e-futbol",
                "https://www.iddaa.com/sonuclar"]:
        dene(oturum, url, cikti)
    sayfa = dene(oturum, "https://www.iddaa.com/sonuclar", cikti)
    if sayfa is not None:
        adresler = sorted(set(re.findall(r"https://[a-z0-9.\-]*iddaa\.com/[A-Za-z0-9_/\-\.?=&{}]+", sayfa.text)))
        print("sonuçlar sayfasındaki adresler:", adresler[:60])
        betikler = sorted(set(re.findall(r'src="([^"]+\.js)"', sayfa.text)))[:30]
        print("betikler:", betikler)
        for b in betikler[:30]:
            url = b if b.startswith("http") else "https://www.iddaa.com" + b
            try:
                js = oturum.get(url, headers=BASLIKLAR, timeout=30).text
            except requests.RequestException:
                continue
            bulunan = sorted(set(re.findall(r'["\'`](/?[a-zA-Z\-]*(?:result|sonuc|score)[a-zA-Z\-/{}$]*)["\'`]', js)))
            api = sorted(set(re.findall(r"https://[a-z0-9.\-]+iddaa\.com[^\"'`\s]*", js)))
            if bulunan or api:
                print("  ", url.split("/")[-1], bulunan[:20], api[:10])


if __name__ == "__main__":
    main()
