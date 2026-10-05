"""Takım adı eşleştirme: farklı kaynaklardaki adlar (İngilizce/Türkçe, kısaltmalı) için kaba benzerlik."""
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

GURULTU = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "fk", "sk", "cd", "ud", "rc", "rcd", "sd", "real", "club",
           "de", "town", "city", "united", "utd", "the", "1", "sv", "vfb", "vfl", "tsg", "fsv", "bk", "if", "kv",
           "krc", "ogc", "aj", "sco", "stade", "olympique", "spor", "kulubu", "calcio", "sl", "1907", "1910", "1919",
           "04", "05"}


# iddaa milli takımları Türkçe yazıyor; yabancı kaynaklar İngilizce
ULKELER = {
    "almanya": "germany", "ispanya": "spain", "italya": "italy", "fransa": "france", "ingiltere": "england",
    "hollanda": "netherlands", "belcika": "belgium", "portekiz": "portugal", "isvicre": "switzerland",
    "avusturya": "austria", "danimarka": "denmark", "isvec": "sweden", "norvec": "norway", "finlandiya": "finland",
    "izlanda": "iceland", "irlanda": "republic of ireland", "kuzey irlanda": "northern ireland", "iskocya": "scotland",
    "galler": "wales", "polonya": "poland", "cekya": "czech republic", "cek cumhuriyeti": "czech republic",
    "slovakya": "slovakia", "macaristan": "hungary", "romanya": "romania", "bulgaristan": "bulgaria",
    "yunanistan": "greece", "sirbistan": "serbia", "hirvatistan": "croatia", "slovenya": "slovenia",
    "bosna hersek": "bosnia and herzegovina", "karadag": "montenegro", "arnavutluk": "albania",
    "kuzey makedonya": "north macedonia", "kosova": "kosovo", "ukrayna": "ukraine", "rusya": "russia",
    "beyaz rusya": "belarus", "turkiye": "turkey", "gurcistan": "georgia", "ermenistan": "armenia",
    "azerbaycan": "azerbaijan", "kazakistan": "kazakhstan", "israil": "israel", "kibris": "cyprus", "malta": "malta",
    "lihtenstayn": "liechtenstein", "luksemburg": "luxembourg", "andorra": "andorra", "san marino": "san marino",
    "cebelitarik": "gibraltar", "faroe adalari": "faroe islands", "estonya": "estonia", "letonya": "latvia",
    "litvanya": "lithuania", "moldova": "moldova", "abd": "usa", "meksika": "mexico", "kanada": "canada",
    "brezilya": "brazil", "arjantin": "argentina", "uruguay": "uruguay", "kolombiya": "colombia", "sili": "chile",
    "peru": "peru", "ekvador": "ecuador", "paraguay": "paraguay", "bolivya": "bolivia", "venezuela": "venezuela",
    "japonya": "japan", "guney kore": "south korea", "cin": "china", "avustralya": "australia",
    "suudi arabistan": "saudi arabia", "iran": "iran", "katar": "qatar", "misir": "egypt", "fas": "morocco",
    "cezayir": "algeria", "tunus": "tunisia", "nijerya": "nigeria", "gana": "ghana", "senegal": "senegal",
    "kamerun": "cameroon", "fildisi sahili": "ivory coast", "guney afrika": "south africa",
}


def _ascii(ad: str) -> str:
    ad = unicodedata.normalize("NFKD", (ad or "").replace("İ", "I").replace("ı", "i")).encode("ascii", "ignore")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", ad.decode().lower())).strip()


@lru_cache(maxsize=200_000)
def norm(ad: str) -> str:
    duz = _ascii(ad)
    for sonek in (" u21", " u19", " u23", " k"):
        if duz.endswith(sonek) and duz[: -len(sonek)] in ULKELER:
            duz = ULKELER[duz[: -len(sonek)]] + sonek
            break
    else:
        duz = ULKELER.get(duz, duz)
    ad = duz
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
