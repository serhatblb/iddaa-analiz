"""Statik panel: docs/index.html (+ docs/veri/iddaa_oran.json), GitHub Pages ile yayınlanır.

Sade tutuldu, üç sekme:
- Bugün: dört kupon (sabitlenmişse kendisi, değilse şu anki oranlarla önizleme) ve kasa.
- Geçmiş: kupon kupon sonuçlar ve kasa tablosu.
- Oran sorgula: bir oran yaz, iddaa'nın 2019'dan beri kendi oranlarıyla o oranın ne sıklıkla tuttuğunu gör;
  altında oran aralıklarına göre özet.
Diğer analizler (model, geriye dönük test, sanal tekliler) data/analiz altında; panelde gösterilmez.
"""
import html
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import analiz, config, depo, kalibrasyon, kupon
from .bulten import iso_oku

log = logging.getLogger("panel")
HEDEF = Path("docs")
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

CSS = """
:root{--bg:#f4f5f7;--kart:#fff;--yazi:#161a23;--soluk:#667085;--cizgi:#e4e7ec;--iyi:#16794a;--kotu:#b42318;
--vurgu:#2d5be3;--vurgu-bg:#eef3ff;--iyi-bg:#e7f6ee;--kotu-bg:#fdecea;--uyari-bg:#fff4dc;--uyari:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--kart:#171b23;--yazi:#e8ebf1;--soluk:#98a2b3;
--cizgi:#262c38;--iyi:#47c483;--kotu:#f07466;--vurgu:#86a6ff;--vurgu-bg:#1b2438;--iyi-bg:#15291e;
--kotu-bg:#351b1a;--uyari-bg:#33290f;--uyari:#f0c36a}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--yazi);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--cizgi)}
.ust{max-width:1000px;margin:auto;padding:14px 16px 0;display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
h1{margin:0;font-size:20px}.alt{color:var(--soluk);font-size:13px}
.sekmeler{max-width:1000px;margin:auto;padding:8px 16px 0;display:flex;gap:4px;overflow-x:auto}
.sekmeler button{font:inherit;font-weight:600;font-size:15px;color:var(--soluk);background:none;border:0;
border-bottom:2px solid transparent;padding:8px 14px;cursor:pointer;white-space:nowrap}
.sekmeler button.aktif{color:var(--vurgu);border-bottom-color:var(--vurgu)}
main{max-width:1000px;margin:auto;padding:16px 16px 56px}.sekme{display:none}.sekme.aktif{display:block}
.ozet{display:flex;flex-wrap:wrap;gap:6px 24px;font-size:14px;color:var(--soluk);margin:0 0 14px}
.ozet b{color:var(--yazi)}
.kartlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:16px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:14px;padding:16px;margin-bottom:16px}
.kart h2{font-size:17px;margin:0 0 2px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.aciklama{color:var(--soluk);font-size:13px;margin:0 0 10px}
.rozet{font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;background:var(--cizgi);white-space:nowrap}
.rozet.kazandi{background:var(--iyi-bg);color:var(--iyi)}.rozet.kaybetti{background:var(--kotu-bg);color:var(--kotu)}
.rozet.onizleme{background:var(--uyari-bg);color:var(--uyari)}.rozet.sabit{background:var(--vurgu-bg);color:var(--vurgu)}
.secim{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--cizgi)}
.mac b{display:block;font-size:15px}.mac span{color:var(--soluk);font-size:13px}
.sag{text-align:right;flex-shrink:0;display:flex;align-items:center;gap:8px}
.pill{font-size:13px;font-weight:700;background:var(--vurgu-bg);color:var(--vurgu);border-radius:6px;padding:2px 8px}
.oran{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums;min-width:52px}
.isaret{font-size:16px;width:20px;text-align:center}
.alt-satir{border-top:1px solid var(--cizgi);padding-top:10px;font-size:14px;color:var(--soluk)}
.alt-satir b{color:var(--yazi)}.bos{color:var(--soluk);margin:10px 0 0;font-size:14px}
.tablo{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--cizgi);text-align:right;white-space:nowrap}
th{color:var(--soluk);font-weight:600;font-size:12px}.sol{text-align:left}td.sarma{white-space:normal}
td.iyi{color:var(--iyi);font-weight:600}td.kotu{color:var(--kotu)}
.sorgu{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
.sorgu label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--soluk)}
input,select{font:inherit;color:var(--yazi);background:var(--bg);border:1px solid var(--cizgi);border-radius:8px;padding:8px 10px}
.sorgu input{font-size:22px;width:130px;font-weight:700}
.cevap{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:12px;margin-top:14px}
.cevap div{background:var(--bg);border-radius:10px;padding:12px 14px}.cevap b{font-size:24px;display:block}
.cevap span{font-size:13px;color:var(--soluk)}.sonuc-iyi{color:var(--iyi);font-weight:700}.sonuc-kotu{color:var(--kotu);font-weight:700}
@media (max-width:520px){.oran{font-size:17px}.kart{padding:14px}}
"""

