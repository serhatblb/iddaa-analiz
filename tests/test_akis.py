from datetime import datetime, timedelta, timezone

from conftest import SahteIstemci, mac

from iddaa import config, depo, kupon, rapor, sonuc, topla

SIMDI = datetime(2026, 9, 30, 6, 50, tzinfo=timezone.utc)  # 09:50 TR


def ts(z):
    return int(z.timestamp())


def iyms(yuksek_1_2):
    return {"1/1": 3.5, "1/0": 14.0, "1/2": yuksek_1_2, "0/1": 5.2, "0/0": 4.3,
            "0/2": 6.4, "2/1": 22.0, "2/0": 14.6, "2/2": 4.9}


def mk_satir(iddaa_id, ev, dep, bas: datetime, durum=4, iy=(0, 0), ms=(0, 0), metin="MS"):
    """Mackolik livedata satırı (38 alan)."""
    tr = bas.astimezone(config.TR)
    satir = [0] * 38
    satir[0], satir[2], satir[4], satir[5], satir[6] = 999, ev, dep, durum, metin
    satir[7] = f"{iy[0]}-{iy[1]}"
    satir[12], satir[13], satir[14] = ms[0], ms[1], iddaa_id
    satir[16] = tr.strftime("%H:%M")
    satir[29], satir[30], satir[31], satir[32] = str(ms[0]), str(ms[1]), str(iy[0]), str(iy[1])
    satir[35] = tr.strftime("%d/%m/%Y")
    satir[36] = [545, "Lig", 1, "Grup", 1, "2026", "", 0, 0, "L", 0, 1]
    satir[37] = 1
    return satir


def sahte_kaynak(satirlar):
    def getir(tarih):
        return [s for s in satirlar if s[35] == tarih]
    return getir


def test_satiri_coz_ve_sonuca_cevir():
    bas = datetime(2026, 9, 29, 18, 45, tzinfo=timezone.utc)
    m = sonuc.satiri_coz(mk_satir(3166428, "San Marino", "Arnavutluk", bas, iy=(0, 2), ms=(0, 3)))
    assert (m["iddaa_id"], m["tarih"], m["saat"]) == ("3166428", "29/09/2026", "21:45")
    assert sonuc.sonuca_cevir(m) == {"iy_ev": 0, "iy_dep": 2, "ms_ev": 0, "ms_dep": 3, "durum": "tamam",
                                     "kaynak": "mackolik"}
    # uzatmaya giden maçta 90 dakika skoru kullanılır
    uz = mk_satir(1, "A", "B", bas, durum=6, metin="UZ", iy=(0, 0), ms=(1, 1))
    uz[12], uz[13] = 1, 2
    assert sonuc.sonuca_cevir(sonuc.satiri_coz(uz))["ms_dep"] == 1
    assert sonuc.sonuca_cevir(sonuc.satiri_coz(mk_satir(1, "A", "B", bas, durum=9, metin="Ert.")))["durum"] == "iptal"
    assert sonuc.sonuca_cevir(sonuc.satiri_coz(mk_satir(1, "A", "B", bas, durum=3, metin="70")))is None
    basket = mk_satir(1, "A", "B", bas)
    basket[36] = [9, "EuroLeague", 1, "", 1, "", "", 0, 0, "AVL", 0, 2]
    assert sonuc.satiri_coz(basket) is None


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
    assert ozet["iyms"].startswith("bekliyor (3 aday)")
    assert ozet["deger"].startswith("aday_yok")  # geçmiş analiz yok
    satirlar = [s for s in kupon.kuponlari_oku() if s["tur"] == "iyms"]
    assert [(s["mac_id"], s["market"], s["secim"], s["oran"]) for s in satirlar] == [
        ("1", "İY/MS", "1/2", "28.0"), ("2", "İY/MS", "1/2", "25.0"), ("3", "İY/MS", "2/1", "22.0")]
    assert float(satirlar[0]["toplam_oran"]) == 28 * 25 * 22

    # Aynı gün tekrar çalışırsa yeni kupon açmaz
    kupon.calistir(SIMDI + timedelta(hours=1))
    assert len(kupon.kuponlari_oku()) == 4

    # Sonuçlar: ilk iki tuttu, üçüncü yattı; 1. maç kimliksiz, isim ve saatle eşleşir
    bas = {m["i"]: datetime.fromtimestamp(m["d"], timezone.utc) for m in maclar}
    kaynak = sahte_kaynak([
        mk_satir(0, "A", "B", bas[1], iy=(1, 0), ms=(1, 2)),
        mk_satir(2, "C", "D", bas[2], iy=(2, 1), ms=(2, 3)),
        mk_satir(3, "E", "F", bas[3], iy=(0, 0), ms=(1, 1)),
    ])
    ertesi = SIMDI + timedelta(days=1)
    ozet = sonuc.calistir(ertesi, veri_getir=kaynak)
    assert ozet["bulunan"] == 3
    assert depo.sonuclari_oku()["1"]["ms_dep"] == "2"
    kupon.calistir(ertesi)
    dunku = [s for s in kupon.kuponlari_oku() if s["tarih"] == "2026-09-30" and s["tur"] == "iyms"]
    assert [s["tuttu"] for s in dunku] == ["1", "1", "0"]
    assert {s["durum"] for s in dunku} == {"kaybetti"}

    r = rapor.olustur(ertesi)
    metin = "\n".join(r.md)
    assert "Dünkü İY/MS kuponu" in metin
    assert "Kaybetti" in metin
    assert "| 1/2 | 2 | 2 |" in metin  # 20–30 arası 1/2: 28 ve 25 oranlı iki örnek, ikisi de tuttu


