"""Statik panel: docs/index.html.

GitHub Pages (repo public ya da ücretli plan) veya Vercel (kök dizin: docs) ile yayınlanabilir.
Tamamen statik, dış bağımlılık yok; her çalışmada yeniden üretilir.
"""
import html
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import analiz, config, depo
from .bulten import iso_oku
from .kupon import gunlere_ayir, kupon_yolu
from .rapor import IYMS_SIRASI, iyms_istatistik

log = logging.getLogger("panel")

CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--yazi:#1d2330;--soluk:#6b7385;--cizgi:#e3e6ec;--iyi:#1f8a4c;--kotu:#c0392b;
--vurgu:#2f5bea;--iyi-bg:#e6f4ec;--kotu-bg:#fbeaea}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--kart:#1a1f29;--yazi:#e6e9ef;--soluk:#9aa3b5;
--cizgi:#2a3140;--iyi:#4cc47f;--kotu:#ef6b5b;--vurgu:#7a9bff;--iyi-bg:#17301f;--kotu-bg:#3a1c1c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--yazi);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:1200px;margin:auto}h1{margin:0;font-size:22px}
.alt{color:var(--soluk);font-size:13px}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--cizgi);z-index:2}
nav div{max-width:1200px;margin:auto;padding:8px 16px;display:flex;gap:16px;overflow-x:auto;white-space:nowrap}
nav a{color:var(--soluk);text-decoration:none;font-weight:500}nav a:hover{color:var(--vurgu)}
main{max-width:1200px;margin:auto;padding:8px 16px 48px}
section{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:16px;margin:16px 0}
h2{font-size:17px;margin:0 0 4px}p.not{color:var(--soluk);margin:0 0 12px;font-size:13px}
.ozet{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.ozet div{border:1px solid var(--cizgi);border-radius:8px;padding:10px}
.ozet b{display:block;font-size:20px}.ozet span{color:var(--soluk);font-size:12px}
.tablo{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--cizgi);text-align:right;white-space:nowrap}
th{color:var(--soluk);font-weight:600;font-size:12px}th:first-child,td:first-child{text-align:left}
td.sol{text-align:left}td.soluk{color:var(--soluk)}.iyi{color:var(--iyi);font-weight:600}.kotu{color:var(--kotu)}
td.cubuk{min-width:140px}td.cubuk i{display:inline-block;height:8px;border-radius:4px;background:var(--vurgu);
vertical-align:middle;margin-right:6px}
tr.iyi-satir{background:var(--iyi-bg)}.bos{color:var(--soluk);font-style:italic}
.filtre{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 10px}.filtre label{font-size:12px;color:var(--soluk);
display:flex;flex-direction:column;gap:3px}.filtre select,.filtre input{font:inherit;color:var(--yazi);
background:var(--bg);border:1px solid var(--cizgi);border-radius:6px;padding:5px 8px;min-width:110px}
.kaydir{max-height:520px;overflow:auto}.kaydir thead th{position:sticky;top:0;background:var(--kart)}
table.siralanir th{cursor:pointer;user-select:none}table.siralanir th[data-yon=azalan]::after{content:" ▼"}
table.siralanir th[data-yon=artan]::after{content:" ▲"}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _tablo(basliklar: list[str], satirlar: list[list], sinif_fn=None) -> str:
    if not satirlar:
        return '<p class="bos">Henüz veri yok.</p>'
    bas = "".join(f"<th>{_e(b)}</th>" for b in basliklar)
    govde = []
    for s in satirlar:
        sinif = sinif_fn(s) if sinif_fn else ""
        hucreler = "".join(h if isinstance(h, str) and h.startswith("<td") else f"<td>{_e(h)}</td>" for h in s)
        govde.append(f'<tr class="{sinif}">{hucreler}</tr>')
    return f'<div class="tablo"><table><thead><tr>{bas}</tr></thead><tbody>{"".join(govde)}</tbody></table></div>'


def _getiri(x: float) -> str:
    return f'<td class="{"iyi" if x > 1 else "kotu"}">{x:.3f}</td>'


def _cubuk(oran: float, azami: float) -> str:
    genislik = 0 if azami <= 0 else max(2, int(110 * oran / azami))
    return f'<td class="cubuk"><i style="width:{genislik}px"></i>%{100 * oran:.1f}</td>'