JS = r"""
var sekmeler=document.querySelectorAll('.sekmeler button');
function sekmeAc(ad){
  if(!document.getElementById('sekme-'+ad)) ad='bugun';
  sekmeler.forEach(function(b){b.classList.toggle('aktif',b.dataset.sekme===ad)});
  document.querySelectorAll('.sekme').forEach(function(s){s.classList.toggle('aktif',s.id==='sekme-'+ad)});
  window.scrollTo(0,0);
}
sekmeler.forEach(function(b){b.addEventListener('click',function(){
  if(history.replaceState) history.replaceState(null,'','#'+b.dataset.sekme); sekmeAc(b.dataset.sekme);
})});
window.addEventListener('hashchange',function(){sekmeAc(location.hash.slice(1))});
if(location.hash) sekmeAc(location.hash.slice(1));

(function(){
  var kutu=document.getElementById('sorgu'); if(!kutu) return;
  var giris=kutu.querySelector('input'), mSec=kutu.querySelector('.f-market'), sSec=kutu.querySelector('.f-sec'),
      cevap=kutu.querySelector('.cevap'), veri=null;
  function yuzde(x){return '%'+(100*x).toFixed(1)}
  function kutucuk(baslik,n,t,donus){
    if(!n) return '<div><span>'+baslik+'</span><b>veri yok</b></div>';
    var g=donus/n;
    return '<div><span>'+baslik+' · '+n.toLocaleString('tr-TR')+' kez oynanabilirdi</span><b>'+yuzde(t/n)+' tuttu</b>'
      +'<span>1 TL → <strong class="'+(g>1?'sonuc-iyi':'sonuc-kotu')+'">'+g.toFixed(2)+' TL</strong> döndü</span></div>';
  }
  function doldur(){
    var h='<option value="hepsi">Hepsi</option>';
    Object.keys(veri[mSec.value]||{}).forEach(function(k){h+='<option value="'+k+'">'+k+'</option>'});
    sSec.innerHTML=h;
  }
  function bul(){
    var o=parseFloat(giris.value.replace(',','.')), m=mSec.value, s=sSec.value;
    if(!(o>1)||!veri||!veri[m]){cevap.innerHTML='';return}
    var ks=s==='hepsi'?Object.keys(veri[m]):[s], n=0,t=0,d=0,n2=0,t2=0,d2=0, a=o*0.97, u=o*1.03;
    ks.forEach(function(k){(veri[m][k]||[]).forEach(function(r){
      if(Math.abs(r[0]-o)<0.005){n+=r[1];t+=r[2];d+=r[2]*r[0]}
      if(r[0]>=a&&r[0]<=u){n2+=r[1];t2+=r[2];d2+=r[2]*r[0]}
    })});
    cevap.innerHTML=kutucuk('Tam '+o.toFixed(2),n,t,d)+kutucuk(a.toFixed(2)+'–'+u.toFixed(2)+' arası',n2,t2,d2);
  }
  fetch('veri/iddaa_oran.json').then(function(r){return r.json()}).then(function(v){
    veri=v; doldur(); bul();
  }).catch(function(){cevap.innerHTML='<div><span>Veri yüklenemedi.</span></div>'});
  mSec.addEventListener('input',function(){doldur();bul()}); sSec.addEventListener('input',bul);
  giris.addEventListener('input',bul);
})();
"""

