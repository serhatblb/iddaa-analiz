"""Günlük kağıt üstü kuponlar. Para yatırılmaz; seçimler kaydedilir, sonuçlar gelince değerlendirilir.

Olasılıklar iddaa'nın kendi geçmiş oranlarıyla kurulan modelden gelir (`kalibrasyon.py`: iddaa bu seçeneğe
kâr payı ayıklanınca %q şans veriyordu, gerçekte ne sıklıkla tuttu + lig düzeltmesi). Model o market için henüz
yoksa yabancı şirket verisiyle (football-data) kurulan eski tablolar kullanılır. Beklenen = iddaa.com oranı × olasılık.

Dört ayrı kupon, önümüzdeki 24 saatte başlayacak maçlardan (her maçtan en fazla bir seçim):
- iyms: Oranı 20–30 arası İY/MS seçenekleri; beklenen dönüşü en yüksek 3 seçim (hayal kuponu, hep 3 maç).
- ms:   MS 1-0-2 seçimleri (oran 1.40–5.00); beklenen dönüşü en yüksek seçimler.
- iyms_deger: Her maçın beklenen dönüşü en yüksek İY/MS seçimi.
- gol:  Toplam gol (0-1 / 2-3 / 4-5 / 6+); beklenen dönüşü en yüksek seçimler.
ms, iyms_deger ve gol kuponlarında maç sayısı MBS'ye göre seçilir: 1, 2 ya da 3 maçlık kuponlardan (her seçimin
MBS'si kupondaki maç sayısını geçmemeli) 1 TL'ye beklenen dönüşü en yüksek olan; eşitlikte az maçlı olan.
Çünkü her eklenen maç iddaa'nın kâr payını bir kez daha çarpar.
"""
import logging
from datetime import datetime, timedelta, timezone

import math

from . import analiz, config, depo, kalibrasyon
from .bulten import iso_oku, iyms_sonucu, sonuc_isareti

log = logging.getLogger("kupon")

KUPON_ALANLARI = ["tarih", "tur", "sira", "mac_id", "lig", "ev", "dep", "baslama_utc", "market", "secim",
                  "oran", "tutma", "beklenen", "gercek", "tuttu", "toplam_oran", "tutar", "durum", "kazanc", "mbs",
                  "kaynak"]
SABIT_MAC_SAYILI = {"iyms"}   # hayal kuponu hep 3 maç; diğerleri MBS'ye göre en iyi maç sayısı
TURLER = {"iyms": "İY/MS kuponu", "ms": "1-0-2 kuponu", "iyms_deger": "İY/MS değer kuponu", "gol": "Gol kuponu"}
MS_MIN_ORAN = config.MS_KUPON_MIN_ORAN
MS_MAX_ORAN = config.MS_KUPON_MAX_ORAN
EN_ERKEN_BASLAMA = timedelta(minutes=15)
PENCERE = timedelta(hours=24)


def kupon_yolu():
    return depo.kok() / "kuponlar.csv"


def _pencerede(kayit: dict, simdi: datetime) -> bool:
    bas = iso_oku(kayit["baslama_utc"])
    return simdi + EN_ERKEN_BASLAMA <= bas <= simdi + PENCERE


# --- aday bulma ---

def iyms_adaylari(oranlar: dict, kayitlar: dict, simdi: datetime, kosullu: dict | None = None,
                  min_oran: float = config.KUPON_MIN_ORAN, max_oran: float = config.KUPON_MAX_ORAN) -> list[dict]:
    """kosullu verilirse her adaya geçmiş sıklık, adil oran ve beklenen dönüş eklenir."""
    gecmis = {}
    if kosullu:
        for a in analiz.deger_adaylari(oranlar, kayitlar, kosullu, simdi, ufuk=PENCERE):
            if a["market"] == "İY/MS":
                gecmis[(a["mac_id"], a["secim"])] = a
    adaylar = []
    for mac_id, marketler in oranlar.items():
        kayit = kayitlar.get(mac_id)
        iyms = (marketler.get(config.IYMS) or {}).get("oranlar", {})
        if not kayit or not iyms or not _pencerede(kayit, simdi):
            continue
        uygun = [(o, s) for s, o in iyms.items() if min_oran <= o <= max_oran]
        if not uygun:
            continue
        oran, secim = max(uygun)
        g = gecmis.get((mac_id, secim), {})
        adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                        "baslama_utc": kayit["baslama_utc"], "market": "İY/MS", "secim": secim, "oran": oran,
                        "tutma": g.get("gecmis_siklik", ""), "beklenen": g.get("beklenen", "")})
    return sorted(adaylar, key=lambda a: (-a["oran"], a["baslama_utc"], a["mac_id"]))


