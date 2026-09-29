from datetime import datetime, timedelta, timezone

from conftest import SahteIstemci, mac

from iddaa import bulten, depo, topla

IYMS_ORANLARI = {"1/1": 3.5, "1/0": 14.0, "1/2": 25.0, "0/1": 5.2, "0/0": 4.3,
                 "0/2": 6.4, "2/1": 31.5, "2/0": 14.6, "2/2": 4.9}
SIMDI = datetime(2026, 9, 30, 7, 7, tzinfo=timezone.utc)


def ts(zaman):
    return int(zaman.timestamp())


def test_iyms_sonucu():
    assert bulten.iyms_sonucu(1, 0, 1, 2) == "1/2"
    assert bulten.iyms_sonucu(0, 1, 2, 1) == "2/1"
    assert bulten.iyms_sonucu(0, 0, 0, 0) == "0/0"


def test_oran_satirlari_canli_marketleri_atlar():
    m = mac(1, ts(SIMDI), iyms=IYMS_ORANLARI)
    satirlar = bulten.oran_satirlari(m, "acilis", SIMDI)
    assert {s["market"] for s in satirlar} == {"1_1", "2_101", "2_90"}
    iyms = bulten.oran_satirlari(m, "saatlik", SIMDI, sadece={"2_90"})
    assert len(iyms) == 9 and {s["secenek"] for s in iyms} == set(IYMS_ORANLARI)


def test_ilk_calisma_acilis_ve_kayit(veri_dizini):
    istemci = SahteIstemci([
        mac(1, ts(SIMDI + timedelta(hours=10)), iyms=IYMS_ORANLARI),
        mac(2, ts(SIMDI + timedelta(hours=10))),
        mac(3, ts(SIMDI - timedelta(minutes=5))),  # başlamış, atlanır
    ])
    ozet = topla.calistir(istemci, SIMDI)
    assert ozet["yeni"] == 2 and ozet["iyms_mac"] == 1
    kayitlar = depo.maclari_oku()
    assert kayitlar["1"]["iyms_var"] == "1" and kayitlar["2"]["iyms_var"] == "0"
    assert kayitlar["1"]["lig"] == "Süper Lig"
    satirlar = depo.gz_csv_oku(depo.anlik_yolu("oranlar", SIMDI))
    assert {s["tip"] for s in satirlar} == {"acilis"}
    assert sum(1 for s in satirlar if s["market"] == "2_90") == 9
    assert depo.anlik_yolu("oynanma/secenek", SIMDI).exists()


def test_saatlik_sadece_iyms_ve_kapanis(veri_dizini):
    istemci = SahteIstemci([
        mac(1, ts(SIMDI + timedelta(hours=10)), iyms=IYMS_ORANLARI),
        mac(2, ts(SIMDI + timedelta(hours=1, minutes=50)), iyms=IYMS_ORANLARI),
        mac(4, ts(SIMDI + timedelta(days=3))),
    ])
    topla.calistir(istemci, SIMDI)
    istemci.detay_istekleri.clear()
    sonraki = SIMDI + timedelta(hours=1)
    ozet = topla.calistir(istemci, sonraki)
    satirlar = depo.gz_csv_oku(depo.anlik_yolu("oranlar", sonraki))
    tipler = {(s["mac_id"], s["tip"]) for s in satirlar}
    assert ("1", "saatlik") in tipler and ("2", "kapanis") in tipler
    assert all(s["market"] == "2_90" for s in satirlar if s["tip"] == "saatlik")
    assert 4 not in istemci.detay_istekleri  # İY/MS'siz ve uzak maç tekrar çekilmez
    assert ozet["kapanis"] == 1
    assert depo.maclari_oku()["2"]["kapanis"] == "1"


def test_iyms_sonradan_acilirsa_yakalanir(veri_dizini):
    m = mac(5, ts(SIMDI + timedelta(hours=20)))
    istemci = SahteIstemci([m])
    topla.calistir(istemci, SIMDI)
    istemci.maclar[5] = mac(5, m["d"], iyms=IYMS_ORANLARI)
    topla.calistir(istemci, SIMDI + timedelta(hours=1))
    assert depo.maclari_oku()["5"]["iyms_var"] == "0"  # 6 saat dolmadan kontrol edilmez
    sonra = SIMDI + timedelta(hours=6)
    topla.calistir(istemci, sonra)
    assert depo.maclari_oku()["5"]["iyms_var"] == "1"
    assert any(s["market"] == "2_90" for s in depo.gz_csv_oku(depo.anlik_yolu("oranlar", sonra)))
