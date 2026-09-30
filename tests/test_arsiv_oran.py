from iddaa import arsiv, arsiv_oran, depo


def _market(ad, mbs, adlar, oranlar, market_no, iddaa_id="533479"):
    liste = lambda xs: ",".join(f"'{x}'" for x in xs)  # noqa: E731
    return (f'<div class="detail-title" style="width:auto"> {ad} <span style="float:right">06340&nbsp;&nbsp;'
            f'<img src="http://im.mackolik.com/img5/iddaa/mbs{mbs}.png"></span></div>'
            f"<a href=\"javascript:openOddsDialog('1', '{ad}', [{liste(adlar)}], [{liste(oranlar)}], '06340', "
            f"'openBmMacDetay', '{iddaa_id}', '{market_no}', ['1','2','3'])\">x</a>" * 2)


SAYFA = (_market("Maç Sonucu", 2, ["1", "X", "2"], ["2.21", "2.85", "2.48"], "1")
         + _market("İlk Yarı/Maç Sonucu", 3, ["1/1", "1/X", "1/2", "X/1", "X/X", "X/2", "2/1", "2/X", "2/2"],
                   ["3.35", "11.00", "26.00", "4.90", "3.90", "5.20", "25.00", "11.00", "3.55"], "2")
         + _market("Toplam Gol Aralığı", 1, ["0-1 Gol", "2-3 Gol", "4-5 Gol", "6+ Gol"], ["2.85", "1.71", "3.10", "-"], "3")
         + _market("Maç Skoru", 1, ["1-0"], ["7.80"], "4"))


def test_sayfayi_coz():
    k = arsiv_oran.sayfayi_coz(SAYFA, 3562540)
    assert (k["iddaa_id"], k["market_sayisi"]) == ("533479", 4)
    assert (k["ms_1"], k["ms_0"], k["ms_2"], k["ms_mbs"]) == ("2.21", "2.85", "2.48", "2")
    assert (k["iyms_21"], k["iyms_00"], k["iyms_mbs"]) == ("25.00", "3.90", "3")
    assert (k["tg_45"], k["tg_6"]) == ("3.10", "")
    assert "kg_var" not in k
    assert arsiv_oran.sayfayi_coz("<html>iddaa yok</html>", 1)["market_sayisi"] == 0


def test_calistir_yeniden_eskiye_ve_atlama(veri_dizini):
    satirlar = []
    for gun in range(1, 4):
        for i in range(2):
            mk_id = gun * 10 + i
            satirlar.append({"tarih": f"2026-08-0{gun}", "saat": "20:00", "mk_id": mk_id, "iddaa_id": 500 + mk_id,
                             "ulke_id": 1, "ulke": "Türkiye", "lig_id": 1, "lig": "Süper Lig", "lig_kodu": "TSL",
                             "sezon": "2026/2027", "ev_id": 1, "ev": "A", "dep_id": 2, "dep": "B", "durum": 4,
                             "iy_ev": 1, "iy_dep": 0, "ms_ev": 2, "ms_dep": 1, "o1": "2.00", "o0": "3.00",
                             "o2": "3.50", "alt25": "", "ust25": ""})
    arsiv._yaz(depo.kok() / "arsiv" / "2026-08.csv.gz", satirlar)
    istenen = []

    def getir(mk_id, oturum):
        istenen.append(mk_id)
        return SAYFA if mk_id != "21" else "<html></html>"

    ozet = arsiv_oran.calistir(bekleme=0, is_parcacigi=1, getir=getir)
    assert ozet["indirilen"] == 6 and ozet["iddaasiz"] == 1
    assert istenen[:2] == ["30", "31"] or istenen[:2] == ["31", "30"]  # en yeni gün önce
    kayitlar = arsiv_oran.oku()
    assert kayitlar["10"]["iyms_21"] == 25.0 and kayitlar["21"]["market_sayisi"] == "0"
    istenen.clear()
    assert arsiv_oran.calistir(bekleme=0, getir=getir)["aday"] == 0 and istenen == []