def ms_adaylari(oranlar: dict, kayitlar: dict, tablo: dict, simdi: datetime,
                min_oran: float = MS_MIN_ORAN, max_oran: float = MS_MAX_ORAN) -> list[dict]:
    """Her maçtan beklenen dönüşü en yüksek MS seçimi."""
    en_iyi: dict[str, dict] = {}
    for a in analiz.ms_adaylari(oranlar, kayitlar, tablo, simdi, ufuk=PENCERE):
        if not (min_oran <= a["oran"] <= max_oran) or not _pencerede(kayitlar[a["mac_id"]], simdi):
            continue
        if a["mac_id"] not in en_iyi or a["beklenen"] > en_iyi[a["mac_id"]]["beklenen"]:
            en_iyi[a["mac_id"]] = a
    return sorted(({k: a[k] for k in ("mac_id", "lig", "ev", "dep", "baslama_utc", "market", "secim", "oran",
                                      "tutma", "ornek", "beklenen", "hata")} for a in en_iyi.values()),
                  key=lambda a: (-a["beklenen"], a["baslama_utc"], a["mac_id"]))


def mac_basina_en_iyi(adaylar: list[dict], kayitlar: dict, simdi: datetime) -> list[dict]:
    """Her maçtan beklenen dönüşü en yüksek tek seçim; beklenene göre sıralı."""
    en_iyi: dict[str, dict] = {}
    for a in adaylar:
        if not _pencerede(kayitlar[a["mac_id"]], simdi):
            continue
        if a["mac_id"] not in en_iyi or a["beklenen"] > en_iyi[a["mac_id"]]["beklenen"]:
            en_iyi[a["mac_id"]] = a
    alanlar = ("mac_id", "lig", "ev", "dep", "baslama_utc", "market", "secim", "oran", "tutma", "beklenen",
               "mbs", "kaynak")
    return sorted(({k: a.get(k, "") for k in alanlar} for a in en_iyi.values()),
                  key=lambda a: (-a["beklenen"], a["baslama_utc"], a["mac_id"]))


# --- iddaa'nın kendi geçmişiyle kurulan model ---

MODEL_MARKET_ANAHTARLARI = {config.IYMS, analiz.MS, analiz.TOPLAM_GOL, analiz.ALT_UST, "2_88", "2_89"}


def model_adaylari(model: dict, oranlar: dict, kayitlar: dict, simdi: datetime) -> list[dict]:
    """Penceredeki bütün maçların model kapsamındaki bütün seçimleri."""
    adaylar = []
    if not model.get("marketler"):
        return adaylar
    for mac_id, marketler in oranlar.items():
        kayit = kayitlar.get(mac_id)
        if not kayit or not _pencerede(kayit, simdi):
            continue
        for s in kalibrasyon.mac_secenekleri(model, marketler, kayit.get("mk_lig") or None):
            adaylar.append({"mac_id": mac_id, "lig": kayit.get("lig", ""), "ev": kayit["ev"], "dep": kayit["dep"],
                            "baslama_utc": kayit["baslama_utc"], "market": s["market"], "secim": s["secim"],
                            "oran": s["oran"], "tutma": s["olasilik"], "beklenen": s["beklenen"],
                            "mbs": s["mbs"] or kayit.get("mbs", ""),
                            "kaynak": "iddaa geçmişi" + (" + lig" if s["lig_etkisi"] else "")})
    return adaylar


def _model_turu(model_adaylar: list[dict], market: str, kayitlar: dict, simdi: datetime,
                min_oran: float = 1.0, max_oran: float = 1e9) -> list[dict]:
    return mac_basina_en_iyi([a for a in model_adaylar if a["market"] == market
                              and min_oran <= a["oran"] <= max_oran], kayitlar, simdi)


def iyms_deger_adaylari(oranlar: dict, kayitlar: dict, kosullu: dict, simdi: datetime) -> list[dict]:
    if not kosullu:
        return []
    adaylar = [{**a, "tutma": a["gecmis_siklik"]}
               for a in analiz.deger_adaylari(oranlar, kayitlar, kosullu, simdi, ufuk=PENCERE)
               if a["market"] == "İY/MS"]
    return mac_basina_en_iyi(adaylar, kayitlar, simdi)


def gol_adaylari(oranlar: dict, kayitlar: dict, tablo: dict, simdi: datetime) -> list[dict]:
    return mac_basina_en_iyi(analiz.gol_adaylari(oranlar, kayitlar, tablo, simdi, ufuk=PENCERE), kayitlar, simdi)


