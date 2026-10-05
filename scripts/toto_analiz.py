"""Spor Toto devreden analizi -> data/analiz/toto.json

1) Geçmiş: kaç haftada 15 bilen çıkmadı, devreden kaç hafta sürdü, en büyük havuz.
2) Ortalama oyuncu: her hafta ödenen toplam ikramiye / hasılat (devredenin ortalama kolona etkisi).
3) Kolon stratejileri, 2023-08'den bu yana (kolon fiyatının bilindiği dönem), gerçek sonuç ve ikramiyelerle:
   - olasılık: her maç iddaa olasılığıyla rastgele doldurulur
   - tek favori: her maçta en olası sonuç (tek kolon)
   - sistem p≥t: olasılığı t'yi geçen bütün sonuçlar işaretli sistem kuponu
   - eşit: tamamen rastgele kolon
4) Bir yıllık oyun benzetimi (geçmiş haftalardan yeniden örnekleme), haftada K kolon.
"""
import json
import math
from collections import defaultdict
from datetime import date

import numpy as np

from iddaa import arsiv, depo, kalibrasyon, sonuc, toto

BASLANGIC = "2023-08-06"
DONEMLER = {"2023/24 (2 TL)": ("2023-08-06", "2024-08-11"), "2024/25 (4 TL)": ("2024-08-11", "2025-03-18"),
            "2025/26 (10 TL)": ("2025-03-18", "9999")}


def gecmis_ozeti(hs):
    tum = [h for h in hs if h["P"]]
    seri = en_uzun = 0
    for h in tum:
        seri = seri + 1 if h["dereceler"][15]["kazanan"] == 0 else 0
        en_uzun = max(en_uzun, seri)
    en_buyuk = max(tum, key=lambda h: h["havuz"][15])
    return {"hafta": len(tum), "ilk": tum[0]["bas"][:10], "son": tum[-1]["bas"][:10],
            "15_cikmayan_oran": round(sum(h["dereceler"][15]["kazanan"] == 0 for h in tum) / len(tum), 3),
            "en_uzun_devir_serisi": en_uzun,
            "en_buyuk_15_havuzu": {"no": en_buyuk["no"], "program": en_buyuk["program"],
                                   "havuz": round(en_buyuk["havuz"][15]), "kazanan": en_buyuk["dereceler"][15]["kazanan"]}}


def ortalama_oyuncu(hs):
    """Her hafta: ödenen toplam ikramiye / hasılat. Devreden yoksa ≈ 0.69 (bütün dereceler kazanılırsa)."""
    satirlar = []
    for h in hs:
        if not h["P"] or h["bas"][:10] < BASLANGIC:
            continue
        R = toto.hasilat(h["P"])
        odenen = sum(h["havuz"][k] for k in toto.PAYLAR if h["dereceler"][k]["kazanan"])
        satirlar.append({"no": h["no"], "program": h["program"], "getiri": round(odenen / R, 3),
                         "devir15": round(h["devir"][15]), "devir_toplam": round(sum(h["devir"].values())),
                         "hasilat": round(R)})
    satirlar.sort(key=lambda s: -s["getiri"])
    return {"en_yuksek": satirlar[:6], "1_ustu_hafta": sum(s["getiri"] > 1 for s in satirlar), "hafta": len(satirlar)}


def hafta_verisi():
    hs = toto.haftalar([toto.ozet(d) for d in toto.donemleri_oku()])
    rows = arsiv.oku(BASLANGIC[:7], "9999")
    gun = defaultdict(list)
    for r in rows:
        gun[r["tarih"]].append(r)
    model = kalibrasyon.model_oku()
    cikti = []
    for h in hs:
        if h["bas"][:10] < BASLANGIC or not h["P"] or len(h["maclar"]) != 15:
            continue
        r = [toto.SECIM_SIRASI.get(m["sonuc"]) for m in h["maclar"]]
        if None in r:
            continue
        es = toto.arsiv_eslestir(h["maclar"], gun)
        p = np.tile(toto.NOTR, (15, 1))
        for i, m in enumerate(h["maclar"]):
            s = es.get(m["no"])
            if s:
                oranlar = {"1": s["o1"], "0": s["o0"], "2": s["o2"]}
                olas = (kalibrasyon.olasiliklar(model, "MS", oranlar, sonuc.lig_anahtari(s["ulke"], s["lig_kodu"]))
                        or kalibrasyon.normallestir(oranlar))
                p[i] = [olas["1"], olas["0"], olas["2"]]
        if 15 - len(es) <= 1:
            cikti.append({**h, "p": p, "r": r, "eksik": 15 - len(es)})
    return hs, cikti