ACIKLAMALAR = {
    "iyms": "Günün en yüksek oranlı 3 İY/MS'si; aynı oranlılar arasından geçmişte en sık tutanlar. Piyango.",
    "ms": "1-0-2'de en az kaybettiren seçim(ler).",
    "iyms_deger": "İY/MS'de en az kaybettiren seçim(ler).",
    "gol": "Toplam gol (0-1 / 2-3 / 4-5 / 6+) aralığında en az kaybettiren seçim(ler).",
}
DURUM = {"bekliyor": ("Bekliyor", "sabit"), "kazandi": ("KAZANDI", "kazandi"), "kaybetti": ("Kaybetti", "kaybetti"),
         "belirsiz": ("Sonuç bulunamadı", "")}
ISARET = {"1": "✅", "0": "❌", "iptal": "➖", "?": "❔"}


def _e(x) -> str:
    return html.escape(str(x))


def _saat(iso_metin: str, gun: bool = False) -> str:
    z = iso_oku(iso_metin).astimezone(config.TR)
    return f"{GUNLER[z.weekday()]} {z.strftime('%d.%m %H:%M')}" if gun else z.strftime("%H:%M")


def _tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")


def _toplam(x: float) -> str:
    """Kupon oranı: 1000 ve üstü binlik noktayla tam sayı (32.208), altı iki basamak (6.16)."""
    return f"{x:,.0f}".replace(",", ".") if x >= 1000 else f"{x:.2f}"


def _secim_etiketi(s: dict) -> str:
    market = s.get("market") or "İY/MS"
    if market == "Toplam gol":
        return s["secim"]
    if market.endswith("A/Ü"):
        return f"{market.split()[0]} {s['secim']}"
    return f"{market} {s['secim']}"


def _tablo(basliklar: list[str], satirlar: list[list], sol: int = 1) -> str:
    if not satirlar:
        return '<p class="bos">Henüz yok.</p>'
    bas = "".join(f'<th class="{"sol" if i < sol else ""}">{_e(b)}</th>' for i, b in enumerate(basliklar))
    govde = "".join("<tr>" + "".join(h if isinstance(h, str) and h.startswith("<td") else
                                     f'<td class="{"sol" if i < sol else ""}">{_e(h)}</td>' for i, h in enumerate(s))
                    + "</tr>" for s in satirlar)
    return f'<div class="tablo"><table><thead><tr>{bas}</tr></thead><tbody>{govde}</tbody></table></div>'


def _secimler(secimler: list[dict], sonuc_goster: bool) -> str:
    satirlar = []
    for s in secimler:
        isaret = ISARET.get(s.get("tuttu"), "") if sonuc_goster else ""
        gercek = f" · sonuç {s['gercek']}" if sonuc_goster and s.get("tuttu") in ("0", "1") else ""
        satirlar.append(
            f'<div class="secim"><div class="mac"><b>{_e(s["ev"])} – {_e(s["dep"])}</b>'
            f'<span>{_e(_saat(s["baslama_utc"]))} · {_e(s["lig"])}{_e(gercek)}</span></div>'
            f'<div class="sag"><span class="pill">{_e(_secim_etiketi(s))}</span>'
            f'<span class="oran">{float(s["oran"]):.2f}</span><span class="isaret">{isaret}</span></div></div>')
    return "".join(satirlar)


def _kupon_karti(tur: str, ad: str, sabit: list[dict] | None, adaylar: list[dict]) -> str:
    if sabit and sabit[0]["durum"] != "aday_yok":
        etiket, sinif = DURUM.get(sabit[0]["durum"], (sabit[0]["durum"], ""))
        secilen, tutar = sabit, float(sabit[0]["tutar"])
        kazanc = (f' · kazanç <b>{_tl(float(sabit[0]["kazanc"]))}</b>' if sabit[0]["durum"] == "kazandi" else "")
    else:
        secilen = kupon.kupon_secimi(tur, adaylar)
        tutar, kazanc = config.KUPON_TUTARI, ""
        if sabit:
            etiket, sinif = "Bugün kupon yok", ""
            secilen = []
        else:
            etiket, sinif = "Önizleme", "onizleme"
    if secilen:
        toplam = 1.0
        for s in secilen:
            toplam *= float(s["oran"])
        govde = (_secimler(secilen, bool(sabit))
                 + f'<div class="alt-satir">{len(secilen)} maç · oran <b>{_toplam(toplam)}</b> · {_tl(tutar)} → '
                   f'<b>{_tl(tutar * toplam)}</b>{kazanc}</div>')
    else:
        govde = '<p class="bos">Bugün uygun maç yok.</p>'
    return (f'<div class="kart"><h2>{_e(ad)} <span class="rozet {sinif}">{_e(etiket)}</span></h2>'
            f'<p class="aciklama">{_e(ACIKLAMALAR.get(tur, ""))}</p>{govde}</div>')