def oneriler(simdi: datetime | None = None, model: dict | None = None) -> dict[str, list[dict]]:
    """Şu anki oranlarla her kupon türünün aday listesi. Model o marketi kapsıyorsa model, yoksa eski tablolar."""
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    kayitlar = depo.maclari_oku()
    oranlar = analiz.son_oranlar(simdi, MODEL_MARKET_ANAHTARLARI)
    model = kalibrasyon.model_oku() if model is None else model
    kapsam = set((model.get("marketler") or {}).keys())
    modelden = model_adaylari(model, oranlar, kayitlar, simdi) if kapsam else []
    kosullu = analiz.kosullu_oku()

    def eski(adaylar):
        return [{**a, "kaynak": "yabancı şirket verisi"} for a in adaylar]

    return {
        "iyms": (_model_turu(modelden, "İY/MS", kayitlar, simdi, config.KUPON_MIN_ORAN, config.KUPON_MAX_ORAN)
                 if "İY/MS" in kapsam else eski(iyms_adaylari(oranlar, kayitlar, simdi, kosullu))),
        "ms": (_model_turu(modelden, "MS", kayitlar, simdi, MS_MIN_ORAN, MS_MAX_ORAN)
               if "MS" in kapsam else eski(ms_adaylari(oranlar, kayitlar, analiz.ms_olasilik_oku(), simdi))),
        "iyms_deger": (_model_turu(modelden, "İY/MS", kayitlar, simdi)
                       if "İY/MS" in kapsam else eski(iyms_deger_adaylari(oranlar, kayitlar, kosullu, simdi))),
        "gol": (_model_turu(modelden, "Toplam gol", kayitlar, simdi)
                if "Toplam gol" in kapsam else eski(gol_adaylari(oranlar, kayitlar, analiz.gol_tablosu_oku(), simdi))),
    }


# --- kupon oluşturma ve değerlendirme ---

def _mbs(aday: dict) -> int:
    """Seçimin MBS'si; bilinmiyorsa en kısıtlayıcı varsayım (kupon maç sayısı)."""
    try:
        return max(1, int(float(aday.get("mbs") or "")))
    except ValueError:
        return config.KUPON_MAC_SAYISI


def mbs_ile_sec(adaylar: list[dict], en_fazla: int = config.KUPON_MAC_SAYISI) -> list[dict]:
    """Beklenene göre sıralı adaylardan MBS'ye uyan, 1 TL'ye beklenen dönüşü en yüksek kupon (eşitlikte az maç).
    MBS'si bilinmeyen seçim en fazla maç sayısında oynanabilir sayılır."""
    en_iyi, en_iyi_deger = [], -1.0
    for k in range(1, en_fazla + 1):
        uygun = [a for a in adaylar if _mbs(a) <= k][:k]
        if len(uygun) < k:
            continue
        deger = math.prod(float(a["beklenen"] or 0) for a in uygun)
        if deger > en_iyi_deger + 1e-9:
            en_iyi, en_iyi_deger = uygun, deger
    return en_iyi


def kupon_olustur(tarih: str, tur: str, adaylar: list[dict], mac_sayisi: int = config.KUPON_MAC_SAYISI,
                  tutar: float = config.KUPON_TUTARI) -> list[dict]:
    secilen = adaylar[:mac_sayisi] if tur in SABIT_MAC_SAYILI else mbs_ile_sec(adaylar, mac_sayisi)
    if not secilen or (tur in SABIT_MAC_SAYILI and len(secilen) < mac_sayisi):
        return [{"tarih": tarih, "tur": tur, "sira": 0, "durum": "aday_yok", "tutar": 0, "kazanc": 0,
                 "secim": f"{len(adaylar)} aday"}]
    toplam = 1.0
    for a in secilen:
        toplam *= a["oran"]
    return [{**a, "tarih": tarih, "tur": tur, "sira": i + 1, "gercek": "", "tuttu": "",
             "toplam_oran": round(toplam, 2), "tutar": tutar, "durum": "bekliyor", "kazanc": ""}
            for i, a in enumerate(secilen)]


def gercek_sonuc(market: str, sonuc: dict) -> str:
    iy_ev, iy_dep, ms_ev, ms_dep = (int(sonuc[k]) for k in ("iy_ev", "iy_dep", "ms_ev", "ms_dep"))
    if market == "MS":
        return sonuc_isareti(ms_ev, ms_dep)
    if market == "Toplam gol":
        return f"{ms_ev + ms_dep} gol"
    if market in kalibrasyon.MARKETLER:
        return kalibrasyon.kazanan(market, iy_ev, iy_dep, ms_ev, ms_dep)
    return iyms_sonucu(iy_ev, iy_dep, ms_ev, ms_dep)


