"""Günlük rapor: dünkü kupon, bugünkü kupon, kasa, İY/MS istatistikleri, veri durumu.

Rapor data/raporlar/YYYY-MM-DD.md olarak repoya yazılır. GMAIL_ADRES ve GMAIL_UYGULAMA_SIFRESI
ortam değişkenleri tanımlıysa aynı rapor mail olarak da gönderilir.
"""
import html
import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import math

from . import analiz, config, depo, kupon, tekler
from .bulten import iso_oku, iyms_sonucu

log = logging.getLogger("rapor")
MAIL_ORANLARI = ["1.20", "1.30", "1.40", "1.50", "1.60", "1.70", "1.80", "1.90", "2.00", "2.20", "2.50",
                 "2.80", "3.00", "3.30", "3.60", "4.00", "4.50", "5.00"]
IYMS_SIRASI = ["1/1", "1/0", "1/2", "0/1", "0/0", "0/2", "2/1", "2/0", "2/2"]


class Rapor:
    def __init__(self, baslik: str):
        self.md = [f"# {baslik}", ""]
        self.htm = [f"<h2>{html.escape(baslik)}</h2>"]

    def bolum(self, baslik: str):
        self.md += [f"## {baslik}", ""]
        self.htm.append(f"<h3>{html.escape(baslik)}</h3>")

    def yazi(self, metin: str):
        self.md += [metin, ""]
        self.htm.append(f"<p>{html.escape(metin)}</p>")

    def tablo(self, basliklar: list[str], satirlar: list[list]):
        self.md.append("| " + " | ".join(basliklar) + " |")
        self.md.append("|" + "---|" * len(basliklar))
        for s in satirlar:
            self.md.append("| " + " | ".join(str(x) for x in s) + " |")
        self.md.append("")
        hucre = "border:1px solid #ccc;padding:4px 8px"
        self.htm.append('<table style="border-collapse:collapse;font-family:sans-serif;font-size:13px">')
        self.htm.append("<tr>" + "".join(f'<th style="{hucre};background:#f2f2f2">{html.escape(b)}</th>'
                                         for b in basliklar) + "</tr>")
        for s in satirlar:
            self.htm.append("<tr>" + "".join(f'<td style="{hucre}">{html.escape(str(x))}</td>' for x in s) + "</tr>")
        self.htm.append("</table>")


def _saat(iso_metin: str) -> str:
    return iso_oku(iso_metin).astimezone(config.TR).strftime("%d.%m %H:%M")


def _tl(tutar: float) -> str:
    return f"{tutar:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


def _yuzde(x: float) -> str:
    return f"%{100 * x:.1f}"


def _ms_tablosu(rapor: Rapor, satirlar: list[dict], maks: bool = True):
    basliklar = ["Oran", "Örnek", "Tutma %", "Oranın vaadi %", "Getiri (1 TL'ye)", "Hata payı"]
    if maks:
        basliklar.append("Getiri (en iyi oranla)")
    rapor.tablo(basliklar, [
        [s["oran"], s["ornek"], _yuzde(s["tutma"]), _yuzde(s["vaat"]), f"{s['getiri']:.3f}", f"±{s['hata']:.2f}"]
        + ([f"{s['getiri_maks']:.3f}"] if maks else [])
        for s in satirlar
    ])