def _saat(iso_metin: str) -> str:
    return iso_oku(iso_metin).astimezone(config.TR).strftime("%d.%m %H:%M")


def _ms_satirlari(satirlar: list[dict], maks: bool) -> list[list]:
    azami = max((s["tutma"] for s in satirlar), default=1)
    return [[s["oran"], f"{s['ornek']:,}", _cubuk(s["tutma"], azami), f"%{100 * s['vaat']:.1f}",
             _getiri(s["getiri"])] + ([_getiri(s["getiri_maks"])] if maks else []) for s in satirlar]


SECIM_ADLARI = {"hepsi": "Tümü", "1": "Ev sahibi (1)", "0": "Beraberlik (0)", "2": "Deplasman (2)"}


def _oran_tablosu(kimlik: str, satirlar: list[dict], maks: bool) -> str:
    """Seçim filtresi, oran arama ve örnek eşiği olan, sütuna tıklayınca sıralanan tablo."""
    if not satirlar:
        return '<p class="bos">Henüz veri yok.</p>'
    secenekler = "".join(f'<option value="{k}">{_e(v)}</option>' for k, v in SECIM_ADLARI.items()
                         if any(r["secim"] == k for r in satirlar))
    kontroller = (f'<div class="filtre" data-tablo="{kimlik}">'
                  f'<label>Seçim <select class="f-secim">{secenekler}</select></label>'
                  '<label>Oran <input class="f-oran" type="search" inputmode="decimal" placeholder="ör. 1.55"></label>'
                  '<label>En az örnek <select class="f-ornek"><option value="30">30</option>'
                  '<option value="100">100</option><option value="300" selected>300</option>'
                  '<option value="1000">1000</option></select></label></div>')
    basliklar = ["Oran", "Örnek", "Tutma", "Oranın vaadi", "Getiri", "Hata payı"] + (["Getiri (en iyi oran)"] if maks else [])
    bas = "".join(f'<th data-sutun="{i}">{_e(b)}</th>' for i, b in enumerate(basliklar))
    govde = []
    for r in satirlar:
        hucreler = [
            f'<td data-d="{r["oran"]}">{_e(r["oran"])}</td>',
            f'<td data-d="{r["ornek"]}">{r["ornek"]:,}</td>',
            f'<td data-d="{r["tutma"]}">%{100 * r["tutma"]:.1f}</td>',
            f'<td data-d="{r["vaat"]}">%{100 * r["vaat"]:.1f}</td>',
            _getiri(r["getiri"]).replace("<td ", f'<td data-d="{r["getiri"]}" ', 1),
            f'<td data-d="{r.get("hata", 0)}" class="soluk">±{r.get("hata", 0):.2f}</td>',
        ]
        if maks:
            hucreler.append(_getiri(r["getiri_maks"]).replace("<td ", f'<td data-d="{r["getiri_maks"]}" ', 1))
        govde.append(f'<tr data-secim="{r["secim"]}" data-oran="{r["oran"]}" data-ornek="{r["ornek"]}">'
                     + "".join(hucreler) + "</tr>")
    return (kontroller + f'<div class="tablo kaydir"><table id="{kimlik}" class="siralanir"><thead><tr>{bas}</tr></thead>'
            f'<tbody>{"".join(govde)}</tbody></table></div><p class="not sayac" id="{kimlik}-sayac"></p>')


JS = """
document.querySelectorAll('.filtre').forEach(function(f){
  var t=document.getElementById(f.dataset.tablo), say=document.getElementById(f.dataset.tablo+'-sayac');
  function uygula(){
    var secim=f.querySelector('.f-secim').value, oran=f.querySelector('.f-oran').value.trim().replace(',', '.'),
        esik=+f.querySelector('.f-ornek').value, n=0;
    t.querySelectorAll('tbody tr').forEach(function(tr){
      var g=tr.dataset.secim===secim && +tr.dataset.ornek>=esik && (!oran || tr.dataset.oran.indexOf(oran)===0);
      tr.style.display=g?'':'none'; if(g) n++;
    });
    say.textContent=n+' oran gösteriliyor'+(esik<300?' · az örnekli oranlarda sonuç şansa çok bağlıdır':'');
  }
  f.querySelectorAll('select,input').forEach(function(e){e.addEventListener('input',uygula)});
  uygula();
});
document.querySelectorAll('table.siralanir th').forEach(function(th){
  th.addEventListener('click',function(){
    var t=th.closest('table'), i=+th.dataset.sutun, azalan=th.dataset.yon!=='azalan';
    t.querySelectorAll('th').forEach(function(x){delete x.dataset.yon});
    th.dataset.yon=azalan?'azalan':'artan';
    var satirlar=[].slice.call(t.tBodies[0].rows);
    satirlar.sort(function(a,b){var x=+a.cells[i].dataset.d, y=+b.cells[i].dataset.d; return azalan?y-x:x-y});
    satirlar.forEach(function(r){t.tBodies[0].appendChild(r)});
  });
});
"""


