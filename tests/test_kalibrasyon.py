import math
import random
from datetime import date

from iddaa import arsiv, arsiv_oran, depo, kalibrasyon as k


def test_kazanan():
    assert k.kazanan("MS", 0, 0, 2, 1) == "1"
    assert k.kazanan("İY/MS", 1, 0, 1, 2) == "1/2"
    assert k.kazanan("Toplam gol", 0, 0, 3, 3) == "6+ gol"
    assert k.kazanan("Toplam gol", 0, 0, 1, 0) == "0-1 gol"
    assert k.kazanan("KG", 0, 0, 1, 0) == "Yok" and k.kazanan("KG", 0, 1, 1, 1) == "Var"
    assert k.kazanan("İY", 0, 1, 2, 1) == "2"
    assert k.kazanan("2.5 A/Ü", 0, 0, 2, 1) == "Üst" and k.kazanan("1.5 A/Ü", 0, 0, 1, 0) == "Alt"


def test_irls_egriyi_bulur():
    gercek = [0.3, 0.9, 0.04]
    dilimler = []
    for i in range(1, 100):
        q = i / 100
        x = k.logit(q)
        p = k.sigmoid(gercek[0] + gercek[1] * x + gercek[2] * x * x)
        dilimler.append((x, 10000, 10000 * p))
    tahmin = k._irls(dilimler)
    assert all(abs(a - b) < 1e-3 for a, b in zip(tahmin, gercek))


def _mac_uret(n, rnd, lig_etkisi):
    """Ev olasılığı bilinen maçlar; iddaa %17 kâr payıyla adil oranları düşürür. Lig B'de ev sahibi daha güçlü."""
    maclar = []
    for i in range(n):
        lig = "B" if i % 2 else "A"
        p1 = rnd.uniform(0.2, 0.7)
        p0 = (1 - p1) * 0.45
        p2 = 1 - p1 - p0
        oranlar = {s: round(1 / (p * 1.17), 2) for s, p in (("1", p1), ("0", p0), ("2", p2))}
        gercek_p1 = min(0.95, p1 + (lig_etkisi if lig == "B" else 0))
        r = rnd.random()
        sonuc = "1" if r < gercek_p1 else "0" if r < gercek_p1 + p0 * (1 - gercek_p1) / (1 - p1) else "2"
        skor = {"1": (1, 0, 2, 0), "0": (0, 0, 1, 1), "2": (0, 1, 0, 2)}[sonuc]
        maclar.append((lig, skor, {"MS": oranlar}))
    return maclar


def test_model_lig_duzeltmesi_ve_olasiliklar():
    rnd = random.Random(7)
    sayac = k.Sayaclar()
    for lig, skor, marketler in _mac_uret(40000, rnd, 0.08):
        sayac.ekle(lig, skor, marketler)
    model = k.model_kur(sayac)
    ev = model["marketler"]["MS"]["1"]
    assert ev["lig"].get("B", 0) > ev["lig"].get("A", 0)  # B'de ev sahibi iddaa'nın sandığından sık kazanıyor
    oranlar = {"1": 2.0, "0": 3.3, "2": 3.6}
    p_a, p_b = k.olasiliklar(model, "MS", oranlar, "A"), k.olasiliklar(model, "MS", oranlar, "B")
    assert abs(sum(p_a.values()) - 1) < 1e-9 and abs(sum(p_b.values()) - 1) < 1e-9
    assert p_b["1"] > p_a["1"]
    assert k.olasiliklar(model, "MS", {"1": 2.0, "0": None, "2": 3.6}) == {}


def _dosyalari_yaz(rnd, aylar):
    for ay in aylar:
        arsiv_satirlari, oran_satirlari = [], []
        for i in range(400):
            mk_id = f"{ay.replace('-', '')}{i:04d}"
            q_ev = rnd.uniform(0.25, 0.65)
            ev_kazanir = rnd.random() < q_ev
            iy, ms = ((1, 0), (2, 1)) if ev_kazanir else ((0, 0), (1, 1))
            arsiv_satirlari.append({
                "tarih": f"{ay}-15", "saat": "20:00", "mk_id": mk_id, "iddaa_id": 100 + i, "ulke_id": 17,
                "ulke": "İngiltere", "lig_id": 1, "lig": "Premier Lig", "lig_kodu": "İNG", "sezon": "2025/2026",
                "ev_id": 1, "ev": "A", "dep_id": 2, "dep": "B", "durum": 4, "iy_ev": iy[0], "iy_dep": iy[1],
                "ms_ev": ms[0], "ms_dep": ms[1], "o1": round(0.96 / (q_ev * 1.17), 2), "o0": 3.3,
                "o2": 3.5, "alt25": 1.8, "ust25": 1.9})
            oran_satirlari.append({"mk_id": mk_id, "iddaa_id": 100 + i, "market_sayisi": 40,
                                   "iyms_11": 3.0, "iyms_10": 15.0, "iyms_12": 25.0, "iyms_01": 5.0, "iyms_00": 4.5,
                                   "iyms_02": 7.0, "iyms_21": 26.0, "iyms_20": 15.0, "iyms_22": 6.0,
                                   "tg_01": 3.5, "tg_23": 1.8, "tg_45": 3.2, "tg_6": 12.0})
        arsiv._yaz(arsiv.dizin() / f"{ay}.csv.gz", arsiv_satirlari)
        depo.gz_csv_yaz(arsiv_oran.dizin() / f"{ay}.csv.gz", oran_satirlari, arsiv_oran.ALANLAR)