def _gecmis_bolumu(rapor: Rapor):
    ozet = depo.json_oku(analiz.analiz_yolu("gecmis_ozet.json"))
    ms = analiz.ms_tablosu_oku()
    kosullu = analiz.kosullu_oku()
    if not ozet or not ms:
        return
    rapor.bolum("Geçmiş veri: MS 1-0-2 oranları ne sıklıkla tutuyor")
    rapor.yazi(f"{ozet['mac']:,} maç, {ozet['lig']} lig, {ozet['ilk']} – {ozet['son']}. "
               "Oranlar yabancı bahis şirketlerinin ortalaması; iddaa oranları genelde biraz daha düşüktür.")
    secili = {s["oran"]: s for s in ms if s["secim"] == "hepsi"}
    rapor.yazi("Sık görülen oranlar. Hata payı: getiri bu kadar şansla oynayabilir; payın içinde kalan fark "
               "tesadüf olabilir. Tüm oranlar panelde, arama kutusuna oranı (ör. 1.55) yazarak bakabilirsin.")
    _ms_tablosu(rapor, [secili[o] for o in MAIL_ORANLARI if o in secili])
    rapor.bolum("Geçmiş veri: ev sahibinin gücüne göre İY/MS adil oranları")
    rapor.yazi("Adil oran = 1 / gerçekleşme sıklığı. iddaa bu orandan yüksek veriyorsa seçim değerlidir.")
    satirlar = []
    for d, t in kosullu.items():
        if t["ornek"] < analiz.MIN_DILIM_ORNEGI:
            continue
        satirlar.append([d, t["ornek"]] + [f"{t['ornek'] / t[s]:.1f}" if t[s] else "-" for s in IYMS_SIRASI])
    satirlar.sort(key=lambda s: float(s[0].split("–")[0].lstrip("%")))
    rapor.tablo(["Ev kazanma olasılığı", "Örnek"] + IYMS_SIRASI, satirlar)


STRATEJI_ADI = {"mac_basi": "Her maçın en iyi seçimi", "hayal_model": "İY/MS 20–30, en mantıklı",
                "hayal_oran": "İY/MS 20–30, en yüksek oran"}


def _iddaa_gecmisi_bolumu(rapor: Rapor) -> bool:
    senaryo = depo.json_oku(analiz.analiz_yolu("iddaa_senaryolar.json"))
    if not senaryo:
        return False
    hayal = senaryo.get("hayal_kuponu") or {}
    if hayal.get("gun"):
        rapor.bolum(f"iddaa geçmişi: her gün 3 maçlık İY/MS kuponu ({config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g})")
        rapor.yazi(f"{hayal['ilk']} → {hayal['son']}: {hayal['gun']} gün, {_tl(hayal['harcanan'])} harcanırdı; "
                   f"{hayal['kazanan']} kupon tutardı, dönen {_tl(hayal['donen'])}. 3 maçın 2'si tutan gün: "
                   f"{hayal['iki_tutan']}. Aynı seçimler tek tek 1 TL: %"
                   f"{100 * hayal['tek_tutan'] / max(hayal['tek_bahis'], 1):.1f} tuttu, 1 TL → {hayal['tek_getiri']:.2f} "
                   f"(hata payı ±{hayal.get('tek_hata', 0):.2f}).")
    rapor.bolum("iddaa geçmişi: her seçime 1 TL oynasaydın")
    rapor.yazi(f"{senaryo['mac']:,} iddaa maçı ({senaryo.get('ilk', '')[:7]} → {senaryo.get('son', '')[:7]}), "
               "Kral oranla. 1 TL → 1'in altındaysa uzun vadede kaybettirir.")
    satirlar = [r for r in senaryo["satirlar"] if r["secenek"] == "hepsi"]
    rapor.tablo(["Bahis", "Oran aralığı", "Seçim sayısı", "Tuttu", "1 TL →", "Hata payı"],
                [[r["market"], r["bant"] or "hepsi", f"{r['bahis']:,}", _yuzde(r["tutma"]), f"{r['getiri_kral']:.3f}",
                  f"±{r.get('hata', 0):.2f}"]
                 for r in satirlar])
    test = depo.json_oku(analiz.analiz_yolu("geriye_test.json")) or {}
    secili = [r for r in test.get("satirlar", [])
              if (r["strateji"] == "mac_basi" and r["esik"] in (0.0, 0.9, 1.0)) or r["strateji"].startswith("hayal")]
    if secili:
        rapor.bolum("Model geriye dönük test (model test dönemini görmeden kuruldu)")
        rapor.tablo(["Strateji", "Bahis", "Beklenen eşiği", "Bahis sayısı", "Tuttu", "1 TL →", "Hata payı",
                     "Test dönemi"],
                    [[STRATEJI_ADI.get(r["strateji"], r["strateji"]), r["market"],
                      "hepsi" if not r["esik"] else f"≥ {r['esik']:.2f}", f"{r['bahis']:,}",
                      _yuzde(r["tutan"] / r["bahis"]) if r["bahis"] else "-", f"{r['getiri_kral']:.3f}",
                      f"±{r.get('hata', 0):.2f}", r.get("test", "")]
                     for r in sorted(secili, key=lambda r: (r["market"], r["strateji"], r["esik"]))])
    tekli = tekler.degerlendir()
    if tekli["satirlar"]:
        rapor.bolum("Sanal tekliler (maça yakın değerli seçimler, 1 TL)")
        rapor.tablo(["Bahis", "Beklenen", "Bahis sayısı", "Tuttu", "1 TL →", "Modelin beklentisi", "CLV"],
                    [[r["market"], r["dilim"] or "hepsi", r["bahis"], _yuzde(r["tutan"] / r["bahis"]),
                      f"{r['getiri']:.3f}", f"{r['beklenen']:.2f}", f"{r['clv']:.3f}" if r["clv"] else "-"]
                     for r in tekli["satirlar"]])
    return True


