from datetime import datetime, timedelta, timezone

from conftest import SahteIstemci, mac

from iddaa import depo, kupon, rapor, sonuc, topla

SIMDI = datetime(2026, 9, 30, 6, 50, tzinfo=timezone.utc)  # 09:50 TR


def ts(z):
    return int(z.timestamp())


def iyms(yuksek_1_2):
    return {"1/1": 3.5, "1/0": 14.0, "1/2": yuksek_1_2, "0/1": 5.2, "0/0": 4.3,
            "0/2": 6.4, "2/1": 22.0, "2/0": 14.6, "2/2": 4.9}


def son_maclar_yaniti(bas, ev, dep, iy, ms):
    return {"m": [
        {"t": ts(bas), "h": {"n": ev, "fhs": iy[0], "rs": ms[0]}, "a": {"n": dep, "fhs": iy[1], "rs": ms[1]}},
        {"t": ts(bas - timedelta(days=7)), "h": {"n": ev, "fhs": 0, "rs": 1}, "a": {"n": "Başka", "fhs": 0, "rs": 0}},
    ]}


def test_sonucu_bul_tam_ve_esnek_eslesme():
    kayit = {"baslama_utc": "2026-09-30T18:00:00Z", "ev": "İstanbulspor", "dep": "Iğdır FK"}
    bas = datetime(2026, 9, 30, 18, tzinfo=timezone.utc)
    assert sonuc.sonucu_bul(son_maclar_yaniti(bas, "İSTANBULSPOR", "IĞDIR FK", (1, 0), (1, 2)), kayit) == (1, 0, 1, 2)
    # deplasman adı farklı yazılmış, tek aday -> kabul
    assert sonuc.sonucu_bul(son_maclar_yaniti(bas, "İstanbulspor", "Igdir", (0, 1), (2, 1)), kayit) == (0, 1, 2, 1)
    # zaman tutmuyor -> yok
    assert sonuc.sonucu_bul(son_maclar_yaniti(bas + timedelta(days=1), "İstanbulspor", "Iğdır FK", (0, 0), (0, 0)),
                            kayit) is None


def test_kupon_secimi_ve_degerlendirme(veri_dizini):
    maclar = [
        mac(1, ts(SIMDI + timedelta(hours=9)), ev="A", dep="B", iyms=iyms(28.0)),
        mac(2, ts(SIMDI + timedelta(hours=10)), ev="C", dep="D", iyms=iyms(25.0)),
        mac(3, ts(SIMDI + timedelta(hours=11)), ev="E", dep="F", iyms=iyms(35.0)),  # 2/1=22 aday
        mac(4, ts(SIMDI + timedelta(hours=30)), ev="G", dep="H", iyms=iyms(29.0)),  # pencere dışı
    ]
    istemci = SahteIstemci(maclar)
    topla.calistir(istemci, SIMDI - timedelta(minutes=43))
    ozet = kupon.calistir(SIMDI)
    assert ozet["aday"] == 3 and ozet["kupon"] == "bekliyor"
    satirlar = depo.csv_oku(kupon.kupon_yolu())
    assert [(s["mac_id"], s["secim"], s["oran"]) for s in satirlar] == [
        ("1", "1/2", "28.0"), ("2", "1/2", "25.0"), ("3", "2/1", "22.0")]
    assert float(satirlar[0]["toplam_oran"]) == 28 * 25 * 22

    # Aynı gün tekrar çalışırsa yeni kupon açmaz
    kupon.calistir(SIMDI + timedelta(hours=1))
    assert len(depo.csv_oku(kupon.kupon_yolu())) == 3

    # Sonuçlar: ilk iki tuttu, üçüncü yattı
    bas = {m["i"]: datetime.fromtimestamp(m["d"], timezone.utc) for m in maclar}
    istemci._son_maclar = {
        1: son_maclar_yaniti(bas[1], "A", "B", (1, 0), (1, 2)),
        2: son_maclar_yaniti(bas[2], "C", "D", (2, 1), (2, 3)),
        3: son_maclar_yaniti(bas[3], "E", "F", (0, 0), (1, 1)),
    }
    ertesi = SIMDI + timedelta(days=1)
    ozet = sonuc.calistir(istemci, ertesi)
    assert ozet["bulunan"] == 3
    kupon.calistir(ertesi)
    dunku = [s for s in depo.csv_oku(kupon.kupon_yolu()) if s["tarih"] == "2026-09-30"]
    assert [s["tuttu"] for s in dunku] == ["1", "1", "0"]
    assert {s["durum"] for s in dunku} == {"kaybetti"}

    r = rapor.olustur(ertesi)
    metin = "\n".join(r.md)
    assert "Dünkü kupon" in metin and "Kaybetti" in metin
    assert "| 1/2 | 2 | 2 |" in metin  # 20–30 arası 1/2: 28 ve 25 oranlı iki örnek, ikisi de tuttu


def test_kupon_kazanir_ve_iptal_oran_1_sayilir():
    satirlar = [{"tarih": "t", "sira": i, "mac_id": str(i), "secim": "1/2", "oran": str(o), "gercek": "",
                 "tuttu": "", "toplam_oran": "", "tutar": "20", "durum": "bekliyor", "kazanc": ""}
                for i, o in [(1, 20.0), (2, 25.0), (3, 30.0)]]
    sonuclar = {
        "1": {"durum": "tamam", "iy_ev": "1", "iy_dep": "0", "ms_ev": "1", "ms_dep": "2"},
        "2": {"durum": "tamam", "iy_ev": "2", "iy_dep": "0", "ms_ev": "2", "ms_dep": "3"},
    }
    kupon.kupon_degerlendir(satirlar, sonuclar)
    assert satirlar[0]["durum"] == "bekliyor"
    sonuclar["3"] = {"durum": "iptal"}
    kupon.kupon_degerlendir(satirlar, sonuclar)
    assert satirlar[0]["durum"] == "kazandi" and satirlar[0]["kazanc"] == 20 * 20 * 25


def test_aday_yoksa_kupon_yok(veri_dizini):
    istemci = SahteIstemci([mac(1, ts(SIMDI + timedelta(hours=5)), iyms=iyms(26.0))])
    topla.calistir(istemci, SIMDI - timedelta(minutes=43))
    assert kupon.calistir(SIMDI)["kupon"] == "aday_yok"
    assert "kupon oluşturulmadı" in "\n".join(rapor.olustur(SIMDI).md)


def test_sonuc_bulunamazsa_3_saat_bekler_sonra_iptal(veri_dizini):
    istemci = SahteIstemci([mac(7, ts(SIMDI + timedelta(hours=2)))])
    topla.calistir(istemci, SIMDI)
    sonra = SIMDI + timedelta(hours=5)
    assert sonuc.calistir(istemci, sonra)["bulunamayan"] == 1
    assert sonuc.calistir(istemci, sonra + timedelta(hours=1))["bekleyen"] == 0
    assert sonuc.calistir(istemci, sonra + timedelta(hours=3))["bekleyen"] == 1
    assert sonuc.calistir(istemci, SIMDI + timedelta(days=4))["iptal"] == 1