def test_mac_akisi_ve_calistir(veri_dizini):
    rnd = random.Random(3)
    aylar = [k.ay_ekle("2026-09", -i) for i in range(20, -1, -1)]
    _dosyalari_yaz(rnd, aylar)
    akis = list(k.mac_akisi("2026-09", "2026-09"))
    assert len(akis) == 400
    tarih, lig, skor, marketler = akis[0]
    assert lig == "İngiltere|İNG" and set(marketler) == {"MS", "İY/MS", "Toplam gol", "2.5 A/Ü"}
    ozet = k.calistir(date(2026, 9, 30))
    assert ozet["tum_mac"] == 400 * 21
    assert ozet["planlar"]["MS"] == {"egitim": "2022-10 → 2025-09", "test": "2025-10 → 2026-09", "egitim_mac": 3600}
    model = k.model_oku()
    assert model["mac"] == 400 * 21 and "İY/MS" in model["marketler"]
    test = depo.json_oku(depo.kok() / "analiz" / "geriye_test.json")
    satir = {(s["strateji"], s["market"], s["esik"]): s for s in test["satirlar"]}
    assert satir[("hepsi", "MS", 0.0)]["bahis"] == 3 * 400 * 12  # maç başına 3 seçim
    assert satir[("mac_basi", "MS", 0.0)]["bahis"] == 400 * 12
    kosullu = k.kosullu_oku()
    assert kosullu["genel"]["n"] == 400 * 21 and sum(h["n"] for h in kosullu["hucre"].values()) == 400 * 21
    tablo = depo.json_oku(depo.kok() / "analiz" / "iddaa_oran_tablosu.json")
    assert tablo["İY/MS"]["2/1"][0][:2] == [27.04, 400 * 21]  # Kral orana çevrilmiş
    senaryo = depo.json_oku(depo.kok() / "analiz" / "iddaa_senaryolar.json")
    bantlar = {(r["market"], r["secenek"], r["bant"]): r for r in senaryo["satirlar"]}
    iyms_2030 = bantlar[("İY/MS", "hepsi", "20–30")]
    assert iyms_2030["bahis"] == 2 * 400 * 21 and iyms_2030["tutan"] == 0  # sentetik veride hiç 1/2, 2/1 yok


def test_normallestir_ve_logit():
    q = k.normallestir({"1": 2.0, "0": 3.0, "2": 6.0})
    assert abs(sum(q.values()) - 1) < 1e-12 and abs(q["1"] - 0.5) < 1e-12
    assert abs(k.sigmoid(k.logit(0.3)) - 0.3) < 1e-12
    assert math.isfinite(k.logit(0)) and math.isfinite(k.logit(1))


def test_mbs_ile_sec():
    from iddaa import kupon
    a = lambda b, mbs: {"beklenen": b, "mbs": mbs}  # noqa: E731
    # Hepsi zararlı: tek maç (MBS 1) en iyisi
    assert kupon.mbs_ile_sec([a(0.95, "3"), a(0.93, "1"), a(0.9, "2")]) == [a(0.93, "1")]
    # Değerli seçimler: 3 maç çarpımı daha büyük
    assert len(kupon.mbs_ile_sec([a(1.10, "3"), a(1.05, "1"), a(1.02, "2")])) == 3
    # MBS bilinmiyorsa en kısıtlayıcı varsayım: tek başına oynanamaz
    assert kupon.mbs_ile_sec([a(0.97, ""), a(0.9, "1")]) == [a(0.9, "1")]
    assert kupon.mbs_ile_sec([a(0.97, "2")]) == []