def _aday_bolumu(rapor: Rapor, simdi: datetime):
    adaylar = kupon.oneriler(simdi)
    for tur, ad in kupon.TURLER.items():
        rapor.bolum(f"Şu anki {ad.replace(' kuponu', '')} adayları (en iyi 5)")
        if not adaylar[tur]:
            rapor.yazi("Aday yok.")
            continue
        rapor.tablo(["Maç", "Lig", "Başlama", "Seçim", "Oran", "Tutma şansı", "1 TL'ye dönen"],
                    [[f"{a['ev']} - {a['dep']}", a["lig"], _saat(a["baslama_utc"]), a["secim"], a["oran"],
                      _yuzde(float(a["tutma"])) if a.get("tutma") not in ("", None) else "-",
                      f"{float(a['beklenen']):.2f}" if a.get("beklenen") not in ("", None) else "-"]
                     for a in adaylar[tur][:5]])
    rapor.yazi("1 TL'ye dönen 1'in altındaysa o seçim uzun vadede kaybettirir.")


def iyms_istatistik(kapanis: dict, sonuclar: dict, min_oran: float | None = None,
                    max_oran: float | None = None) -> dict[str, dict]:
    """Seçenek bazında: kaç kez oynanabilirdi, kaç kez tuttu, vaat edilen ve gerçek oran, getiri."""
    tablo = {s: {"n": 0, "tuttu": 0, "vaat": 0.0, "donus": 0.0} for s in IYMS_SIRASI}
    for mac_id, oranlar in kapanis.items():
        sonuc = sonuclar.get(mac_id)
        if not sonuc or sonuc.get("durum") != "tamam":
            continue
        gercek = iyms_sonucu(int(sonuc["iy_ev"]), int(sonuc["iy_dep"]), int(sonuc["ms_ev"]), int(sonuc["ms_dep"]))
        for secim, oran in oranlar.items():
            if secim not in tablo:
                continue
            if min_oran is not None and oran < min_oran:
                continue
            if max_oran is not None and oran > max_oran:
                continue
            t = tablo[secim]
            t["n"] += 1
            t["vaat"] += 1 / oran
            if secim == gercek:
                t["tuttu"] += 1
                t["donus"] += oran
    return tablo


def _istatistik_tablosu(rapor: Rapor, tablo: dict):
    satirlar = []
    toplam = {"n": 0, "tuttu": 0, "vaat": 0.0, "donus": 0.0}
    for secim in IYMS_SIRASI:
        t = tablo[secim]
        if not t["n"]:
            continue
        for k in toplam:
            toplam[k] += t[k]
        satirlar.append([secim, t["n"], t["tuttu"], f"%{100 * t['tuttu'] / t['n']:.1f}",
                         f"%{100 * t['vaat'] / t['n']:.1f}", f"{t['donus'] / t['n']:.2f}"])
    if not satirlar:
        rapor.yazi("Henüz sonucu belli olan veri yok.")
        return
    satirlar.append(["Toplam", toplam["n"], toplam["tuttu"], f"%{100 * toplam['tuttu'] / toplam['n']:.1f}",
                     f"%{100 * toplam['vaat'] / toplam['n']:.1f}", f"{toplam['donus'] / toplam['n']:.2f}"])
    rapor.tablo(["Seçim", "Örnek", "Tuttu", "Gerçek %", "Oranın vaadi %", "Getiri (1 TL'ye)"], satirlar)