def olustur(simdi: datetime | None = None) -> str:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()
    kuponlar = gunlere_ayir(depo.csv_oku(kupon_yolu()))
    kapanis_tum = analiz.kapanis_oranlari(kayitlar, {config.IYMS, analiz.MS})
    kapanis_iyms = {m: v[config.IYMS] for m, v in kapanis_tum.items() if config.IYMS in v}
    ozet_gecmis = depo.json_oku(analiz.analiz_yolu("gecmis_ozet.json")) or {}
    ms_gecmis = analiz.ms_tablosu_oku()
    kosullu = analiz.kosullu_oku()
    bolumler = []

    # Kasa ve kuponlar
    oynanan = [g for g in kuponlar.values() if g[0]["durum"] != "aday_yok"]
    yatirilan = sum(float(g[0]["tutar"]) for g in oynanan)
    donen = sum(float(g[0]["kazanc"] or 0) for g in oynanan if g[0]["durum"] == "kazandi")
    kutular = [("Kupon", len(oynanan)), ("Kazanan", sum(1 for g in oynanan if g[0]["durum"] == "kazandi")),
               ("Yatırılan", f"{yatirilan:,.0f} TL"), ("Dönen", f"{donen:,.0f} TL"),
               ("Net", f"{donen - yatirilan:,.0f} TL"), ("Bütçeden kalan", f"{config.KUPON_BUTCE - yatirilan + donen:,.0f} TL")]
    kupon_satirlari = []
    for tarih in sorted(kuponlar, reverse=True):
        for s in kuponlar[tarih]:
            if s["durum"] == "aday_yok":
                kupon_satirlari.append([tarih, "—", "", "", "", "aday yok"])
                continue
            sonuc = {"1": f"✅ {s['gercek']}", "0": f"❌ {s['gercek']}", "iptal": "iptal"}.get(s["tuttu"], "bekliyor")
            kupon_satirlari.append([tarih, f"{s['ev']} - {s['dep']}", s["secim"], s["oran"], sonuc,
                                    {"bekliyor": "bekliyor", "kazandi": "KAZANDI", "kaybetti": "kaybetti"}.get(s["durum"], s["durum"])])
    bolumler.append(("kasa", "Kağıt üstü kasa ve kuponlar",
                     f"Her gün oranı {config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g} arası İY/MS seçeneklerinden "
                     f"{config.KUPON_MAC_SAYISI}'lü, {config.KUPON_TUTARI:g} TL'lik kağıt kupon.",
                     '<div class="ozet">' + "".join(f"<div><b>{_e(v)}</b><span>{_e(k)}</span></div>" for k, v in kutular)
                     + "</div><br>" + _tablo(["Tarih", "Maç", "Seçim", "Oran", "Sonuç", "Kupon"], kupon_satirlari[:60])))

    # Değer adayları
    oranlar = analiz.son_oranlar(simdi, {config.IYMS, analiz.MS})
    adaylar = [a for a in analiz.deger_adaylari(oranlar, kayitlar, kosullu, simdi) if a["beklenen"] > 1] if kosullu else []
    bolumler.append(("deger", "Önümüzdeki 24 saat: değerli görünen seçimler",
                     "Beklenen dönüş = iddaa oranı × geçmişte aynı güçteki maçlarda gerçekleşme sıklığı. "
                     "1'in üstü teoride kârlı. Lig farkları hesaba katılmadı; canlı veri biriktikçe doğrulanacak.",
                     _tablo(["Maç", "Lig", "Başlama", "Market", "Seçim", "iddaa oranı", "Adil oran", "Beklenen"],
                            [[f"{a['ev']} - {a['dep']}", a["lig"], _saat(a["baslama_utc"]), a["market"], a["secim"],
                              a["oran"], a["adil_oran"], _getiri(a["beklenen"])] for a in adaylar[:40]])))

    # Geçmiş MS: her oran tek tek
    if ms_gecmis:
        bolumler.append(("gecmis-ms", "Geçmiş veri: MS 1-0-2 oranları tek tek",
                         f"{ozet_gecmis.get('mac', 0):,} maç, {ozet_gecmis.get('lig', 0)} lig, "
                         f"{ozet_gecmis.get('ilk', '')} – {ozet_gecmis.get('son', '')}. Getiri 1 TL'ye dönen para, "
                         "1'in üstü kârlı. Oranlar yabancı şirketlerin ortalaması, iddaa genelde daha düşük verir. "
                         "Hata payı: getiri şans eseri bu kadar oynayabilir, payın içindeki farklar tesadüf olabilir. "
                         "Sütun başlığına tıklayarak sıralayabilirsin.",
                         _oran_tablosu("t-gecmis-ms", [r for r in ms_gecmis if r["ornek"] >= 30], maks=True)))

    # Koşullu İY/MS
    if kosullu:
        satirlar = []
        for d, t in sorted(kosullu.items(), key=lambda kv: float(kv[0].split("–")[0].lstrip("%"))):
            if t["ornek"] < analiz.MIN_DILIM_ORNEGI:
                continue
            satirlar.append([d, f"{t['ornek']:,}"] + [f"{t['ornek'] / t[s]:.1f}" if t[s] else "-" for s in IYMS_SIRASI])
        bolumler.append(("gecmis-iyms", "Geçmiş veri: ev sahibinin gücüne göre İY/MS adil oranları",
                         "Adil oran = 1 / gerçekleşme sıklığı. iddaa bundan yüksek oran veriyorsa seçim değerlidir.",
                         _tablo(["Ev kazanma olasılığı", "Örnek"] + IYMS_SIRASI, satirlar)))

    # iddaa verisi
    iyms_tablo = iyms_istatistik(kapanis_iyms, sonuclar)
    iyms_satirlari = [[s, t["n"], f"%{100 * t['tuttu'] / t['n']:.1f}", f"%{100 * t['vaat'] / t['n']:.1f}",
                       _getiri(t["donus"] / t["n"])] for s, t in iyms_tablo.items() if t["n"]]
    bolumler.append(("iddaa", "iddaa verisi (toplanan)",
                     "Sistemin kendi topladığı kapanış oranları ve sonuçlar. Sonuçlar geldikçe büyür.",
                     "<h3>MS oranları</h3>"
                     + _oran_tablosu("t-iddaa-ms", analiz.iddaa_ms_tablosu(kapanis_tum, sonuclar), maks=False)
                     + "<h3>İY/MS seçimleri</h3>"
                     + _tablo(["Seçim", "Örnek", "Tutma", "Oranın vaadi", "Getiri"], iyms_satirlari)))

    # Veri durumu
    tamam = sum(1 for s in sonuclar.values() if s.get("durum") == "tamam")
    bolumler.append(("durum", "Veri durumu", "",
                     _tablo(["Toplam maç", "İY/MS'li maç", "Sonuçlu maç", "Kapanış oranı olan", "Güncelleme"],
                            [[len(kayitlar), sum(1 for k in kayitlar.values() if k.get("iyms_var") == "1"), tamam,
                              len(kapanis_tum), simdi.astimezone(config.TR).strftime("%d.%m.%Y %H:%M")]])))

    nav = "".join(f'<a href="#{i}">{_e(b.split(":")[0])}</a>' for i, b, _, _ in bolumler)
    govde = "".join(f'<section id="{i}"><h2>{_e(b)}</h2>' + (f'<p class="not">{_e(n)}</p>' if n else "") + c + "</section>"
                    for i, b, n, c in bolumler)
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>iddaa analiz</title><style>{CSS}</style></head><body>
<header><h1>iddaa analiz</h1><div class="alt">Son güncelleme {simdi.astimezone(config.TR).strftime('%d.%m.%Y %H:%M')} · kağıt üstü, para yatırılmaz</div></header>
<nav><div>{nav}</div></nav><main>{govde}</main><script>{JS}</script></body></html>"""


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    hedef = Path("docs") / "index.html"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(olustur(), encoding="utf-8")
    log.info("panel yazıldı: %s", hedef)


if __name__ == "__main__":
    main()