def test_model_ile_kupon_adaylari(veri_dizini):
    from datetime import datetime, timedelta, timezone

    from conftest import SahteIstemci, mac

    from iddaa import kupon, topla
    rnd = random.Random(5)
    sayac = k.Sayaclar()
    for lig, skor, marketler in _mac_uret(20000, rnd, 0.0):
        sayac.ekle(lig, skor, marketler)
    model = k.model_kur(sayac)
    simdi = datetime(2026, 9, 30, 6, 50, tzinfo=timezone.utc)
    m = mac(1, int((simdi + timedelta(hours=8)).timestamp()))
    m["m"][0]["o"] = [{"no": 1, "odd": 1.5, "n": "1"}, {"no": 2, "odd": 4.0, "n": "0"}, {"no": 3, "odd": 6.5, "n": "2"}]
    m["m"][0]["mbc"] = 1
    topla.calistir(SahteIstemci([m]), simdi - timedelta(minutes=30))
    oneriler = kupon.oneriler(simdi, model=model)
    ms = oneriler["ms"]
    assert ms and ms[0]["kaynak"].startswith("iddaa geçmişi") and ms[0]["mbs"] == "1"
    assert abs(ms[0]["beklenen"] - ms[0]["oran"] * ms[0]["tutma"]) < 0.01
    assert oneriler["iyms"] == [] or oneriler["iyms"][0]["kaynak"] == "yabancı şirket verisi"  # model İY/MS'yi bilmiyor
    satirlar = kupon.kupon_olustur("2026-09-30", "ms", ms)
    assert len(satirlar) == 1 and satirlar[0]["mbs"] == "1"  # MBS 1: tek maçlık kupon


def test_sanal_tekler(veri_dizini):
    from datetime import datetime, timedelta, timezone

    from conftest import SahteIstemci, mac

    from iddaa import sonuc, tekler, topla
    rnd = random.Random(9)
    sayac = k.Sayaclar()
    for lig, skor, marketler in _mac_uret(20000, rnd, 0.0):
        sayac.ekle(lig, skor, marketler)
    model = k.model_kur(sayac)
    simdi = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)
    bas = simdi + timedelta(hours=2)
    m = mac(1, int(bas.timestamp()), ev="A", dep="B")
    # Deplasman çok değerli görünsün: iddaa'nın payı düşük (adil orana yakın)
    m["m"][0]["o"] = [{"no": 1, "odd": 1.7, "n": "1"}, {"no": 2, "odd": 4.2, "n": "0"}, {"no": 3, "odd": 6.5, "n": "2"}]
    topla.calistir(SahteIstemci([m]), simdi - timedelta(hours=5))
    assert tekler.calistir(simdi - timedelta(hours=5), model=model)["mac"] == 0  # henüz erken
    ozet = tekler.calistir(simdi, model=model)
    assert ozet["mac"] == 1 and ozet["secim"] >= 1
    assert tekler.calistir(simdi + timedelta(hours=1), model=model)["mac"] == 0  # bir kez
    satirlar = [s for s in tekler.oku() if s["market"]]
    assert all(float(s["beklenen"]) >= 1.0 for s in satirlar)
    # Sonuç: deplasman kazandı (0-1); sonuçlar dosyasına doğrudan yazılır
    from iddaa import depo
    kayitlar = depo.maclari_oku()
    sonuclar = {"1": {"mac_id": "1", "iy_ev": 0, "iy_dep": 0, "ms_ev": 0, "ms_dep": 1, "durum": "tamam",
                      "kaynak": "test", "guncelleme_utc": ""}}
    depo.sonuclari_yaz(sonuclar, kayitlar, {"1"})
    ozet = tekler.degerlendir()
    hepsi = [r for r in ozet["satirlar"] if r["market"] == "hepsi" and not r["dilim"]][0]
    assert hepsi["bahis"] == len(satirlar) and ozet["bekleyen"] == 0
    kazanan = [s for s in satirlar if k.kazanan(s["market"], 0, 0, 0, 1) == s["secim"]]
    assert hepsi["tutan"] == len(kazanan)
    assert hepsi["clv"] == 1.0  # oranlar değişmedi: kapanış = aldığımız oran
    assert sonuc  # modül içe aktarılabiliyor


def test_senaryolar_cift_saymaz():
    sayac = k.Sayaclar()
    sayac.ekle("L", (0, 0, 2, 1), {"2.5 A/Ü": {"Alt": 1.8, "Üst": 1.9}, "MS": {"1": 2.0, "0": 3.2, "2": 3.6}})
    satirlar = {(r["market"], r["secenek"], r["bant"]): r for r in k.senaryolar(sayac)["satirlar"]}
    assert satirlar[("2.5 A/Ü", "hepsi", "")]["bahis"] == 2 and satirlar[("2.5 A/Ü", "Üst", "")]["bahis"] == 1
    assert satirlar[("MS", "hepsi", "")]["bahis"] == 3 and satirlar[("MS", "1", "2–3")]["tutan"] == 1
    assert abs(satirlar[("MS", "1", "")]["getiri_kral"] - 2.0 * 1.04) < 1e-9