SONUC_ETIKETI = {"1": "✅", "0": "❌", "iptal": "iptal", "?": "sonuç yok"}
DURUM_ETIKETI = {"bekliyor": "Bekliyor", "kaybetti": "Kaybetti", "belirsiz": "Sonuç bulunamadı"}


def _kupon_bolumu(rapor: Rapor, baslik: str, satirlar: list[dict] | None, tur: str):
    rapor.bolum(baslik)
    if not satirlar:
        rapor.yazi("Kupon yok.")
        return
    ilk = satirlar[0]
    if ilk["durum"] == "aday_yok":
        neden = {"iyms": f"Oranı {config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g} arası İY/MS seçeneği olan",
                 "ms": f"Oranı {config.MS_KUPON_MIN_ORAN:.2f}–{config.MS_KUPON_MAX_ORAN:.2f} arası ve geçmiş verisi olan",
                 }.get(tur, "Geçmiş verisi olan")
        rapor.yazi(f"{neden} yeterli maç yoktu ({ilk['secim']}), kupon oluşturulmadı.")
        return
    rapor.tablo(["Maç", "Lig", "Başlama", "Market", "Seçim", "Oran", "Şans", "1 TL →", "MBS", "Sonuç"],
                [[f"{s['ev']} - {s['dep']}", s["lig"], _saat(s["baslama_utc"]), s["market"], s["secim"], s["oran"],
                  _yuzde(float(s["tutma"])) if s.get("tutma") not in ("", None) else "-",
                  f"{float(s['beklenen']):.2f}" if s.get("beklenen") not in ("", None) else "-", s.get("mbs") or "-",
                  f"{SONUC_ETIKETI[s['tuttu']]} {s['gercek']}".strip() if s["tuttu"] in SONUC_ETIKETI else "bekliyor"]
                 for s in satirlar])
    durum = (f"KAZANDI: {_tl(float(ilk['kazanc']))}" if ilk["durum"] == "kazandi"
             else DURUM_ETIKETI.get(ilk["durum"], ilk["durum"]))
    try:
        beklenen = f" · Beklenen: 1 TL → {math.prod(float(s['beklenen']) for s in satirlar):.2f} TL"
    except (KeyError, TypeError, ValueError):
        beklenen = ""
    rapor.yazi(f"{len(satirlar)} maç · Toplam oran: {ilk['toplam_oran']} · Tutar: {_tl(float(ilk['tutar']))}"
               f"{beklenen} · Durum: {durum}")


