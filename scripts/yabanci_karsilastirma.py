"""iddaa ile yabancı piyasa karşılaştırması (2019-2026, 22 Avrupa ligi).

1) football-data.co.uk maçlarını Mackolik arşivindeki iddaa maçlarıyla eşleştirir (lig, tarih ±1 gün, İY ve MS skoru, takım adı benzerliği).
2) Beklenen dönüş = iddaa Kral oranı (Mackolik oranı × 1.04) × yabancı piyasanın adil olasılığı (Pinnacle kapanış, yoksa piyasa
   ortalaması; kâr payı ayıklanmış). Beklenen dönüş dilimlerine göre gerçekte 1 TL ne döndürdü.
Çalıştırma: python scripts/yabanci_karsilastirma.py   (data/arsiv ve data/gecmis gerekir)
"""
import sys, math, unicodedata, re, pickle
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
sys.path.insert(0, '/home/claude/iddaa-analiz')
from iddaa import arsiv, gecmis

LIG = {"E0": "İNP", "E1": "İNCL", "E2": "İN1", "E3": "İN2", "EC": "İBSL", "SC0": "İKP", "SC1": "İKCL", "SC2": "İK1",
       "SC3": "İK2", "D1": "AL1", "D2": "AL2", "I1": "İTA", "I2": "İTB", "SP1": "İS1", "SP2": "İS2", "F1": "FR1",
       "F2": "FR2", "N1": "HOL", "B1": "BEL", "P1": "POR", "T1": "TSL", "G1": "YUN"}
GURULTU = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "fk", "sk", "cd", "ud", "rc", "rcd", "sd", "real", "club",
           "de", "town", "city", "united", "utd", "the", "1", "sv", "vfb", "vfl", "tsg", "fsv", "bk", "if", "kv",
           "krc", "ogc", "aj", "sco", "stade", "olympique", "spor", "kulubu", "calcio", "1907", "1910", "1919", "04", "05"}

def norm(ad):
    ad = unicodedata.normalize("NFKD", ad.replace("İ", "I").replace("ı", "i")).encode("ascii", "ignore").decode().lower()
    ad = re.sub(r"[^a-z0-9 ]", " ", ad)
    kel = [k for k in ad.split() if k not in GURULTU]
    return " ".join(kel) or ad.strip()

def benzerlik(a, b):
    a, b = norm(a), norm(b)
    if not a or not b: return 0
    if a in b or b in a: return 0.95
    r = SequenceMatcher(None, a, b).ratio()
    ka, kb = set(a.split()), set(b.split())
    if ka & kb: r = max(r, 0.8)
    return r

mk = defaultdict(list)
for m in arsiv.oku('2019-08', '9999'):
    if m['lig_kodu'] in LIG.values():
        mk[(m['lig_kodu'], m['tarih'])].append(m)
fd = [x for x in gecmis.oku() if x['tarih'] >= '2019-08-01' and x['lig'] in LIG]
eslesen, kotu = [], 0
for x in fd:
    adaylar = []
    for fark in (0, 1, -1):
        g = (date.fromisoformat(x['tarih']) + timedelta(days=fark)).isoformat()
        for m in mk.get((LIG[x['lig']], g), []):
            if (m['ms_ev'], m['ms_dep'], m['iy_ev'], m['iy_dep']) != (x['ms_ev'], x['ms_dep'], x['iy_ev'], x['iy_dep']):
                continue
            s = benzerlik(x['ev'], m['ev']) + benzerlik(x['dep'], m['dep'])
            adaylar.append((s, fark != 0, m))
    if not adaylar:
        kotu += 1; continue
    adaylar.sort(key=lambda a: (-a[0], a[1]))
    s, _, m = adaylar[0]
    if s < 1.2 or (len(adaylar) > 1 and adaylar[1][0] > s - 0.2):
        kotu += 1; continue
    eslesen.append((x, m))
print('football-data maç', len(fd), 'eşleşen', len(eslesen), 'eşleşmeyen', kotu)


es = eslesen
K = 1.04
def adil(o):
    t = sum(1/x for x in o.values()); return {s: (1/x)/t for s, x in o.items()}
def sonuc(x):
    return '1' if x['ms_ev'] > x['ms_dep'] else '2' if x['ms_dep'] > x['ms_ev'] else '0'
kayit = []  # (yil, lig, market, secim, kral_oran, p_adil, tuttu, kaynak)
for x, m in es:
    yil = x['tarih'][:4]
    ido = {s: m['o' + s] for s in '102'}
    if all(ido.values()) and min(ido.values()) > 1.0:
        if x['ps_1'] and x['ps_0'] and x['ps_2']:
            ref, kay = {s: x['ps_' + s] for s in '102'}, 'pinnacle'
        else:
            ref, kay = {s: x['ort_' + s] for s in '102'}, 'ortalama'
        if all(ref.values()):
            p = adil(ref); g = sonuc(x)
            for s in '102':
                kayit.append((yil, x['lig'], 'MS', s, ido[s] * K, p[s], s == g, kay))
    if m['alt25'] and m['ust25'] and x['ort_ust25'] and x['ort_alt25']:
        p = adil({'Üst': x['ort_ust25'], 'Alt': x['ort_alt25']})
        g = 'Üst' if x['ms_ev'] + x['ms_dep'] > 2.5 else 'Alt'
        for s, o in (('Üst', m['ust25']), ('Alt', m['alt25'])):
            kayit.append((yil, x['lig'], 'AÜ2.5', s, o * K, p[s], s == g, 'ortalama'))

print('seçim', len(kayit))

def ozet(liste):
    n = len(liste); t = sum(r[6] for r in liste); d = sum(r[4] for r in liste if r[6])
    if not n: return '-'
    hp = 1.96 * math.sqrt(sum((r[4] * r[6] - d / n) ** 2 for r in liste) / n / n)
    return f"n={n:>7} tuttu=%{100*t/n:5.1f} 1TL->{d/n:.3f} ±{hp:.3f}"

DIL = [(0, .85), (.85, .9), (.9, .95), (.95, 1.0), (1.0, 1.03), (1.03, 1.06), (1.06, 1.1), (1.1, 9)]
for market in ('MS', 'AÜ2.5'):
    for kay in (('pinnacle',) if market == 'MS' else ()) + ('hepsi',):
        alt = [r for r in kayit if r[2] == market and (kay == 'hepsi' or r[7] == kay)]
        print(f"\n== {market} referans={kay}  (beklenen = iddaa Kral oranı × adil olasılık)")
        for a, b in DIL:
            print(f"  {a:.2f}-{b:.2f}: ", ozet([r for r in alt if a <= r[4] * r[5] < b]))
