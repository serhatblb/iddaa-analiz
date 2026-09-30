from datetime import date

from iddaa import arsiv, depo

LIG = [545, "UEFA Uluslar Ligi", 10974, "A Ligi Grup 3", 72303, "2026/2027", "", 0, 0, "AVUL", 0, 1]
BITMIS = [4445135, 499, "İspanya", 510, "Hırvatistan", 4, "MS", "2-1", 0, 0, 0, 0, 4, 1, 3166490, {}, "21:45", 0,
          "1.11", "5.97", "9.28", "2.59", "1.27", 1, "0.0", "0.0", "0.0", "0.0", "0.0", "4", "1", "2", "1", None,
          "1", "29/09/2026", LIG, 1]


def _satir(**degis):
    s = list(BITMIS)
    for sira, deger in degis.items():
        s[int(sira[1:])] = deger
    return s


def test_satir_kaydi():
    k = arsiv.satir_kaydi(BITMIS)
    assert (k["tarih"], k["iddaa_id"], k["lig"], k["lig_kodu"]) == ("2026-09-29", 3166490, "A Ligi Grup 3", "AVUL")
    assert (k["iy_ev"], k["iy_dep"], k["ms_ev"], k["ms_dep"]) == (2, 1, 4, 1)
    assert (k["o1"], k["o0"], k["o2"], k["alt25"], k["ust25"]) == ("1.11", "5.97", "9.28", "2.59", "1.27")
    assert arsiv.satir_kaydi(_satir(a5=3)) is None                     # devam ediyor
    assert arsiv.satir_kaydi(_satir(a14=0, a18="0.00")) is None        # iddaa'da yok
    assert arsiv.satir_kaydi(_satir(a36=LIG[:11] + [2])) is None       # basketbol
    assert arsiv.satir_kaydi(_satir(a21="0.00", a22="0.00"))["alt25"] == ""
    assert arsiv.satir_kaydi(_satir(a5=6, a29="1", a30="1"))["ms_dep"] == 1  # uzatma: 90 dk skoru


def test_calistir_aylik_dosya_ve_atlama(veri_dizini):
    istekler = []

    def getir(gun, oturum):
        istekler.append(gun)
        if gun == date(2026, 8, 31):
            return []
        return [arsiv.satir_kaydi(_satir(a0=gun.toordinal(), a35=gun.strftime("%d/%m/%Y")))]

    ozet = arsiv.calistir(date(2026, 7, 30), date(2026, 8, 31), bekleme=0, getir=getir)
    assert ozet == {"ay": 2, "atlanan": 0, "mac": 32, "eksik_gun": 0}
    assert len(depo.gz_csv_oku(depo.kok() / "arsiv" / "2026-08.csv.gz")) == 30
    # Biten aylar tekrar indirilmez
    istekler.clear()
    assert arsiv.calistir(date(2026, 7, 1), date(2026, 8, 31), bekleme=0, getir=getir)["atlanan"] == 2
    assert istekler == []
    maclar = arsiv.oku()
    assert len(maclar) == 32 and maclar[0]["o1"] == 1.11 and maclar[0]["ms_ev"] == 4


def test_eksik_gunlu_ay_yazilmaz(veri_dizini):
    def getir(gun, oturum):
        return None if gun.day == 5 else []

    ozet = arsiv.calistir(date(2026, 6, 1), date(2026, 6, 30), bekleme=0, getir=getir)
    assert ozet["eksik_gun"] == 1 and ozet["ay"] == 0
    assert not (depo.kok() / "arsiv" / "2026-06.csv.gz").exists()
