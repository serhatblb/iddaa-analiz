"""Spor Toto: geçmiş dönemler, devreden hesabı ve kolon stratejilerinin gerçekleşen getirisi.

Kurallar (Spor Toto müşterek oyun planı, iddaa.com yardım):
  * 15 maç, her kolon her maç için 1/0/2. Kolon 10 TL (18.03.2025'ten beri); bir kuponda en çok 2.500 kolon.
  * Hasılattan KDV düşülür, kalanın %83'ü ikramiye: 15 bilen %35, 14 bilen %20, 13 bilen %20, 12 bilen %25.
  * Bir derece bilinmezse o derecenin parası bir sonraki oyunun AYNI derecesine devreder.
  * Bir kolon yalnızca en yüksek bildiği dereceden ikramiye alır; derecedeki para kazananlara eşit bölünür.
  * İkramiyenin istisna tutarını (2026: 66.935 TL) aşan kısmından %20 veraset ve intikal vergisi kesilir.

Ortalama kolonun geri dönüşü bu yüzden 0.83 / 1.20 ≈ %69 (devreden hariç).

Veri: sportotov2.iddaa.com (2019'dan bu yana bütün dönemler: maçlar, sonuçlar, derece başına kazanan ve tutar).
Gerçekleşen getiri: bir kolon dağılımı w (her maçta 1/0/2 seçme olasılıkları) için, o haftanın gerçek sonuçları ve
gerçek ikramiyeleriyle, böyle doldurulmuş bir kolonun 1 TL başına beklenen ödemesi. Kalabalığın davranışı modele
gerek kalmadan gerçek kazanan sayılarından gelir.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from . import depo, isim

API = "https://sportotov2.iddaa.com/SporToto"
PAYLAR = {15: 0.35, 14: 0.20, 13: 0.20, 12: 0.25}
KOLON_FIYATI = 10.0
IKRAMIYE_ORANI = 0.83
KDV = 0.20
VERGI_ISTISNA = 66935.0       # 2026 veraset ve intikal vergisi istisnası (ikramiye başına)
VERGI_ORANI = 0.20
SECIM_SIRASI = {"1": 0, "0": 1, "2": 2}
NOTR = np.array([0.45, 0.27, 0.28])   # oranı bulunamayan maç için ortalama 1/0/2 olasılığı

# Kolon fiyatı dönemleri (haber kaynakları: 06.08.2023 2 TL, Ağustos 2024 4 TL, 18.03.2025 10 TL)
FIYATLAR = [("2025-03-18", 10.0), ("2024-08-11", 4.0), ("2023-08-06", 2.0)]

BASLIK = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36",
          "Accept": "application/json, text/plain, */*", "Origin": "https://www.iddaa.com",
          "Referer": "https://www.iddaa.com/"}


def fiyat(gun: str) -> float | None:
    for bas, f in FIYATLAR:
        if gun >= bas:
            return f
    return None


def sayi(metin) -> float:
    """'4.418.640,12' -> 4418640.12"""
    if metin in (None, ""):
        return 0.0
    if isinstance(metin, (int, float)):
        return float(metin)
    return float(str(metin).replace(".", "").replace(",", "."))


def dizin() -> Path:
    return depo.kok() / "toto"


def donemleri_oku(yol: Path | None = None) -> list[dict]:
    yol = yol or dizin() / "donemler.jsonl"
    if not yol.exists():
        return []
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines() if s.strip()]


def guncelle(oturum=None) -> dict:
    """Eksik sonuçlanmış dönemleri ve güncel programı indir (iddaa'ya erişen yerde, ör. GitHub Actions)."""
    import requests
    oturum = oturum or requests.Session()

    def getir(url, params=None):
        for deneme in range(3):
            try:
                y = oturum.get(url, params=params, headers=BASLIK, timeout=30)
                if y.status_code == 200:
                    return (y.json() or {}).get("data")
            except (requests.RequestException, ValueError):
                pass
            time.sleep(2 + 3 * deneme)
        return None

    dizin().mkdir(parents=True, exist_ok=True)
    guncel = getir(API)
    if not guncel:
        return {"durum": "erişilemedi"}
    (dizin() / "guncel.json").write_text(json.dumps(guncel, ensure_ascii=False, indent=1), encoding="utf-8")
    var = {d["gameCycleNo"] for d in donemleri_oku()}
    yeni = 0
    with open(dizin() / "donemler.jsonl", "a", encoding="utf-8") as f:
        for no in range(1, guncel["gameCycleNo"]):
            if no in var:
                continue
            d = getir(f"{API}/result", {"gameCycleNo": no})
            if d and d.get("dividends") and all(e.get("winner") for e in d.get("events") or []):
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
                yeni += 1
            time.sleep(0.3)
    return {"durum": "tamam", "guncel": guncel["gameCycleNo"], "yeni": yeni}


def sonuc_kodu(winner) -> str | None:
    w = str(winner or "").strip().upper()
    return {"1": "1", "0": "0", "X": "0", "2": "2"}.get(w)


def ozet(d: dict) -> dict:
    """Bir dönemin dereceleri: {15: {"kazanan", "tutar"}, ...} + maçlar."""
    dereceler = {}
    for x in d.get("dividends") or []:
        k = 16 - int(x["ordinalNumber"])
        dereceler[k] = {"kazanan": int(sayi(x["winners"])), "tutar": sayi(x["amount"])}
    maclar = [{"no": e["eventNo"], "ad": e["eventName"], "lig": e.get("competitionName"), "tarih": e.get("eventDate"),
               "sonuc": sonuc_kodu(e.get("winner"))} for e in d.get("events") or []]
    return {"no": d["gameCycleNo"], "program": d.get("programName"), "bas": d.get("payinBeginDate"),
            "bitis": d.get("payinEndDate"), "dereceler": dereceler, "maclar": sorted(maclar, key=lambda m: m["no"])}


def haftalar(donemler: list[dict]) -> list[dict]:
    """Dönem özetlerine (ozet) haftalık yeni ikramiye parası P, derece başına devreden ve havuz ekler.

    Devreden özyinelemeli kurulur: bir derecede kazanan çıkmazsa o derecenin havuzu (devreden + pay × P) bir sonraki
    haftaya geçer. (API kazanansız derecede tutarı çoğu zaman 0 gösterdiği için oradan okunamaz.)
    P, kazananı olan en düşük dereceden: (kazanan × tutar − devreden) / pay."""
    cikti = []
    devir = {k: 0.0 for k in PAYLAR}
    for o in sorted(donemler, key=lambda x: x["no"]):
        d = o["dereceler"]
        P = None
        for k in (12, 13, 14, 15):
            if d.get(k, {}).get("kazanan"):
                P = (d[k]["kazanan"] * d[k]["tutar"] - devir[k]) / PAYLAR[k]
                break
        havuz = {k: devir[k] + PAYLAR[k] * (P or 0.0) for k in PAYLAR}
        cikti.append({**o, "P": P, "devir": dict(devir), "havuz": havuz})
        for k in PAYLAR:
            devir[k] = havuz[k] if not d.get(k, {}).get("kazanan") else 0.0
    return cikti


def hasilat(P: float) -> float:
    """Haftalık yeni ikramiye parasından toplam hasılat (KDV dahil)."""
    return P * (1 + KDV) / IKRAMIYE_ORANI


def net_ikramiye(tutar: float) -> float:
    return tutar - VERGI_ORANI * max(0.0, tutar - VERGI_ISTISNA)


# --- isim eşleştirme (Toto maçı <-> Mackolik arşivindeki iddaa oranlı maç) ---

TAKMA_AD = {"Paris Saint Germain": "PSG", "Paris Saint-Germain": "PSG", "Paris SG": "PSG"}
GENC_KADIN = re.compile(r"\(K\)|\bU ?\d{2}\b|\bII\b|\bB$|\bKadın|\bGençler")
TEMIZLE = [" A.Ş.", " A.Ş", " AŞ", " A.S.", " Sportif Faaliyetler", " Futbol Kulübü", " FUTBOL KULÜBÜ"]


def _temiz(ad: str) -> str:
    for t in TEMIZLE:
        ad = ad.replace(t, "").replace(t.upper(), "")
    ad = ad.strip(" -.")
    return TAKMA_AD.get(ad, ad)


def takimlar_adaylari(mac_adi: str) -> list[tuple[str, str]]:
    """'Ev-Dep' veya 'Ev - Dep' adını takımlara ayırmanın olası yolları (takım adında da '-' olabilir)."""
    if " - " in mac_adi:
        a, b = mac_adi.split(" - ", 1)
        return [(_temiz(a), _temiz(b))]
    parcalar = mac_adi.split("-")
    return [(_temiz("-".join(parcalar[:i])), _temiz("-".join(parcalar[i:]))) for i in range(1, len(parcalar))]


def _yakin(a: str, b: str) -> bool:
    """Hızlı ön eleme: ortak kelime ya da aynı ilk 4 harf."""
    na, nb = isim.norm(a), isim.norm(b)
    return bool(set(na.split()) & set(nb.split())) or (na[:4] == nb[:4] and len(na) >= 4)


def arsiv_eslestir(maclar: list[dict], arsiv_gunleri: dict[str, list[dict]]) -> dict[int, dict]:
    """Toto maçlarını Mackolik arşivindeki (iddaa oranlı) maçlarla eşleştir: {maç no: arşiv satırı}.
    Aynı gün ±1, iki takımın da benzerliği ≥ 0.5, aynı başlama saatine ek puan; ikinci aday yakınsa eşleşme yok."""
    cikti = {}
    for m in maclar:
        if not m.get("tarih"):
            continue
        zaman = datetime.fromisoformat(m["tarih"][:19])
        genc = bool(GENC_KADIN.search(m["ad"]))
        adaylar = []
        for fark in (0, -1, 1):
            for s in arsiv_gunleri.get((zaman.date() + timedelta(days=fark)).isoformat(), []):
                if not (s.get("o1") and s.get("o0") and s.get("o2")):
                    continue
                if not genc and (GENC_KADIN.search(s["ev"]) or GENC_KADIN.search(s["dep"])):
                    continue
                try:
                    ayni_saat = abs(datetime.fromisoformat(f"{s['tarih']}T{s['saat']}") - zaman) <= timedelta(minutes=20)
                except ValueError:
                    ayni_saat = False
                adaylar.append((s["ev"], s["dep"], s, 0.3 if ayni_saat else 0.0))
        en_iyi, puan = None, 0.0
        for ev, dep in takimlar_adaylari(m["ad"]):
            puanli = []
            for a, b, n, bonus in adaylar:
                if _yakin(ev, a) or _yakin(dep, b):
                    b1, b2 = isim.benzerlik(ev, a), isim.benzerlik(dep, b)
                    if min(b1, b2) >= 0.5:
                        puanli.append((b1 + b2 + bonus, n))
            puanli.sort(key=lambda x: -x[0])
            if not puanli or puanli[0][0] < 1.3 or (len(puanli) > 1 and puanli[1][0] > puanli[0][0] - 0.2):
                continue
            if puanli[0][0] > puan:
                en_iyi, puan = puanli[0][1], puanli[0][0]
        if en_iyi:
            cikti[m["no"]] = en_iyi
    return cikti


# --- olasılık hesapları ---

def kacirma_dagilimi(olas: np.ndarray, en_cok: int = 3) -> np.ndarray:
    """olas: (S, n) her maçta doğru bilme olasılığı -> (S, en_cok+1): tam m maç kaçırma olasılığı (m = 0..en_cok).
    15 maçta m = 0, 1, 2, 3 sırasıyla 15, 14, 13, 12 bilmek."""
    olas = np.atleast_2d(olas)
    dag = np.zeros((olas.shape[0], en_cok + 1))
    dag[:, 0] = 1.0
    for i in range(olas.shape[1]):
        p = olas[:, i:i + 1]
        dag[:, 1:] = dag[:, 1:] * p + dag[:, :-1] * (1 - p)
        dag[:, 0] *= p[:, 0]
    return dag


def gerceklesen_getiri(w: np.ndarray, hafta: dict, kolon_fiyati: float | None = None,
                       vergi: bool = True) -> dict[int, float]:
    """w (15, 3) dağılımıyla doldurulan bir kolonun o haftaki 1 TL başına beklenen ödemesi, derece derece.
    Sonuçlar ve kazanan sayıları gerçek; bizim kolon da kazanırsa havuz (kazanan + 1)'e bölünür, kazanan yoksa
    havuzun (devreden dahil) tamamı bizim. hafta: haftalar() satırı + "r" (15 sonuç indeksi)."""
    kolon_fiyati = kolon_fiyati or fiyat(hafta["bas"][:10])
    d = kacirma_dagilimi(w[np.arange(15), hafta["r"]][None, :])[0]
    cikti = {}
    for m in range(4):
        k = 15 - m
        pay = hafta["havuz"][k] / (hafta["dereceler"][k]["kazanan"] + 1)
        cikti[k] = d[m] * (net_ikramiye(pay) if vergi else pay) / kolon_fiyati
    return cikti


def kolon_uret(p: np.ndarray, adet: int, rng: np.random.Generator | None = None) -> list[str]:
    """Her maçı iddaa olasılığıyla rastgele doldurulmuş, birbirinden farklı kolonlar ('1', '0', '2' dizileri)."""
    rng = rng or np.random.default_rng()
    p = p / p.sum(axis=1, keepdims=True)
    kolonlar: dict[str, None] = {}
    for _ in range(adet * 50):
        if len(kolonlar) >= adet:
            break
        secim = [int(rng.choice(3, p=p[i])) for i in range(len(p))]
        kolonlar["".join("102"[s] for s in secim)] = None
    return list(kolonlar)
