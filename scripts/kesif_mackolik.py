"""Mackolik livedata arşivi ne kadar geriye gidiyor, eski günlerde iddaa numarası, oranlar ve İY skoru var mı?"""
import argparse
import json
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import requests

KAYNAK = "https://vd.mackolik.com/livedata"
BASLIK = {"User-Agent": "Mozilla/5.0 (compatible; iddaa-analiz personal research)",
          "Referer": "https://arsiv.mackolik.com/Canli-Sonuclar"}


def dolu(x):
    return x not in (None, "", 0, "0", "-", "0.00")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    args = ap.parse_args()
    cikti = Path(args.cikti)
    bugun = date(2026, 9, 30)
    farklar = [0, 1, 7, 30, 90, 180, 365, 548, 730, 1095, 1460, 1825, 2190, 2555, 2920, 3285, 3650, 4380, 5475]
    oturum = requests.Session()
    ozet = []
    for fark in farklar:
        gun = bugun - timedelta(days=fark)
        tarih = gun.strftime("%d/%m/%Y")
        try:
            y = oturum.get(KAYNAK, params={"date": tarih}, headers=BASLIK, timeout=60)
            durum, boyut = y.status_code, len(y.content)
            veri = y.json() if y.ok else {}
        except Exception as hata:  # noqa: BLE001
            print(tarih, "HATA", hata)
            ozet.append({"tarih": tarih, "hata": str(hata)})
            continue
        satirlar = veri.get("m") or []
        futbol = [s for s in satirlar if len(s) > 36 and isinstance(s[36], list) and len(s[36]) > 11 and s[36][11] == 1]
        bitmis = [s for s in futbol if str(s[5]) in ("4", "6", "8")]
        kayit = {
            "tarih": tarih, "http": durum, "bayt": boyut, "anahtarlar": sorted(veri.keys()) if isinstance(veri, dict) else [],
            "satir": len(satirlar), "futbol": len(futbol), "bitmis": len(bitmis),
            "iddaa_no": sum(1 for s in futbol if dolu(s[14])),
            "oran_18": sum(1 for s in futbol if dolu(s[18])),
            "oran_21": sum(1 for s in futbol if dolu(s[21])),
            "iy_skor": sum(1 for s in bitmis if str(s[31]).strip() not in ("", "-")),
            "ulke_lig": len({(s[36][0]) for s in futbol}),
            "alan_sayisi": Counter(len(s) for s in satirlar).most_common(3),
        }
        ozet.append(kayit)
        print(json.dumps(kayit, ensure_ascii=False))
        if fark in (0, 1, 365, 1095, 1825, 3650):
            ornek = [s for s in bitmis if dolu(s[14])][:4] or bitmis[:4] or futbol[:4]
            (cikti / f"ornek_{gun.isoformat()}.json").write_text(json.dumps(ornek, ensure_ascii=False, indent=0))
        if fark in (0, 1):
            (cikti / f"gun_{gun.isoformat()}.json").write_text(json.dumps(futbol, ensure_ascii=False))
        time.sleep(1.5)
    (cikti / "ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