def tuttu_mu(market: str, secim: str, gercek: str) -> bool:
    if market == "Toplam gol":
        aralik = analiz.gol_araligi(secim)
        toplam = int(gercek.split()[0])
        return bool(aralik) and aralik[0] <= toplam <= aralik[1]
    return gercek == secim


def kupon_degerlendir(satirlar: list[dict], sonuclar: dict) -> None:
    """Aynı kupona ait satırları yerinde günceller."""
    if not satirlar or satirlar[0]["durum"] == "aday_yok":
        return
    for s in satirlar:
        if s["tuttu"] in ("1", "0", "iptal"):
            continue
        sonuc = sonuclar.get(str(s["mac_id"]))
        if not sonuc:
            continue
        if sonuc["durum"] == "iptal":
            s["tuttu"], s["gercek"] = "iptal", "iptal"
        elif sonuc["durum"] == "belirsiz":
            s["tuttu"], s["gercek"] = "?", "sonuç yok"
        elif sonuc["durum"] == "tamam":
            market = s.get("market") or "İY/MS"
            s["gercek"] = gercek_sonuc(market, sonuc)
            s["tuttu"] = "1" if tuttu_mu(market, s["secim"], s["gercek"]) else "0"
    tutar = float(satirlar[0]["tutar"])
    if any(s["tuttu"] == "0" for s in satirlar):
        durum, kazanc = "kaybetti", 0.0
    elif all(s["tuttu"] in ("1", "iptal") for s in satirlar):
        toplam = 1.0
        for s in satirlar:
            toplam *= 1.0 if s["tuttu"] == "iptal" else float(s["oran"])
        durum, kazanc = "kazandi", round(tutar * toplam, 2)
        for s in satirlar:
            s["toplam_oran"] = round(toplam, 2)
    elif all(s["tuttu"] for s in satirlar):
        durum, kazanc = "belirsiz", 0.0
    else:
        return
    for s in satirlar:
        s["durum"], s["kazanc"] = durum, kazanc


def kuponlari_oku() -> list[dict]:
    satirlar = depo.csv_oku(kupon_yolu())
    for s in satirlar:
        s["tur"] = s.get("tur") or "iyms"
        s["market"] = s.get("market") or ("İY/MS" if s["durum"] != "aday_yok" else "")
    return satirlar


def kuponlara_ayir(satirlar: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """{(tarih, tur): satırlar}"""
    kuponlar: dict[tuple[str, str], list[dict]] = {}
    for s in satirlar:
        kuponlar.setdefault((s["tarih"], s["tur"]), []).append(s)
    return kuponlar


def kasa(kuponlar: dict, tur: str) -> dict:
    oynanan = [g for (_, t), g in kuponlar.items() if t == tur and g[0]["durum"] not in ("aday_yok", "belirsiz")]
    yatirilan = sum(float(g[0]["tutar"]) for g in oynanan)
    donen = sum(float(g[0]["kazanc"] or 0) for g in oynanan if g[0]["durum"] == "kazandi")
    return {"kupon": len(oynanan), "kazanan": sum(1 for g in oynanan if g[0]["durum"] == "kazandi"),
            "sonuclanan": sum(1 for g in oynanan if g[0]["durum"] in ("kazandi", "kaybetti")),
            "yatirilan": yatirilan, "donen": donen, "net": donen - yatirilan,
            "kalan": config.KUPON_BUTCE - yatirilan + donen}


def calistir(simdi: datetime | None = None, olustur: bool = True) -> dict:
    """Tüm kuponları değerlendirir; olustur=True ise bugünün eksik kuponlarını oluşturur.
    Dönen özette 'yeni' anahtarı bu çalışmada kupon oluşturulup oluşturulmadığını söyler."""
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    tarih = simdi.astimezone(config.TR).date().isoformat()
    satirlar = kuponlari_oku()
    sonuclar = depo.sonuclari_oku()
    for grup in kuponlara_ayir(satirlar).values():
        kupon_degerlendir(grup, sonuclar)

    ozet = {"tarih": tarih, "yeni": False}
    mevcut = {(s["tarih"], s["tur"]) for s in satirlar}
    eksik = [t for t in TURLER if (tarih, t) not in mevcut] if olustur else []
    if eksik:
        ozet["yeni"] = True
        adaylar = oneriler(simdi)
        for tur in eksik:
            yeni = kupon_olustur(tarih, tur, adaylar[tur])
            satirlar += yeni
            ozet[tur] = f"{yeni[0]['durum']} ({len(adaylar[tur])} aday)"
        depo.json_yaz(depo.kok() / "adaylar" / f"{tarih}.json", adaylar)
    depo.csv_yaz(kupon_yolu(), satirlar, KUPON_ALANLARI)
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("özet: %s", calistir())


if __name__ == "__main__":
    main()