def _kasa(kuponlar: dict) -> tuple[list[list], float, float]:
    satirlar, yatirilan, donen = [], 0.0, 0.0
    for tur, ad in kupon.TURLER.items():
        k = kupon.kasa(kuponlar, tur)
        yatirilan += k["yatirilan"]
        donen += k["donen"]
        satirlar.append([ad, k["kupon"], k["kazanan"], _tl(k["yatirilan"]), _tl(k["donen"]),
                         f'<td class="{"iyi" if k["net"] > 0 else "kotu" if k["net"] < 0 else ""}">{_tl(k["net"])}</td>'])
    return satirlar, yatirilan, donen


def _bant_tablosu(senaryo: dict) -> str:
    satirlar = [[r["market"], r["bant"], f"{r['bahis']:,}".replace(",", "."), f"%{100 * r['tutma']:.1f}",
                 f'<td class="{"iyi" if r["getiri_kral"] > 1 else "kotu"}">{r["getiri_kral"]:.2f} TL</td>']
                for r in senaryo.get("satirlar", [])
                if r["bant"] and r["secenek"] == "hepsi" and r["market"] in ("MS", "İY/MS", "Toplam gol")]
    return _tablo(["Bahis", "Oran aralığı", "Kaç kez", "Tuttu", "1 TL →"], satirlar, sol=2)


