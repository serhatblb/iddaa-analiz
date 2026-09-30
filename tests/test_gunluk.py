from datetime import datetime, timedelta, timezone

from conftest import SahteIstemci, mac

from iddaa import gunluk, kupon, topla

SABAH = datetime(2026, 9, 30, 6, 50, tzinfo=timezone.utc)  # 09:50 TR


def test_kupon_sabahtan_once_olusmaz_sonra_bir_kez_olusur(veri_dizini, monkeypatch):
    gonderilen = []
    monkeypatch.setattr("iddaa.rapor.mail_gonder", lambda r, konu: gonderilen.append(konu) or True)
    topla.calistir(SahteIstemci([mac(1, int((SABAH + timedelta(hours=5)).timestamp()))]), SABAH - timedelta(hours=4))
    erken = gunluk.calistir(SABAH - timedelta(hours=3))  # 06:50 TR
    assert erken["yeni"] is False and kupon.kuponlari_oku() == []
    ilk = gunluk.calistir(SABAH)
    assert ilk["yeni"] is True and ilk["mail"] is True and len(gonderilen) == 1
    ikinci = gunluk.calistir(SABAH + timedelta(hours=1))
    assert ikinci["yeni"] is False and len(gonderilen) == 1
    assert {s["tur"] for s in kupon.kuponlari_oku()} == set(kupon.TURLER)
    assert (veri_dizini / "raporlar" / "2026-09-30.md").exists()
