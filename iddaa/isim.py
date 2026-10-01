"""Takım adı eşleştirme: farklı kaynaklardaki adlar (İngilizce/Türkçe, kısaltmalı) için kaba benzerlik."""
import re
import unicodedata
from difflib import SequenceMatcher

GURULTU = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "fk", "sk", "cd", "ud", "rc", "rcd", "sd", "real", "club",
           "de", "town", "city", "united", "utd", "the", "1", "sv", "vfb", "vfl", "tsg", "fsv", "bk", "if", "kv",
           "krc", "ogc", "aj", "sco", "stade", "olympique", "spor", "kulubu", "calcio", "sl", "1907", "1910", "1919",
           "04", "05"}


def norm(ad: str) -> str:
    ad = unicodedata.normalize("NFKD", (ad or "").replace("İ", "I").replace("ı", "i")).encode("ascii", "ignore")
    ad = re.sub(r"[^a-z0-9 ]", " ", ad.decode().lower())
    kelimeler = [k for k in ad.split() if k not in GURULTU]
    return " ".join(kelimeler) or ad.strip()


def benzerlik(a: str, b: str) -> float:
    """0..1: aynı takım olma benzerliği (biri diğerini içeriyorsa ya da ortak kelime varsa yüksek)."""
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.95
    oran = SequenceMatcher(None, a, b).ratio()
    if set(a.split()) & set(b.split()):
        oran = max(oran, 0.8)
    return oran


def en_iyi_eslesme(ev: str, dep: str, adaylar: list[tuple], esik: float = 1.2, fark: float = 0.2):
    """adaylar: [(ev, dep, nesne)] -> en benzer nesne; iki takımın benzerlik toplamı eşiği geçmeli ve ikinciden
    belirgin şekilde iyi olmalı. Yoksa None."""
    puanli = sorted(((benzerlik(ev, a) + benzerlik(dep, b), n) for a, b, n in adaylar), key=lambda x: -x[0])
    if not puanli or puanli[0][0] < esik or (len(puanli) > 1 and puanli[1][0] > puanli[0][0] - fark):
        return None
    return puanli[0][1]