def olustur(simdi: datetime | None = None) -> Rapor:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    bugun = simdi.astimezone(config.TR).date()
    dun = bugun - timedelta(days=1)
    kuponlar = kupon.kuponlara_ayir(kupon.kuponlari_oku())
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()

    rapor = Rapor(f"iddaa günlük rapor — {bugun.strftime('%d.%m.%Y')}")
    for tur, ad in kupon.TURLER.items():
        _kupon_bolumu(rapor, f"Bugünkü {ad}", kuponlar.get((bugun.isoformat(), tur)), tur)
    for tur, ad in kupon.TURLER.items():
        _kupon_bolumu(rapor, f"Dünkü {ad}", kuponlar.get((dun.isoformat(), tur)), tur)

    rapor.bolum("Kağıt üstü kasa")
    rapor.tablo(["Kupon türü", "Kupon", "Kazanan", "Yatırılan", "Dönen", "Net", "Bütçeden kalan"],
                [[ad, k["kupon"], k["kazanan"], _tl(k["yatirilan"]), _tl(k["donen"]), _tl(k["net"]), _tl(k["kalan"])]
                 for tur, ad in kupon.TURLER.items() for k in [kupon.kasa(kuponlar, tur)]])

    kapanis_tum = analiz.kapanis_oranlari(kayitlar, {config.IYMS, analiz.MS})
    kapanis = {m: v[config.IYMS] for m, v in kapanis_tum.items() if config.IYMS in v}

    _aday_bolumu(rapor, simdi)
    if _iddaa_gecmisi_bolumu(rapor):
        _veri_durumu(rapor, simdi, kayitlar, sonuclar, kapanis)
        return rapor
    _gecmis_bolumu(rapor)

    rapor.bolum("iddaa verisi: MS oranları (en çok örneği olan 10 oran)")
    ms_satirlari = [s for s in analiz.iddaa_ms_tablosu(kapanis_tum, sonuclar) if s["secim"] == "hepsi"]
    if ms_satirlari:
        _ms_tablosu(rapor, sorted(ms_satirlari, key=lambda r: -r["ornek"])[:10], maks=False)
    else:
        rapor.yazi("Henüz sonucu belli olan veri yok.")

    rapor.bolum(f"iddaa verisi: İY/MS tek seçim (oran {config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g})")
    rapor.yazi("Getiri 1'in üstündeyse o seçim uzun vadede kazandırıyor demektir.")
    _istatistik_tablosu(rapor, iyms_istatistik(kapanis, sonuclar, config.KUPON_MIN_ORAN, config.KUPON_MAX_ORAN))
    rapor.bolum("iddaa verisi: İY/MS tüm oranlar")
    _istatistik_tablosu(rapor, iyms_istatistik(kapanis, sonuclar))

    _veri_durumu(rapor, simdi, kayitlar, sonuclar, kapanis)
    return rapor


def _veri_durumu(rapor: Rapor, simdi: datetime, kayitlar: dict, sonuclar: dict, kapanis: dict):
    rapor.bolum("Veri durumu")
    son24 = simdi - timedelta(hours=24)
    dosyalar = [d for d in depo.oran_dosyalari(son24)]
    yeni_mac = [k for k in kayitlar.values() if k.get("ilk_gorulme_utc", "") >= son24.strftime("%Y-%m-%dT%H:%M:%SZ")]
    tamam = sum(1 for s in sonuclar.values() if s.get("durum") == "tamam")
    rapor.tablo(["Son 24 saatte çalışma", "Yeni maç", "İY/MS'li yeni maç", "Toplam maç", "Sonuçlu maç",
                 "Kapanış İY/MS'si olan"],
                [[len(dosyalar), len(yeni_mac), sum(1 for k in yeni_mac if k.get("iyms_var") == "1"),
                  len(kayitlar), tamam, len(kapanis)]])


def mail_gonder(rapor: Rapor, konu: str) -> bool:
    adres = os.environ.get("GMAIL_ADRES")
    sifre = os.environ.get("GMAIL_UYGULAMA_SIFRESI")
    if not adres or not sifre:
        log.info("Mail ayarları yok, mail gönderilmedi.")
        return False
    mesaj = EmailMessage()
    mesaj["Subject"] = konu
    mesaj["From"] = adres
    mesaj["To"] = os.environ.get("MAIL_ALICI") or adres
    mesaj.set_content("\n".join(rapor.md))
    mesaj.add_alternative("<html><body>" + "\n".join(rapor.htm) + "</body></html>", subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(adres, sifre.replace(" ", ""))
        smtp.send_message(mesaj)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    simdi = datetime.now(timezone.utc)
    rapor = olustur(simdi)
    tarih = simdi.astimezone(config.TR).date()
    yol = depo.kok() / "raporlar" / f"{tarih.isoformat()}.md"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("\n".join(rapor.md), encoding="utf-8")
    log.info("rapor yazıldı: %s", yol)
    if mail_gonder(rapor, f"iddaa rapor {tarih.strftime('%d.%m.%Y')}"):
        log.info("mail gönderildi")


if __name__ == "__main__":
    main()