def test_bolme_plani():
    sayim = {"MS": {f"2024-{a:02d}": 500 for a in range(1, 13)} | {f"2025-{a:02d}": 500 for a in range(1, 13)},
             "İY/MS": {"2026-01": 100, "2026-02": 100, "2026-03": 100, "2026-04": 100, "2026-05": 100},
             "KG": {"2026-09": 50}}
    plan = k.bolme_plani(sayim, "2026-09")
    assert plan["MS"] == ("2022-10", "2025-09", "2025-10", "2026-09")
    assert "İY/MS" not in plan  # 500 maç: test için çok az
    sayim["İY/MS"] = {a: 1000 for a in sayim["İY/MS"]}
    assert k.bolme_plani(sayim, "2026-09")["İY/MS"] == ("2026-01", "2026-02", "2026-03", "2026-05")  # ikiye
    assert "KG" not in plan


def test_hayal_kuponu(veri_dizini):
    rnd = random.Random(3)
    _dosyalari_yaz(rnd, ["2026-08", "2026-09"])
    k.calistir(date(2026, 9, 30))
    h = depo.json_oku(depo.kok() / "analiz" / "iddaa_senaryolar.json")["hayal_kuponu"]
    # Sentetik veride 30+ oranlı İY/MS seçeneği yok (en yüksek 27.04): yedek kademe (20+) kullanılır; 1/2 ve 2/1
    # hiç tutmuyor (sonuç hep 1/1 ya da 0/0)
    assert h["gun"] == 2 and h["harcanan"] == 40 and h["kazanan"] == 0 and h["tek_bahis"] == 6
    assert h["tek_tutan"] == 0 and h["ort_kupon_orani"] > 20 ** 3


def test_hayal_secimi_ve_kosullu_olasilik():
    tablo = {"genel": {"n": 1000, "1/2": 20}, "hucre": {"3|1": {"n": 950, "1/2": 57}, "0|1": {"n": 10, "1/2": 0}}}
    assert abs(k.kosullu_olasilik(tablo, "3|1", "1/2", 0.02) - (57 + 50 * 0.02) / 1000) < 1e-12
    assert k.kosullu_olasilik(tablo, "yok", "1/2", 0.03) == 0.03   # hücre yoksa iddaa'nın olasılığı
    assert k.kosullu_olasilik(tablo, None, "1/2", 0.03) == 0.03
    assert 0 < k.kosullu_olasilik(tablo, "0|1", "1/2", 0.02) < 0.02  # az maçlı hücre öncüle çekilir
    assert k.kosul_anahtari({"1": 1.0, "0": 9.0, "2": 17.5}, None) == "16|9"  # 1.00 favori de geçerli
    # tavan kademesi önce, kademe içinde olasılığa göre
    adaylar = [("a", 36.4, 0.02, 0), ("b", 36.4, 0.03, 0), ("c", 25.0, 0.09, 0), ("d", 31.0, 0.01, 0)]
    assert [x[0] for x in k.hayal_secimi(adaylar, 30, 20)] == ["b", "a", "d"]
    assert [x[0] for x in k.hayal_secimi(adaylar[:2] + adaylar[2:3], 30, 20)] == ["b", "a", "c"]
    assert k.kosul_anahtari({"1": 2.0, "0": 3.4, "2": 3.8}, {"Alt": 1.9, "Üst": 1.9}) == "4|1"



def test_dar_aralikta_egri_uzatilmaz():
    """İY/MS 1/0 gibi seçeneklerde q hep %4-7 arası; aralık dışında eğri bükülüp saçmalamamalı."""
    rnd = random.Random(11)
    sayac = k.Sayaclar()
    for _ in range(6000):
        q1 = rnd.uniform(0.04, 0.07)
        oranlar = {"Var": round(1 / (q1 * 1.2), 2), "Yok": round(1 / ((1 - q1) * 1.2), 2)}
        tuttu = rnd.random() < q1
        sayac.ekle("L", (0, 0, 1, 1) if tuttu else (0, 0, 1, 0), {"KG": oranlar})
    model = k.model_kur(sayac, min_mac=1000)
    egri = model["marketler"]["KG"]["Var"]
    lo, hi = egri["aralik"]
    assert k.logit(0.035) < lo < k.logit(0.045) and k.logit(0.065) < hi < k.logit(0.075)
    for q in (0.005, 0.01, 0.2, 0.5):
        p = k.egrisel_olasilik(egri["katsayi"], q, aralik=egri["aralik"])
        assert 0.6 * q < p < 1.6 * q, (q, p)   # aralık dışında iddaa'nın olasılığına paralel
