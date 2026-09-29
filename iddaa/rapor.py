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

from . import analiz, config, depo
from .bulten import iso_oku, iyms_sonucu
from .kupon import gunlere_ayir, kupon_yolu

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


def _deger_bolumu(rapor: Rapor, simdi: datetime, kayitlar: dict):
    kosullu = analiz.kosullu_oku()
    if not kosullu:
        return
    oranlar = analiz.son_oranlar(simdi, {config.IYMS, analiz.MS})
    adaylar = [a for a in analiz.deger_adaylari(oranlar, kayitlar, kosullu, simdi) if a["beklenen"] > 1]
    rapor.bolum("Önümüzdeki 24 saat: geçmiş veriye göre değerli görünen seçimler")
    if not adaylar:
        rapor.yazi("iddaa oranı geçmiş sıklığın üstünde kalan seçim yok.")
        return
    rapor.yazi("Beklenen = iddaa oranı × geçmişteki gerçek sıklık. 1'in üstü teoride kârlı; lig farkları "
               "hesaba katılmadığı için kesin değil, doğrulama verisi biriktikçe netleşecek.")
    rapor.tablo(["Maç", "Lig", "Başlama", "Market", "Seçim", "iddaa oranı", "Adil oran", "Beklenen"],
                [[f"{a['ev']} - {a['dep']}", a["lig"], _saat(a["baslama_utc"]), a["market"], a["secim"],
                  a["oran"], a["adil_oran"], f"{a['beklenen']:.2f}"] for a in adaylar[:15]])


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


def _kupon_bolumu(rapor: Rapor, baslik: str, satirlar: list[dict] | None):
    rapor.bolum(baslik)
    if not satirlar:
        rapor.yazi("Kupon yok.")
        return
    ilk = satirlar[0]
    if ilk["durum"] == "aday_yok":
        rapor.yazi(f"Oranı {config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g} arası İY/MS seçeneği olan "
                   f"yeterli maç yoktu ({ilk['secim']}), kupon oluşturulmadı.")
        return
    rapor.tablo(["Maç", "Lig", "Başlama", "Seçim", "Oran", "Sonuç"],
                [[f"{s['ev']} - {s['dep']}", s["lig"], _saat(s["baslama_utc"]), s["secim"], s["oran"],
                  {"1": f"✅ {s['gercek']}", "0": f"❌ {s['gercek']}", "iptal": "iptal"}.get(s["tuttu"], "bekliyor")]
                 for s in satirlar])
    durum = {"bekliyor": "Bekliyor", "kazandi": f"KAZANDI: {_tl(float(ilk['kazanc']))}",
             "kaybetti": "Kaybetti"}.get(ilk["durum"], ilk["durum"])
    rapor.yazi(f"Toplam oran: {ilk['toplam_oran']} · Tutar: {_tl(float(ilk['tutar']))} · Durum: {durum}")


def olustur(simdi: datetime | None = None) -> Rapor:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    bugun = simdi.astimezone(config.TR).date()
    dun = bugun - timedelta(days=1)
    kuponlar = gunlere_ayir(depo.csv_oku(kupon_yolu()))
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()

    rapor = Rapor(f"iddaa günlük rapor — {bugun.strftime('%d.%m.%Y')}")
    _kupon_bolumu(rapor, "Dünkü kupon", kuponlar.get(dun.isoformat()))
    _kupon_bolumu(rapor, "Bugünkü kupon", kuponlar.get(bugun.isoformat()))

    rapor.bolum("Kağıt üstü kasa")
    oynanan = [g for g in kuponlar.values() if g[0]["durum"] != "aday_yok"]
    yatirilan = sum(float(g[0]["tutar"]) for g in oynanan)
    donen = sum(float(g[0]["kazanc"] or 0) for g in oynanan if g[0]["durum"] == "kazandi")
    kazanan = sum(1 for g in oynanan if g[0]["durum"] == "kazandi")
    rapor.tablo(["Kupon", "Kazanan", "Yatırılan", "Dönen", "Net", "Bütçeden kalan"],
                [[len(oynanan), kazanan, _tl(yatirilan), _tl(donen), _tl(donen - yatirilan),
                  _tl(config.KUPON_BUTCE - yatirilan + donen)]])

    kapanis_tum = analiz.kapanis_oranlari(kayitlar, {config.IYMS, analiz.MS})
    kapanis = {m: v[config.IYMS] for m, v in kapanis_tum.items() if config.IYMS in v}

    _deger_bolumu(rapor, simdi, kayitlar)
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

    rapor.bolum("Veri durumu")
    son24 = simdi - timedelta(hours=24)
    dosyalar = [d for d in depo.oran_dosyalari(son24)]
    yeni_mac = [k for k in kayitlar.values() if k.get("ilk_gorulme_utc", "") >= son24.strftime("%Y-%m-%dT%H:%M:%SZ")]
    tamam = sum(1 for s in sonuclar.values() if s.get("durum") == "tamam")
    rapor.tablo(["Son 24 saatte çalışma", "Yeni maç", "İY/MS'li yeni maç", "Toplam maç", "Sonuçlu maç",
                 "Kapanış İY/MS'si olan"],
                [[len(dosyalar), len(yeni_mac), sum(1 for k in yeni_mac if k.get("iyms_var") == "1"),
                  len(kayitlar), tamam, len(kapanis)]])
    return rapor


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