def olustur(simdi: datetime | None = None) -> tuple[str, dict[str, dict]]:
    """(index.html içeriği, {dosya adı: json içeriği})"""
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    bugun = simdi.astimezone(config.TR).date().isoformat()
    kuponlar = kupon.kuponlara_ayir(kupon.kuponlari_oku())
    adaylar = kupon.oneriler(simdi)
    senaryo = depo.json_oku(analiz.analiz_yolu("iddaa_senaryolar.json")) or {}
    iddaa_oran = depo.json_oku(analiz.analiz_yolu("iddaa_oran_tablosu.json")) or {}
    kasa_satirlari, yatirilan, donen = _kasa(kuponlar)

    # --- Bugün ---
    kartlar = "".join(_kupon_karti(tur, ad, kuponlar.get((bugun, tur)), adaylar[tur])
                      for tur, ad in kupon.TURLER.items())
    sekme_bugun = (
        f'<p class="ozet"><span>Kağıt üstü · her kupon {_tl(config.KUPON_TUTARI)} · sadece bugünün maçları'
        + ("" if any((bugun, t) in kuponlar for t in kupon.TURLER) else " · önizleme, 09:40'tan sonra sabitlenir")
        + '</span>'
        f'<span>Kasa: <b>{_tl(donen - yatirilan)}</b> · bütçeden kalan <b>{_tl(config.KUPON_BUTCE - yatirilan + donen)}</b>'
        f'</span></p><div class="kartlar">{kartlar}</div>')

    # --- Geçmiş ---
    satirlar = []
    for (tarih, tur) in sorted(kuponlar, reverse=True):
        grup = kuponlar[(tarih, tur)]
        if grup[0]["durum"] == "aday_yok":
            continue
        secimler = " · ".join(f"{ISARET.get(s['tuttu'], '⏳')} {s['ev']} {_secim_etiketi(s)} ({float(s['oran']):.2f})"
                              for s in grup)
        etiket, sinif = DURUM.get(grup[0]["durum"], (grup[0]["durum"], ""))
        durum = (f'<td class="iyi">{_e(etiket)} {_tl(float(grup[0]["kazanc"]))}</td>' if grup[0]["durum"] == "kazandi"
                 else f'<td class="{"kotu" if sinif == "kaybetti" else ""}">{_e(etiket)}</td>')
        satirlar.append([tarih[8:10] + "." + tarih[5:7], kupon.TURLER.get(tur, tur),
                         f'<td class="sol sarma">{_e(secimler)}</td>', _toplam(float(grup[0]['toplam_oran'])), durum])
    sekme_gecmis = (
        '<div class="kart"><h2>Kasa</h2>'
        + _tablo(["Kupon", "Oynanan", "Tutan", "Yatırılan", "Dönen", "Net"], kasa_satirlari)
        + "</div>"
        '<div class="kart"><h2>Kuponlar</h2>'
        + _tablo(["Tarih", "Kupon", "Seçimler", "Oran", "Durum"], satirlar[:200], sol=3) + "</div>")

    # --- Oran sorgula ---
    marketler = "".join(f'<option value="{_e(m)}">{_e(m)}</option>' for m in kalibrasyon.MARKETLER if m in iddaa_oran)
    mac_sayisi = f"{senaryo.get('mac', 0):,}".replace(",", ".")
    sekme_oran = (
        '<div class="kart" id="sorgu"><h2>Bir oran yaz: geçmişte ne kadar tuttu?</h2>'
        f"<p class=\"aciklama\">iddaa'nın kendi oranları, {mac_sayisi} maç "
        f'({_e(senaryo.get("ilk", "")[:4])}–{_e(senaryo.get("son", "")[:4])}). '
        "1 TL → 1'in altındaysa o oran uzun vadede kaybettirir.</p>"
        '<div class="sorgu"><label>Oran<input type="text" inputmode="decimal" value="1.55"></label>'
        f'<label>Bahis<select class="f-market">{marketler}</select></label>'
        '<label>Seçim<select class="f-sec"></select></label></div><div class="cevap"></div></div>'
        '<div class="kart"><h2>Oran aralıklarına göre</h2><p class="aciklama">Her seçime 1 TL oynansaydı kaç TL '
        "dönerdi. Hiçbir aralık 1'i geçmiyor: iddaa her bahiste payını alıyor.</p>"
        + _bant_tablosu(senaryo) + "</div>")

    sekmeler = [("bugun", "Bugün", sekme_bugun), ("gecmis", "Geçmiş", sekme_gecmis),
                ("oran", "Oran sorgula", sekme_oran)]
    dugmeler = "".join(f'<button data-sekme="{i}" class="{"aktif" if n == 0 else ""}">{_e(b)}</button>'
                       for n, (i, b, _) in enumerate(sekmeler))
    govde = "".join(f'<div class="sekme {"aktif" if n == 0 else ""}" id="sekme-{i}">{c}</div>'
                    for n, (i, _, c) in enumerate(sekmeler))
    zaman = simdi.astimezone(config.TR)
    sayfa = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<meta name="color-scheme" content="light dark"><title>iddaa analiz</title><style>{CSS}</style></head><body>
<header><div class="ust"><h1>iddaa analiz</h1><span class="alt">Güncellendi {GUNLER[zaman.weekday()]} {zaman.strftime('%d.%m %H:%M')}</span></div>
<nav class="sekmeler">{dugmeler}</nav></header>
<main>{govde}</main><script>{JS}</script></body></html>"""
    return sayfa, ({"iddaa_oran.json": iddaa_oran} if iddaa_oran else {})


def yaz(hedef: Path = HEDEF, simdi: datetime | None = None) -> None:
    sayfa, dosyalar = olustur(simdi)
    veri = hedef / "veri"
    veri.mkdir(parents=True, exist_ok=True)
    (hedef / "index.html").write_text(sayfa, encoding="utf-8")
    (hedef / ".nojekyll").touch()
    for eski in veri.glob("*.json"):
        if eski.name not in dosyalar:
            eski.unlink()
    for ad, icerik in dosyalar.items():
        (veri / ad).write_text(json.dumps(icerik, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    yaz()
    log.info("panel yazıldı: %s", HEDEF / "index.html")


if __name__ == "__main__":
    main()
