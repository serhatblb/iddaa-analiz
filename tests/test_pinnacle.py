from datetime import datetime, timedelta, timezone

from conftest import SahteIstemci, mac

from iddaa import isim, pinnacle, topla

SIMDI = datetime(2026, 10, 3, 7, 0, tzinfo=timezone.utc)  # 10:00 TR


class SahteApi:
    def __init__(self, olaylar, oranlar, kalan=300):
        self.olaylar, self.oranlar, self.kalan, self.istekler = olaylar, oranlar, kalan, []

    def getir(self, yol, **params):
        self.istekler.append(yol)
        if yol == "/sports":
            return [{"key": "soccer_epl", "group": "Soccer", "active": True, "has_outrights": False},
                    {"key": "soccer_spain_la_liga", "group": "Soccer", "active": True, "has_outrights": False},
                    {"key": "basketball_nba", "group": "Basketball", "active": True, "has_outrights": False}]
        if yol.endswith("/events"):
            return self.olaylar.get(yol.split("/")[2], [])
        if yol.endswith("/odds"):
            self.kalan -= 1
            return self.oranlar.get(yol.split("/")[2], [])
        raise AssertionError(yol)


def _olay(oid, ev, dep, bas, o1, o0, o2):
    return {"id": oid, "commence_time": bas.strftime("%Y-%m-%dT%H:%M:%SZ"), "home_team": ev, "away_team": dep,
            "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": ev, "price": o1}, {"name": "Draw", "price": o0}, {"name": dep, "price": o2}]}]}]}


def test_isim_eslesme():
    assert isim.benzerlik("Sl Benfica", "Benfica") >= 0.95
    assert isim.benzerlik("Bayern Münih", "Bayern Munich") >= 0.8
    assert isim.benzerlik("Almanya", "Germany") >= 0.95 and isim.benzerlik("Çekya", "Czech Republic") >= 0.95
    assert isim.benzerlik("Almanya", "Spain") < 0.6
    adaylar = [("Manchester United", "Chelsea", 1), ("Manchester City", "Arsenal", 2)]
    assert isim.en_iyi_eslesme("Man City", "Arsenal FC", adaylar) == 2
    assert isim.en_iyi_eslesme("Liverpool", "Everton", adaylar) is None


def test_pinnacle_gunluk_karsilastirma(veri_dizini):
    bas = SIMDI + timedelta(hours=8)
    m = mac(1, int(bas.timestamp()), ev="Manchester City", dep="Arsenal")
    m["m"][0]["o"] = [{"no": 1, "odd": 2.10, "n": "1"}, {"no": 2, "odd": 3.3, "n": "0"}, {"no": 3, "odd": 3.2, "n": "2"}]
    topla.calistir(SahteIstemci([m]), SIMDI - timedelta(minutes=30))
    olay = _olay("e1", "Manchester City", "Arsenal", bas, 1.95, 3.9, 4.2)
    api = SahteApi({"soccer_epl": [olay]}, {"soccer_epl": [olay]})
    ozet = pinnacle.calistir(SIMDI, api=api)
    assert ozet["eslesen"] == 1 and ozet["kredi"] == 1 and ozet["lig"] == 1
    assert sum(1 for y in api.istekler if y.endswith("/odds")) == 1  # eşleşmeyen lige kredi harcanmaz
    p = pinnacle.adil({"1": 1.95, "0": 3.9, "2": 4.2})
    firsat = pinnacle.firsatlar("2026-10-03")
    assert [f["secim"] for f in firsat] == ["1"] and abs(firsat[0]["beklenen"] - round(2.10 * p["1"], 4)) < 1e-9
    assert pinnacle.calistir(SIMDI + timedelta(hours=1), api=api)["durum"] == "bugün alındı"
    assert pinnacle.calistir(SIMDI, anahtar="")["durum"] == "anahtar yok"


def test_gunluk_kredi():
    from datetime import date
    assert pinnacle.gunluk_kredi(300, date(2026, 10, 1)) == 9      # 31 gün
    assert pinnacle.gunluk_kredi(5, date(2026, 10, 31)) == 5
    assert pinnacle.gunluk_kredi(0, date(2026, 10, 15)) == 1


def test_pinnacle_panel_ve_mail(veri_dizini):
    from iddaa import panel, rapor
    bas = SIMDI + timedelta(hours=8)
    m = mac(1, int(bas.timestamp()), ev="Manchester City", dep="Arsenal")
    m["m"][0]["o"] = [{"no": 1, "odd": 2.10, "n": "1"}, {"no": 2, "odd": 3.3, "n": "0"}, {"no": 3, "odd": 3.2, "n": "2"}]
    topla.calistir(SahteIstemci([m]), SIMDI - timedelta(minutes=30))
    olay = _olay("e1", "Manchester City", "Arsenal", bas, 1.95, 3.9, 4.2)
    pinnacle.calistir(SIMDI, api=SahteApi({"soccer_epl": [olay]}, {"soccer_epl": [olay]}))
    sayfa, _ = panel.olustur(SIMDI)
    assert "Deneme: iddaa &gt; Pinnacle" in sayfa and "Manchester City" in sayfa
    metin = "\n".join(rapor.olustur(SIMDI).md)
    assert "Pinnacle 1.95" in metin
