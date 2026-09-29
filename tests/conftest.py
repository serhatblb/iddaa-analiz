import pytest


def iyms_market(oranlar: dict) -> dict:
    return {"i": 900, "t": 2, "st": 90, "s": 1,
            "o": [{"no": i + 1, "odd": o, "wodd": round(o * 0.96, 2), "n": s}
                  for i, (s, o) in enumerate(oranlar.items())]}


def mac(mac_id, d, ev="Ev FK", dep="Dep FK", ci=10, iyms=None, canli=False):
    marketler = [
        {"i": 100 + mac_id, "t": 1, "st": 1, "s": 1,
         "o": [{"no": 1, "odd": 1.9, "n": "1"}, {"no": 2, "odd": 3.3, "n": "0"}, {"no": 3, "odd": 4.1, "n": "2"}]},
        {"i": 200 + mac_id, "t": 2, "st": 101, "sov": "2.5", "s": 1,
         "o": [{"no": 1, "odd": 1.8, "n": "Alt"}, {"no": 2, "odd": 1.9, "n": "Üst"}]},
        {"i": 300 + mac_id, "t": 4, "st": 14, "sov": "3.5", "s": 1,
         "o": [{"no": 1, "odd": 2.8, "n": "Alt"}, {"no": 2, "odd": 1.2, "n": "Üst"}]},
    ]
    if iyms:
        marketler.append(iyms_market(iyms))
    return {"i": mac_id, "hn": ev, "an": dep, "ci": ci, "d": d, "il": canli, "m": marketler}


class SahteIstemci:
    def __init__(self, maclar=None, son_maclar=None):
        self.maclar = {m["i"]: m for m in (maclar or [])}
        self._son_maclar = son_maclar or {}
        self.istek_sayisi = 0
        self.detay_istekleri = []

    def _say(self):
        self.istek_sayisi += 1

    def bulten(self, canli=False):
        self._say()
        # Listede İY/MS bazen eksik gelir: listede sadece ilk 2 market
        return {"events": [{**m, "m": m["m"][:2]} for m in self.maclar.values()]}

    def mac(self, mac_id):
        self._say()
        self.detay_istekleri.append(mac_id)
        return self.maclar.get(mac_id)

    def market_ayarlari(self):
        self._say()
        return {"m": {"2_90": {"n": "1. Yarı / Maç Sonucu"}, "1_1": {"n": "Maç Sonucu"}}}

    def ligler(self):
        self._say()
        return [{"i": 10, "cid": "TR", "n": "Süper Lig", "sn": "TSL", "si": "1"},
                {"i": 99, "cid": "INT", "n": "F1", "sn": "F1", "si": "11"}]

    def secenek_oynanma(self):
        self._say()
        return {str(i): {"900": {"1": 12.5, "7": 3.1}} for i in self.maclar}

    def mac_oynanma(self):
        self._say()
        return {str(i): 1.5 for i in self.maclar}

    def son_maclar(self, mac_id):
        self._say()
        return self._son_maclar.get(mac_id)


@pytest.fixture
def veri_dizini(tmp_path, monkeypatch):
    monkeypatch.setenv("IDDAA_VERI", str(tmp_path / "data"))
    return tmp_path / "data"