def sistem(p, t):
    S = (p >= t).astype(float)
    S[np.arange(15), p.argmax(axis=1)] = 1
    return S / S.sum(axis=1, keepdims=True), int(np.prod(S.sum(axis=1)))


STRATEJILER = {
    "olasılık": lambda p: (p, None),
    "tek favori": lambda p: (np.eye(3)[p.argmax(axis=1)], 1),
    "sistem p≥0.27": lambda p: sistem(p, 0.27),
    "sistem p≥0.25": lambda p: sistem(p, 0.25),
    "eşit rastgele": lambda p: (np.full((15, 3), 1 / 3), None),
}


def ozetle(degerler, rng):
    v = np.array([sum(x.values()) for x in degerler])
    alt = np.array([x[12] + x[13] + x[14] for x in degerler])
    bs = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(3000)]
    return {"hafta": len(v), "getiri": round(float(v.mean()), 3),
            "aralik90": [round(float(np.percentile(bs, 5)), 3), round(float(np.percentile(bs, 95)), 3)],
            "medyan_hafta": round(float(np.median(v)), 3), "12_14_kismi": round(float(alt.mean()), 3),
            "15_kismi": round(float(np.mean([x[15] for x in degerler])), 3)}


def stratejiler(veri, rng):
    cikti = {}
    for ad, f in STRATEJILER.items():
        satir = {}
        for donem, (a, b) in {"hepsi": (BASLANGIC, "9999"), **DONEMLER}.items():
            sec = [h for h in veri if a <= h["bas"][:10] < b]
            satir[donem] = ozetle([toto.gerceklesen_getiri(f(h["p"])[0], h) for h in sec], rng)
        boy = [f(h["p"])[1] for h in veri]
        if boy[0] is not None:
            satir["kolon_medyan"] = int(np.median(boy))
        cikti[ad] = satir
    devirli = [h for h in veri if h["devir"][15] > 0]
    devirsiz = [h for h in veri if h["devir"][15] == 0]
    cikti["olasılık"]["devredenli"] = ozetle([toto.gerceklesen_getiri(h["p"], h) for h in devirli], rng)
    cikti["olasılık"]["devredensiz"] = ozetle([toto.gerceklesen_getiri(h["p"], h) for h in devirsiz], rng)
    return cikti


def yil_benzetimi(veri, K, rng, hafta=52, tekrar=4000):
    """Haftada K kolon (olasılıkla doldurulmuş), 52 hafta; geçmiş haftalardan yeniden örnekleme. TL, bugünkü 10 TL."""
    H = []
    for h in veri:
        d = toto.kacirma_dagilimi(h["p"][np.arange(15), h["r"]][None, :])[0]
        olcek = toto.KOLON_FIYATI / toto.fiyat(h["bas"][:10])
        odeme = np.array([toto.net_ikramiye(h["havuz"][15 - m] / (h["dereceler"][15 - m]["kazanan"] + 1) * olcek)
                          for m in range(4)])
        H.append((np.append(d, 1 - d.sum()), odeme))
    net = np.zeros(tekrar)
    for t in range(tekrar):
        top = 0.0
        for i in rng.integers(0, len(H), hafta):
            n = rng.multinomial(K, H[i][0])
            top += float((n[:4] * H[i][1]).sum())
        net[t] = top - K * toto.KOLON_FIYATI * hafta
    return {"haftalik_kolon": K, "yillik_maliyet": K * toto.KOLON_FIYATI * hafta, "ortalama_net": round(float(net.mean())),
            "medyan_net": round(float(np.median(net))), "kar_olasiligi": round(float((net > 0).mean()), 3),
            "yuzde10": round(float(np.percentile(net, 10))), "yuzde90": round(float(np.percentile(net, 90)))}


def main():
    rng = np.random.default_rng(7)
    hs, veri = hafta_verisi()
    sonuc_ = {"olusturma": date.today().isoformat(), "gecmis": gecmis_ozeti(hs),
              "ortalama_oyuncu": ortalama_oyuncu(hs), "stratejiler": stratejiler(veri, rng),
              "yil": [yil_benzetimi(veri, K, rng) for K in (10, 100, 250, 1000)]}
    yol = depo.kok() / "analiz" / "toto.json"
    yol.write_text(json.dumps(sonuc_, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(sonuc_, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
