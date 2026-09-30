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


def test_saatlik_sadece_degisen_marketler_ve_kapanis(veri_dizini):
    istemci = SahteIstemci([
        mac(1, ts(SIMDI + timedelta(hours=10)), iyms=IYMS_ORANLARI),
        mac(2, ts(SIMDI + timedelta(hours=1, minutes=50)), iyms=IYMS_ORANLARI),
        mac(4, ts(SIMDI + timedelta(days=3))),
    ])
    topla.calistir(istemci, SIMDI)
    istemci.detay_istekleri.clear()
    # Bir saat sonra: 1. maçta İY/MS 2/1 değişti (detaydan), 4. maçta MS değişti (listeden)
    istemci.maclar[1]["m"][3]["o"][6]["odd"] = 29.0
    istemci.maclar[4]["m"][0]["o"][0]["odd"] = 2.05
    sonraki = SIMDI + timedelta(hours=1)
    ozet = topla.calistir(istemci, sonraki)
    satirlar = depo.gz_csv_oku(depo.anlik_yolu("oranlar", sonraki))
    saatlik = {(s["mac_id"], s["market"]) for s in satirlar if s["tip"] == "saatlik"}
    assert saatlik == {("1", "2_90"), ("4", "1_1")}
    assert sum(1 for s in satirlar if s["tip"] == "saatlik" and s["mac_id"] == "1") == 9  # marketin tamamı
    assert ("2", "kapanis") in {(s["mac_id"], s["tip"]) for s in satirlar}
    assert 4 not in istemci.detay_istekleri  # İY/MS'siz ve uzak maç tekrar çekilmez
    assert ozet["kapanis"] == 1 and ozet["saatlik_satir"] == 12
    assert depo.maclari_oku()["2"]["kapanis"] == "1"
    # Hiçbir şey değişmezse saatlik satır yazılmaz
    ucuncu = SIMDI + timedelta(hours=2)
    assert topla.calistir(istemci, ucuncu)["saatlik_satir"] == 0


def test_mbs_kaydedilir(veri_dizini):
    m = mac(6, ts(SIMDI + timedelta(hours=10)))
    m["mbc"], m["kOdd"] = 3, True
    m["m"][0]["mbc"] = 1
    istemci = SahteIstemci([m])
    topla.calistir(istemci, SIMDI)
    assert (depo.maclari_oku()["6"]["mbs"], depo.maclari_oku()["6"]["kral"]) == ("3", "1")
    ms = [s for s in depo.gz_csv_oku(depo.anlik_yolu("oranlar", SIMDI)) if s["market"] == "1_1"]
    assert {s["mbs"] for s in ms} == {"1"}
    istemci.maclar[6]["mbc"] = 1
    topla.calistir(istemci, SIMDI + timedelta(hours=1))
    assert depo.maclari_oku()["6"]["mbs"] == "1"


def test_iyms_sonradan_acilirsa_yakalanir(veri_dizini):
    m = mac(5, ts(SIMDI + timedelta(hours=20)))
    istemci = SahteIstemci([m])
    topla.calistir(istemci, SIMDI)
    istemci.maclar[5] = mac(5, m["d"], iyms=IYMS_ORANLARI)
    topla.calistir(istemci, SIMDI + timedelta(hours=1))
    assert depo.maclari_oku()["5"]["iyms_var"] == "0"  # 2 saat dolmadan kontrol edilmez
    sonra = SIMDI + timedelta(hours=2)
    topla.calistir(istemci, sonra)
    assert depo.maclari_oku()["5"]["iyms_var"] == "1"
    assert any(s["market"] == "2_90" for s in depo.gz_csv_oku(depo.anlik_yolu("oranlar", sonra)))


def test_canli_bahis_acik_mac_da_kaydedilir(veri_dizini):
    # il=True: canlı bahis açık; maç henüz başlamadıysa normal maç gibi toplanmalı
    istemci = SahteIstemci([mac(8, ts(SIMDI + timedelta(hours=6)), iyms=IYMS_ORANLARI, canli=True),
                            mac(9, ts(SIMDI - timedelta(minutes=10)), canli=True)])
    ozet = topla.calistir(istemci, SIMDI)
    kayitlar = depo.maclari_oku()
    assert "8" in kayitlar and kayitlar["8"]["iyms_var"] == "1"
    assert "9" not in kayitlar and ozet["yeni"] == 1
