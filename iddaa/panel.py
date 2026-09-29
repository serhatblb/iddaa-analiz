"""Statik panel: docs/index.html (+ docs/veri/*.json).

GitHub Pages (main / docs) ile yayınlanır. Dış bağımlılık yok. Büyük tablolar ayrı JSON dosyalarında
tutulur ve sayfa açılınca yüklenir; böylece her saat değişen index.html küçük kalır.
"""
import html
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import analiz, config, depo, kupon
from .bulten import iso_oku
from .rapor import IYMS_SIRASI, iyms_istatistik

log = logging.getLogger("panel")
HEDEF = Path("docs")
MS_ALANLARI = ["secim", "oran", "ornek", "tutma", "vaat", "getiri", "hata", "getiri_maks"]

CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--yazi:#1d2330;--soluk:#6b7385;--cizgi:#e3e6ec;--iyi:#1f8a4c;--kotu:#c0392b;
--vurgu:#2f5bea;--iyi-bg:#e6f4ec;--kotu-bg:#fbeaea;--uyari-bg:#fff6e0;--uyari:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--kart:#1a1f29;--yazi:#e6e9ef;--soluk:#9aa3b5;
--cizgi:#2a3140;--iyi:#4cc47f;--kotu:#ef6b5b;--vurgu:#7a9bff;--iyi-bg:#17301f;--kotu-bg:#3a1c1c;
--uyari-bg:#3a2f14;--uyari:#f0c36a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--yazi);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:1200px;margin:auto}h1{margin:0;font-size:22px}
.alt{color:var(--soluk);font-size:13px}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--cizgi);z-index:2}
nav div{max-width:1200px;margin:auto;padding:8px 16px;display:flex;gap:16px;overflow-x:auto;white-space:nowrap}
nav a{color:var(--soluk);text-decoration:none;font-weight:500}nav a:hover{color:var(--vurgu)}
main{max-width:1200px;margin:auto;padding:8px 16px 48px}
section{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:16px;margin:16px 0}
h2{font-size:17px;margin:0 0 4px}h3{font-size:15px;margin:18px 0 6px}
p.not{color:var(--soluk);margin:0 0 12px;font-size:13px}
.kartlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px}
.kupon{border:1px solid var(--cizgi);border-radius:10px;padding:14px}
.kupon h3{margin:0 0 2px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.rozet{font-size:12px;font-weight:600;border-radius:999px;padding:2px 10px;background:var(--cizgi);color:var(--yazi)}
.rozet.kazandi{background:var(--iyi-bg);color:var(--iyi)}.rozet.kaybetti{background:var(--kotu-bg);color:var(--kotu)}
.rozet.onizleme{background:var(--uyari-bg);color:var(--uyari)}
.toplam{display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;font-size:13px;color:var(--soluk)}
.toplam b{color:var(--yazi);font-size:15px}
.ozet{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:8px}
.ozet div{border:1px solid var(--cizgi);border-radius:8px;padding:10px}
.ozet b{display:block;font-size:20px}.ozet span{color:var(--soluk);font-size:12px}
.tablo{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--cizgi);text-align:right;white-space:nowrap}
th{color:var(--soluk);font-weight:600;font-size:12px}th:first-child,td:first-child{text-align:left}
td.sol,th.sol{text-align:left}td.soluk{color:var(--soluk)}.iyi{color:var(--iyi);font-weight:600}.kotu{color:var(--kotu)}
td.secim{font-weight:700}.bos{color:var(--soluk);font-style:italic}
.filtre{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 10px}.filtre label{font-size:12px;color:var(--soluk);
display:flex;flex-direction:column;gap:3px}.filtre select,.filtre input{font:inherit;color:var(--yazi);
background:var(--bg);border:1px solid var(--cizgi);border-radius:6px;padding:5px 8px;min-width:110px}
.kaydir{max-height:520px;overflow:auto}.kaydir thead th{position:sticky;top:0;background:var(--kart)}
table.siralanir th{cursor:pointer;user-select:none}table.siralanir th[data-yon=azalan]::after{content:" ▼"}
table.siralanir th[data-yon=artan]::after{content:" ▲"}
"""

JS = """
function yuzde(x){return '%'+(100*x).toFixed(1)}
function getiriTd(x){return '<td data-d="'+x+'" class="'+(x>1?'iyi':'kotu')+'">'+x.toFixed(3)+'</td>'}
document.querySelectorAll('.oran-tablosu').forEach(function(kutu){
  var t=kutu.querySelector('table'), say=kutu.querySelector('.sayac'), f=kutu.querySelector('.filtre'), maks=kutu.dataset.maks==='1';
  fetch(kutu.dataset.kaynak).then(function(r){return r.json()}).then(function(v){
    var a=v.alanlar, html=[];
    v.satirlar.forEach(function(s){
      var r={}; a.forEach(function(k,i){r[k]=s[i]});
      html.push('<tr data-secim="'+r.secim+'" data-oran="'+r.oran+'" data-ornek="'+r.ornek+'">'
        +'<td data-d="'+r.oran+'">'+r.oran+'</td><td data-d="'+r.ornek+'">'+r.ornek.toLocaleString('tr-TR')+'</td>'
        +'<td data-d="'+r.tutma+'">'+yuzde(r.tutma)+'</td><td data-d="'+r.vaat+'">'+yuzde(r.vaat)+'</td>'
        +getiriTd(r.getiri)+'<td data-d="'+r.hata+'" class="soluk">±'+r.hata.toFixed(2)+'</td>'
        +(maks?getiriTd(r.getiri_maks):'')+'</tr>');
    });
    t.tBodies[0].innerHTML=html.join('');
    uygula();
  }).catch(function(){say.textContent='Veri yüklenemedi.'});
  function uygula(){
    var secim=f.querySelector('.f-secim').value, oran=f.querySelector('.f-oran').value.trim().replace(',','.'),
        esik=+f.querySelector('.f-ornek').value, n=0;
    [].forEach.call(t.tBodies[0].rows,function(tr){
      var g=tr.dataset.secim===secim && +tr.dataset.ornek>=esik && (!oran || tr.dataset.oran.indexOf(oran)===0);
      tr.style.display=g?'':'none'; if(g) n++;
    });
    say.textContent=n+' oran gösteriliyor'+(esik<300?' · az örnekli oranlarda sonuç şansa çok bağlıdır':'');
  }
  f.querySelectorAll('select,input').forEach(function(e){e.addEventListener('input',uygula)});
});
document.querySelectorAll('table.siralanir th').forEach(function(th,i0){
  th.addEventListener('click',function(){
    var t=th.closest('table'), i=[].indexOf.call(th.parentNode.children,th), azalan=th.dataset.yon!=='azalan';
    t.querySelectorAll('th').forEach(function(x){delete x.dataset.yon});
    th.dataset.yon=azalan?'azalan':'artan';
    var s=[].slice.call(t.tBodies[0].rows);
    s.sort(function(a,b){var x=+a.cells[i].dataset.d, y=+b.cells[i].dataset.d; return azalan?y-x:x-y});
    s.forEach(function(r){t.tBodies[0].appendChild(r)});
  });
});
"""


def _e(x) -> str:
    return html.escape(str(x))


def _tablo(basliklar: list[str], satirlar: list[list], sol: int = 1) -> str:
    """sol: soldan kaç sütun sola dayalı."""
    if not satirlar:
        return '<p class="bos">Henüz veri yok.</p>'
    bas = "".join(f'<th class="{"sol" if i < sol else ""}">{_e(b)}</th>' for i, b in enumerate(basliklar))
    govde = []
    for s in satirlar:
        hucreler = "".join(h if isinstance(h, str) and h.startswith("<td") else
                           f'<td class="{"sol" if i < sol else ""}">{_e(h)}</td>' for i, h in enumerate(s))
        govde.append(f"<tr>{hucreler}</tr>")
    return f'<div class="tablo"><table><thead><tr>{bas}</tr></thead><tbody>{"".join(govde)}</tbody></table></div>'


def _getiri(x: float) -> str:
    return f'<td class="{"iyi" if x > 1 else "kotu"}">{x:.3f}</td>'


def _saat(iso_metin: str) -> str:
    return iso_oku(iso_metin).astimezone(config.TR).strftime("%d.%m %H:%M")


def _tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")


def _secim_hucresi(secim: str) -> str:
    return f'<td class="secim">{_e(secim)}</td>'


SONUC = {"1": '<td class="iyi">✅ {g}</td>', "0": '<td class="kotu">❌ {g}</td>',
         "iptal": '<td class="soluk">iptal (oran 1)</td>', "?": '<td class="soluk">sonuç yok</td>'}
DURUM = {"bekliyor": ("Bekliyor", ""), "kazandi": ("KAZANDI", "kazandi"), "kaybetti": ("Kaybetti", "kaybetti"),
         "belirsiz": ("Sonuç yok", "")}


def _kupon_satirlari(satirlar: list[dict], sonuc_goster: bool) -> list[list]:
    tablo = []
    for s in satirlar:
        satir = [f"{s['ev']} - {s['dep']}", s["lig"], _saat(s["baslama_utc"]), s["market"],
                 _secim_hucresi(s["secim"]), f"{float(s['oran']):.2f}"]
        if s.get("beklenen") not in ("", None):
            satir.append(f"{float(s['beklenen']):.2f}")
        if sonuc_goster:
            satir.append(SONUC[s["tuttu"]].format(g=_e(s["gercek"])) if s.get("tuttu") in SONUC else '<td>bekliyor</td>')
        tablo.append(satir)
    return tablo


def _kupon_karti(tur: str, ad: str, sabit: list[dict] | None, adaylar: list[dict], tarih: str) -> str:
    deger = tur == "deger"
    aciklama = (f"Oranı {config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g} arası İY/MS seçeneklerinden en yüksek oranlı "
                f"{config.KUPON_MAC_SAYISI} maç." if not deger else
                "MS 1-0-2 ve İY/MS içinden, geçmiş veriye göre beklenen dönüşü en yüksek "
                f"{config.KUPON_MAC_SAYISI} seçim (1'in üstündekiler).")
    basliklar = ["Maç", "Lig", "Başlama", "Market", "Seçim", "Oran"] + (["Beklenen"] if deger else [])
    if sabit and sabit[0]["durum"] != "aday_yok":
        etiket, sinif = DURUM.get(sabit[0]["durum"], (sabit[0]["durum"], ""))
        ilk = sabit[0]
        kazanc = f" · Kazanç <b>{_tl(float(ilk['kazanc']))}</b>" if ilk["durum"] == "kazandi" else ""
        govde = (_tablo(basliklar + ["Sonuç"], _kupon_satirlari(sabit, True), sol=2)
                 + f'<div class="toplam"><span>Toplam oran <b>{float(ilk["toplam_oran"]):,.2f}</b></span>'
                 f'<span>Tutar <b>{_tl(float(ilk["tutar"]))}</b></span>'
                 f'<span>Olası kazanç <b>{_tl(float(ilk["tutar"]) * float(ilk["toplam_oran"]))}</b></span>{kazanc}</div>')
        rozet = f'<span class="rozet {sinif}">{_e(etiket)}</span>'
        not_ = f"{tarih} tarihli kupon, sabah 09:43'te sabitlendi."
    else:
        secilen = adaylar[:config.KUPON_MAC_SAYISI]
        rozet = '<span class="rozet onizleme">Önizleme</span>'
        if sabit:
            not_ = f"Bugün sabah yeterli aday yoktu ({_e(sabit[0]['secim'])}). Şu anki oranlarla seçilseydi:"
        else:
            not_ = "Kupon her sabah 09:43'te sabitlenir. Şu anki oranlarla seçilseydi:"
        if len(secilen) < config.KUPON_MAC_SAYISI:
            govde = f'<p class="bos">Şu an yeterli aday yok ({len(adaylar)} aday). Liste her saat güncelleniyor.</p>'
        else:
            toplam = 1.0
            for a in secilen:
                toplam *= a["oran"]
            govde = (_tablo(basliklar, _kupon_satirlari(secilen, False), sol=2)
                     + f'<div class="toplam"><span>Toplam oran <b>{toplam:,.2f}</b></span>'
                     f'<span>{_tl(config.KUPON_TUTARI)} ile olası kazanç <b>{_tl(config.KUPON_TUTARI * toplam)}</b></span></div>')
    return (f'<div class="kupon"><h3>{_e(ad)} {rozet}</h3><p class="not">{_e(aciklama)} {_e(not_)}</p>'
            f"{govde}</div>")


def _aday_tablosu(adaylar: list[dict], deger: bool) -> str:
    basliklar = ["Maç", "Lig", "Başlama", "Market", "Seçim", "Oran"]
    if deger:
        basliklar += ["Adil oran", "Beklenen"]
    satirlar = []
    for a in adaylar[:25]:
        satir = [f"{a['ev']} - {a['dep']}", a["lig"], _saat(a["baslama_utc"]), a["market"],
                 _secim_hucresi(a["secim"]), f"{a['oran']:.2f}"]
        if deger:
            satir += [f"{a['oran'] / a['beklenen']:.2f}", _getiri(a["beklenen"])]
        satirlar.append(satir)
    return _tablo(basliklar, satirlar, sol=2)


def _oran_tablosu(kaynak: str, secimler: dict[str, str], maks: bool) -> str:
    secenekler = "".join(f'<option value="{k}">{_e(v)}</option>' for k, v in secimler.items())
    basliklar = ["Oran", "Örnek", "Tutma", "Oranın vaadi", "Getiri", "Hata payı"] + (["Getiri (en iyi oran)"] if maks else [])
    return (f'<div class="oran-tablosu" data-kaynak="{kaynak}" data-maks="{int(maks)}">'
            f'<div class="filtre"><label>Seçim <select class="f-secim">{secenekler}</select></label>'
            '<label>Oran <input class="f-oran" type="search" inputmode="decimal" placeholder="ör. 1.55"></label>'
            '<label>En az örnek <select class="f-ornek"><option value="1">hepsi</option><option value="30">30</option>'
            f'<option value="100">100</option><option value="300" {"selected" if maks else ""}>300</option>'
            '<option value="1000">1000</option></select></label></div>'
            '<div class="tablo kaydir"><table class="siralanir"><thead><tr>'
            + "".join(f"<th>{_e(b)}</th>" for b in basliklar)
            + '</tr></thead><tbody></tbody></table></div><p class="not sayac">Yükleniyor…</p></div>')


def _oran_json(satirlar: list[dict]) -> dict:
    return {"alanlar": MS_ALANLARI,
            "satirlar": [[r["secim"], r["oran"], r["ornek"], round(r["tutma"], 4), round(r["vaat"], 4),
                          round(r["getiri"], 4), round(r.get("hata") or 0, 4), round(r.get("getiri_maks") or 0, 4)]
                         for r in satirlar]}


SECIM_ADLARI = {"hepsi": "Tümü", "1": "Ev sahibi (1)", "0": "Beraberlik (0)", "2": "Deplasman (2)"}


def olustur(simdi: datetime | None = None) -> tuple[str, dict[str, dict]]:
    """(index.html içeriği, {dosya adı: json içeriği})"""
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    bugun = simdi.astimezone(config.TR).date().isoformat()
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()
    kuponlar = kupon.kuponlara_ayir(kupon.kuponlari_oku())
    adaylar = kupon.oneriler(simdi)
    kapanis_tum = analiz.kapanis_oranlari(kayitlar, {config.IYMS, analiz.MS})
    kapanis_iyms = {m: v[config.IYMS] for m, v in kapanis_tum.items() if config.IYMS in v}
    ozet_gecmis = depo.json_oku(analiz.analiz_yolu("gecmis_ozet.json")) or {}
    kosullu = analiz.kosullu_oku()
    iddaa_ms = analiz.iddaa_ms_tablosu(kapanis_tum, sonuclar)
    json_dosyalari = {"gecmis_ms.json": _oran_json([r for r in analiz.ms_tablosu_oku() if r["ornek"] >= 30]),
                      "iddaa_ms.json": _oran_json(iddaa_ms)}
    bolumler = []

    # 1. Kupon önerileri
    kartlar = "".join(_kupon_karti(tur, ad, kuponlar.get((bugun, tur)), adaylar[tur], bugun)
                      for tur, ad in kupon.TURLER.items())
    bolumler.append(("oneriler", "Kupon önerileri",
                     "Seçim kodları: MS'de 1 ev sahibi, 0 beraberlik, 2 deplasman. İY/MS'de ilk yarı/maç sonu, "
                     "ör. 2/1 = ilk yarı deplasman önde, maçı ev sahibi kazanır. Kağıt üstü; para yatırılmaz.",
                     f'<div class="kartlar">{kartlar}</div>'
                     f"<h3>Şu anki İY/MS adayları ({len(adaylar['iyms'])})</h3>"
                     + _aday_tablosu(adaylar["iyms"], False)
                     + f"<h3>Şu anki değer adayları ({len(adaylar['deger'])})</h3>"
                     '<p class="not">Beklenen = iddaa oranı × geçmişte aynı güçteki maçlarda gerçekleşme sıklığı. '
                     "1'in üstü teoride kârlı. Lig farkları hesaba katılmadı; canlı veri biriktikçe doğrulanacak.</p>"
                     + _aday_tablosu(adaylar["deger"], True)))

    # 2. Kasa ve kupon geçmişi
    kutular = ""
    for tur, ad in kupon.TURLER.items():
        k = kupon.kasa(kuponlar, tur)
        kutular += (f"<h3>{_e(ad)}</h3><div class=\"ozet\">"
                    + "".join(f"<div><b>{_e(v)}</b><span>{_e(e)}</span></div>" for e, v in [
                        ("Kupon", k["kupon"]), ("Sonuçlanan", k["sonuclanan"]), ("Kazanan", k["kazanan"]),
                        ("Yatırılan", _tl(k["yatirilan"])), ("Dönen", _tl(k["donen"])), ("Net", _tl(k["net"])),
                        ("Bütçeden kalan", _tl(k["kalan"]))]) + "</div>")
    gecmis_satirlari = []
    for (tarih, tur) in sorted(kuponlar, reverse=True):
        grup = kuponlar[(tarih, tur)]
        if grup[0]["durum"] == "aday_yok":
            gecmis_satirlari.append([tarih, kupon.TURLER[tur], "—", "", "", "", "", '<td class="soluk">aday yok</td>'])
            continue
        for s in grup:
            gecmis_satirlari.append([tarih, kupon.TURLER[tur], f"{s['ev']} - {s['dep']}", s["market"],
                                     _secim_hucresi(s["secim"]), f"{float(s['oran']):.2f}",
                                     SONUC[s["tuttu"]].format(g=_e(s["gercek"])) if s["tuttu"] in SONUC else "<td>bekliyor</td>",
                                     f'<td class="{DURUM.get(s["durum"], ("", ""))[1]}">{_e(DURUM.get(s["durum"], (s["durum"],))[0])}</td>'])
    bolumler.append(("kasa", "Kasa ve kupon geçmişi",
                     f"Her kupon {config.KUPON_TUTARI:g} TL, bütçe {config.KUPON_BUTCE:g} TL (kağıt üstü).",
                     kutular + "<h3>Kuponlar</h3>"
                     + _tablo(["Tarih", "Tür", "Maç", "Market", "Seçim", "Oran", "Sonuç", "Kupon"],
                              gecmis_satirlari[:120], sol=3)))

    # 3. Geçmiş MS oranları
    if ozet_gecmis:
        bolumler.append(("gecmis-ms", "Geçmiş veri: MS 1-0-2 oranları tek tek",
                         f"{ozet_gecmis.get('mac', 0):,} maç, {ozet_gecmis.get('lig', 0)} lig, "
                         f"{ozet_gecmis.get('ilk', '')} – {ozet_gecmis.get('son', '')}. Getiri 1 TL'ye dönen para, "
                         "1'in üstü kârlı. Hata payı: getiri şans eseri bu kadar oynayabilir, payın içindeki farklar "
                         "tesadüf olabilir. Oranlar yabancı şirketlerin ortalaması, iddaa genelde daha düşük verir. "
                         "Sütun başlığına tıklayarak sıralayabilirsin.",
                         _oran_tablosu("veri/gecmis_ms.json", SECIM_ADLARI, maks=True)))

    # 4. Koşullu İY/MS adil oranları
    if kosullu:
        satirlar = []
        for d, t in sorted(kosullu.items(), key=lambda kv: float(kv[0].split("–")[0].lstrip("%"))):
            if t["ornek"] < analiz.MIN_DILIM_ORNEGI:
                continue
            satirlar.append([d, f"{t['ornek']:,}"] + [f"{t['ornek'] / t[s]:.1f}" if t[s] else "-" for s in IYMS_SIRASI])
        bolumler.append(("gecmis-iyms", "Geçmiş veri: ev sahibinin gücüne göre İY/MS adil oranları",
                         "Adil oran = 1 / gerçekleşme sıklığı. iddaa bundan yüksek oran veriyorsa seçim değerlidir. "
                         "Ev kazanma olasılığı MS oranlarından, kâr payı ayıklanarak hesaplanır.",
                         _tablo(["Ev kazanma olasılığı", "Örnek"] + IYMS_SIRASI, satirlar)))

    # 5. iddaa verisi
    iyms_tablo = iyms_istatistik(kapanis_iyms, sonuclar)
    iyms_satirlari = [[s, t["n"], f"%{100 * t['tuttu'] / t['n']:.1f}", f"%{100 * t['vaat'] / t['n']:.1f}",
                       _getiri(t["donus"] / t["n"])] for s, t in iyms_tablo.items() if t["n"]]
    bolumler.append(("iddaa", "iddaa verisi (toplanan)",
                     "Sistemin kendi topladığı kapanış oranları ve sonuçlar. Sonuçlar geldikçe büyür.",
                     "<h3>MS oranları</h3>" + _oran_tablosu("veri/iddaa_ms.json", SECIM_ADLARI, maks=False)
                     + "<h3>İY/MS seçimleri</h3>"
                     + _tablo(["Seçim", "Örnek", "Tutma", "Oranın vaadi", "Getiri"], iyms_satirlari)))

    # 6. Veri durumu
    durumlar = {d: sum(1 for s in sonuclar.values() if s.get("durum") == d) for d in ("tamam", "iptal", "belirsiz")}
    baslamis = sum(1 for k in kayitlar.values() if iso_oku(k["baslama_utc"]) < simdi)
    bolumler.append(("durum", "Veri durumu", "Sonuçlar Mackolik'in canlı sonuç verisinden, iddaa maç numarasıyla eşleştirilir.",
                     _tablo(["Toplam maç", "İY/MS'li maç", "Başlamış", "Sonuçlanan", "İptal", "Sonuç bulunamayan",
                             "Kapanış oranı olan", "Güncelleme"],
                            [[len(kayitlar), sum(1 for k in kayitlar.values() if k.get("iyms_var") == "1"), baslamis,
                              durumlar["tamam"], durumlar["iptal"], durumlar["belirsiz"], len(kapanis_tum),
                              simdi.astimezone(config.TR).strftime("%d.%m.%Y %H:%M")]])))

    nav = "".join(f'<a href="#{i}">{_e(b.split(":")[0])}</a>' for i, b, _, _ in bolumler)
    govde = "".join(f'<section id="{i}"><h2>{_e(b)}</h2>' + (f'<p class="not">{_e(n)}</p>' if n else "") + c + "</section>"
                    for i, b, n, c in bolumler)
    sayfa = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>iddaa analiz</title><style>{CSS}</style></head><body>
<header><h1>iddaa analiz</h1><div class="alt">Son güncelleme {simdi.astimezone(config.TR).strftime('%d.%m.%Y %H:%M')} · kağıt üstü, para yatırılmaz</div></header>
<nav><div>{nav}</div></nav><main>{govde}</main><script>{JS}</script></body></html>"""
    return sayfa, json_dosyalari


def yaz(hedef: Path = HEDEF, simdi: datetime | None = None) -> None:
    sayfa, dosyalar = olustur(simdi)
    (hedef / "veri").mkdir(parents=True, exist_ok=True)
    (hedef / "index.html").write_text(sayfa, encoding="utf-8")
    (hedef / ".nojekyll").touch()
    for ad, icerik in dosyalar.items():
        (hedef / "veri" / ad).write_text(json.dumps(icerik, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    yaz()
    log.info("panel yazıldı: %s", HEDEF / "index.html")


if __name__ == "__main__":
    main()