def test_kupon_kazanir_iptal_oran_1_ve_ms_secimi():
    satirlar = [{"tarih": "t", "tur": "deger", "sira": i, "mac_id": str(i), "market": m, "secim": sec,
                 "oran": str(o), "gercek": "", "tuttu": "", "toplam_oran": "", "tutar": "20", "durum": "bekliyor",
                 "kazanc": ""}
                for i, m, sec, o in [(1, "İY/MS", "1/2", 20.0), (2, "MS", "0", 3.5), (3, "MS", "2", 4.0)]]
    sonuclar = {
        "1": {"durum": "tamam", "iy_ev": "1", "iy_dep": "0", "ms_ev": "1", "ms_dep": "2"},
        "2": {"durum": "tamam", "iy_ev": "0", "iy_dep": "0", "ms_ev": "2", "ms_dep": "2"},
    }
    kupon.kupon_degerlendir(satirlar, sonuclar)
    assert satirlar[0]["durum"] == "bekliyor" and satirlar[1]["gercek"] == "0"
    sonuclar["3"] = {"durum": "iptal"}
    kupon.kupon_degerlendir(satirlar, sonuclar)
    assert satirlar[0]["durum"] == "kazandi" and satirlar[0]["kazanc"] == 20 * 20 * 3.5


def test_sonuc_bulunamazsa_belirsiz_kupon(veri_dizini):
    istemci = SahteIstemci([mac(7, ts(SIMDI + timedelta(hours=2)))])
    topla.calistir(istemci, SIMDI)
    bos = sahte_kaynak([])
    assert sonuc.calistir(SIMDI + timedelta(hours=5), veri_getir=bos)["devam"] == 1
    assert sonuc.calistir(SIMDI + timedelta(days=4), veri_getir=bos)["belirsiz"] == 1
    satirlar = [{"tarih": "t", "tur": "iyms", "mac_id": "7", "market": "İY/MS", "secim": "1/2", "oran": "25",
                 "gercek": "", "tuttu": "", "toplam_oran": "", "tutar": "20", "durum": "bekliyor", "kazanc": ""}]
    kupon.kupon_degerlendir(satirlar, depo.sonuclari_oku())
    assert satirlar[0]["durum"] == "belirsiz" and satirlar[0]["tuttu"] == "?"


def test_aday_yoksa_kupon_yok(veri_dizini):
    istemci = SahteIstemci([mac(1, ts(SIMDI + timedelta(hours=5)), iyms=iyms(26.0))])
    topla.calistir(istemci, SIMDI - timedelta(minutes=43))
    assert kupon.calistir(SIMDI)["iyms"].startswith("aday_yok")
    assert "kupon oluşturulmadı" in "\n".join(rapor.olustur(SIMDI).md)
