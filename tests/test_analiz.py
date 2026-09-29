from datetime import datetime, timedelta, timezone

from conftest import SahteIstemci, mac

from iddaa import analiz, depo, gecmis, kupon, panel, rapor, topla

YENI_BICIM = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,B365H,B365D,B365A,PSH,PSD,PSA,"
    "MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5\n"
    "T1,08/08/2025,19:00,Galatasaray,Fatih Karagumruk,3,0,H,1,0,H,1.2,6,11,1.22,6.2,12,1.25,6.5,13,1.21,6.1,11.5,"
    "1.5,2.5,1.2,6.4,13,1.24,6.6,14,1.2,6.2,12,1.45,2.6\n"
    "T1,09/08/2025,19:00,Kasimpasa,Kocaelispor,1,2,A,1,0,H,2.4,3.3,2.9,,,,,,,2.35,3.25,2.95,,,,,,,,,,,,,\n"
    "T1,10/08/2025,19:00,Eksik,Skor,,,,,,,2.0,3.0,3.5,,,,,,,,,,,,,,,,,,,,,,\n"
)
ESKI_BICIM = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,B365H,B365D,B365A,BbMxH,BbAvH,BbMxD,BbAvD,BbMxA,BbAvA\n"
    "E0,17/08/13,Arsenal,Aston Villa,1,3,A,1,1,D,1.3,5,10,1.33,1.29,5.5,5.1,12,10.5\n"
)


def test_cozumle_yeni_ve_eski_bicim():
    yeni = gecmis.cozumle(YENI_BICIM.encode("utf-8"), "T1", "2526")
    assert len(yeni) == 2  # skoru eksik satır atlanır
    gs = yeni[0]
    assert (gs["tarih"], gs["iy_ev"], gs["ms_ev"]) == ("2025-08-08", 1, 3)
    assert gs["ort_1"] == 1.2 and gs["maks_1"] == 1.24 and gs["ps_1"] == 1.2  # kapanış sütunları öncelikli
    assert yeni[1]["ort_1"] == 2.35 and yeni[1]["maks_1"] == ""  # kapanış yoksa açılış ortalaması
    eski = gecmis.cozumle(ESKI_BICIM.encode("latin-1"), "E0", "1314")
    assert eski[0]["tarih"] == "2013-08-17" and eski[0]["ort_1"] == 1.29 and eski[0]["maks_1"] == 1.33


def test_sezon_kodlari():
    kodlar = gecmis.sezon_kodlari(datetime(2026, 9, 1))
    assert kodlar[0] == "1213" and kodlar[-1] == "2627"
    assert gecmis.sezon_kodlari(datetime(2026, 3, 1))[-1] == "2526"


def test_oran_etiketi_ve_dilim():
    assert analiz.oran_etiketi(1.55) == "1.55"
    assert analiz.oran_etiketi(1.549999) == "1.55"
    assert analiz.oran_etiketi(12) == "12.00"
    assert analiz.dilim(0.62) == "%60–65"
    assert analiz.dilim(1.0) == "%95–100"
    p = analiz.normal_olasiliklar(2.0, 3.5, 4.0)
    assert abs(sum(p) - 1) < 1e-9 and p[0] > p[2]


def _gecmis_uret(n=1200):
    maclar = []
    for i in range(n):
        # Ev favori (1.50): İY/MS 1/1 sık, arada 2/1
        iy, ms = [((1, 0), (2, 0)), ((0, 0), (1, 0)), ((0, 1), (2, 1)), ((0, 0), (0, 0)), ((1, 0), (1, 2))][i % 5]
        maclar.append({"lig": "T1", "sezon": "2526", "tarih": "2025-08-08", "ev": "A", "dep": "B",
                       "iy_ev": iy[0], "iy_dep": iy[1], "ms_ev": ms[0], "ms_dep": ms[1],
                       "ort_1": 1.5, "ort_0": 4.0, "ort_2": 6.5, "maks_1": 1.6, "maks_0": 4.2, "maks_2": 7.0,
                       "ps_1": None, "ps_0": None, "ps_2": None, "ort_ust25": None, "ort_alt25": None})
    return maclar


def test_ms_oran_tablosu_ve_kosullu():
    maclar = _gecmis_uret()
    tablo = {(s["secim"], s["oran"]): s for s in analiz.ms_oran_tablosu(maclar)}
    ev = tablo[("1", "1.50")]
    assert ev["ornek"] == 1200 and ev["tutma"] == 0.6  # 5'te 3 ev kazandı
    assert abs(ev["getiri"] - 0.9) < 1e-9 and abs(ev["getiri_maks"] - 0.96) < 1e-9
    kosullu = analiz.iyms_kosullu_tablo(maclar)
    d = analiz.dilim(analiz.normal_olasiliklar(1.5, 4.0, 6.5)[0])
    assert kosullu[d]["ornek"] == 1200 and kosullu[d]["2/1"] == 240 and kosullu[d]["1/2"] == 240


def test_deger_adaylari_ve_panel(veri_dizini):
    maclar = _gecmis_uret()
    analiz.gecmis_analizi_yaz(maclar)
    simdi = datetime(2026, 9, 30, 6, 50, tzinfo=timezone.utc)
    m = mac(1, int((simdi + timedelta(hours=8)).timestamp()),
            iyms={"1/1": 3.0, "1/0": 14.0, "1/2": 6.0, "0/1": 5.2, "0/0": 4.3, "0/2": 6.4, "2/1": 26.0,
                  "2/0": 14.6, "2/2": 4.9})
    m["m"][0]["o"] = [{"no": 1, "odd": 1.5, "n": "1"}, {"no": 2, "odd": 4.0, "n": "0"}, {"no": 3, "odd": 6.5, "n": "2"}]
    topla.calistir(SahteIstemci([m]), simdi - timedelta(minutes=30))
    oranlar = analiz.son_oranlar(simdi, {"2_90", "1_1"})
    adaylar = analiz.deger_adaylari(oranlar, depo.maclari_oku(), analiz.kosullu_oku(), simdi)
    en_iyi = adaylar[0]
    assert (en_iyi["market"], en_iyi["secim"]) == ("İY/MS", "2/1")  # geçmiş sıklık %20, iddaa 26 -> 5.2
    assert en_iyi["beklenen"] == 5.2 and en_iyi["adil_oran"] == 5.0

    oneriler = kupon.oneriler(simdi)
    assert [(a["mac_id"], a["market"], a["secim"], a["beklenen"]) for a in oneriler["deger"]] == [("1", "İY/MS", "2/1", 5.2)]
    metin = "\n".join(rapor.olustur(simdi).md)
    assert "değerli görünen seçimler" in metin and "2/1" in metin
    assert "Geçmiş veri: MS 1-0-2" in metin
    sayfa, dosyalar = panel.olustur(simdi)
    assert "<html" in sayfa and "MS 1-0-2 oranları tek tek" in sayfa and "Ev sahibi (1)" in sayfa
    assert "Kupon önerileri" in sayfa and "Önizleme" in sayfa and "f-oran" in sayfa
    ms = dosyalar["gecmis_ms.json"]
    assert ms["alanlar"][:2] == ["secim", "oran"] and ["1", "1.50"] in [r[:2] for r in ms["satirlar"]]
