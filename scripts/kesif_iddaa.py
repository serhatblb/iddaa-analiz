"""iddaa bülten verisinde hangi alanlar var? (MBS, market ve seçenek alanları)"""
import argparse
import json
from collections import Counter
from pathlib import Path

from iddaa.api import IddaaIstemci


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    cikti = Path(ap.parse_args().cikti)
    istemci = IddaaIstemci()
    bulten = istemci.bulten() or {}
    maclar = [m for m in bulten.get("events") or [] if m.get("hn")]
    print("bülten anahtarları:", sorted(bulten.keys()))
    print("maç sayısı:", len(maclar))
    mac_alanlari, market_alanlari, secenek_alanlari = Counter(), Counter(), Counter()
    degerler = {}
    for m in maclar:
        mac_alanlari.update(m.keys())
        for mk in m.get("m") or []:
            market_alanlari.update(mk.keys())
            for k, v in mk.items():
                if k not in ("o",) and not isinstance(v, (list, dict)):
                    degerler.setdefault(f"market.{k}", Counter())[str(v)[:20]] += 1
            for o in mk.get("o") or []:
                secenek_alanlari.update(o.keys())
        for k, v in m.items():
            if not isinstance(v, (list, dict)):
                degerler.setdefault(f"mac.{k}", Counter())[str(v)[:20]] += 1
    print("maç alanları:", dict(mac_alanlari))
    print("market alanları:", dict(market_alanlari))
    print("seçenek alanları:", dict(secenek_alanlari))
    for k, c in sorted(degerler.items()):
        if len(c) <= 40:
            print(k, dict(c.most_common(15)))
        else:
            print(k, f"({len(c)} farklı)", dict(c.most_common(5)))
    (cikti / "ornek_bulten.json").write_text(json.dumps(maclar[:3], ensure_ascii=False, indent=1))
    ornek = next((m for m in maclar if len(m.get("m") or []) >= 2), maclar[0])
    detay = istemci.mac(ornek["i"])
    (cikti / "ornek_detay.json").write_text(json.dumps(detay, ensure_ascii=False, indent=1))
    marketler = Counter()
    for mk in (detay or {}).get("m") or []:
        marketler[(mk.get("t"), mk.get("st"), str(mk.get("mbc", mk.get("mbs", ""))))] += 1
    print("detay marketleri (t, st, mbc):", sorted(marketler.items())[:80])
    ayar = istemci.market_ayarlari() or {}
    (cikti / "market_ayarlari.json").write_text(json.dumps(ayar, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
