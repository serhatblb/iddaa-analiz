"""Statik panel: docs/index.html (+ docs/veri/*.json), GitHub Pages ile yayınlanır.

Dört sekme: Kuponlar, Oran sorgula, Kupon geçmişi, Analiz. Büyük tablolar ayrı JSON dosyalarında
tutulur ve gerektiğinde yüklenir; böylece her saat değişen index.html küçük kalır.
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
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
VARSAYILAN_IDDAA_PAYI = 1.17

CSS = """
:root{--bg:#f4f5f7;--kart:#fff;--yazi:#161a23;--soluk:#667085;--cizgi:#e4e7ec;--iyi:#16794a;--kotu:#b42318;
--vurgu:#2d5be3;--vurgu-bg:#eef3ff;--iyi-bg:#e7f6ee;--kotu-bg:#fdecea;--uyari-bg:#fff4dc;--uyari:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--kart:#171b23;--yazi:#e8ebf1;--soluk:#98a2b3;
--cizgi:#262c38;--iyi:#47c483;--kotu:#f07466;--vurgu:#86a6ff;--vurgu-bg:#1b2438;--iyi-bg:#15291e;
--kotu-bg:#351b1a;--uyari-bg:#33290f;--uyari:#f0c36a}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--yazi);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--cizgi)}
.ust{max-width:1100px;margin:auto;padding:14px 16px 0;display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
h1{margin:0;font-size:20px;letter-spacing:-.01em}.alt{color:var(--soluk);font-size:13px}
.sekmeler{max-width:1100px;margin:auto;padding:8px 16px 0;display:flex;gap:4px;overflow-x:auto}
.sekmeler button{font:inherit;font-weight:600;font-size:14px;color:var(--soluk);background:none;border:0;
border-bottom:2px solid transparent;padding:8px 12px;cursor:pointer;white-space:nowrap}
.sekmeler button.aktif{color:var(--vurgu);border-bottom-color:var(--vurgu)}
main{max-width:1100px;margin:auto;padding:16px 16px 56px}.sekme{display:none}.sekme.aktif{display:block}
.bilgi{background:var(--vurgu-bg);border-radius:10px;padding:10px 14px;font-size:14px;margin-bottom:16px}
.kartlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:16px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:14px;padding:16px;margin-bottom:16px}
.kart h2{font-size:17px;margin:0;display:flex;justify-content:space-between;align-items:center;gap:8px}
.kart h3{font-size:15px;margin:18px 0 8px}.aciklama{color:var(--soluk);font-size:13px;margin:4px 0 12px}
.rozet{font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;background:var(--cizgi);white-space:nowrap}
.rozet.kazandi{background:var(--iyi-bg);color:var(--iyi)}.rozet.kaybetti{background:var(--kotu-bg);color:var(--kotu)}
.rozet.onizleme{background:var(--uyari-bg);color:var(--uyari)}.rozet.sabit{background:var(--vurgu-bg);color:var(--vurgu)}
.secimler{border-top:1px solid var(--cizgi)}
.secim{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--cizgi)}
.mac b{display:block;font-size:15px}.mac span{color:var(--soluk);font-size:13px}
.tahmin{text-align:right;flex-shrink:0}.tahmin .ust-satir{display:flex;align-items:center;gap:8px;justify-content:flex-end}
.pill{font-size:13px;font-weight:700;background:var(--vurgu-bg);color:var(--vurgu);border-radius:6px;padding:2px 8px}
.oran{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.tahmin .kucuk{display:block;font-size:12px;color:var(--soluk)}
.sonuc-iyi{color:var(--iyi);font-weight:700}.sonuc-kotu{color:var(--kotu);font-weight:700}
.alt-bilgi{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:12px;font-size:14px;color:var(--soluk)}
.alt-bilgi b{color:var(--yazi)}.bos{color:var(--soluk);padding:14px 0;margin:0;font-size:14px}
td.mac-hucre{white-space:normal;min-width:200px}td.mac-hucre b{display:block;font-weight:600}
td.mac-hucre span{display:block;font-size:12px;color:var(--soluk)}
.kasa{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}
.kasa div{background:var(--bg);border-radius:8px;padding:8px 10px}.kasa b{display:block;font-size:16px}
.kasa span{font-size:12px;color:var(--soluk)}
details{margin-top:4px}summary{cursor:pointer;font-weight:600;padding:8px 0;color:var(--vurgu)}
.tablo{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:7px 10px;border-bottom:1px solid var(--cizgi);text-align:right;white-space:nowrap}
th{color:var(--soluk);font-weight:600;font-size:12px}.sol{text-align:left}
td.iyi{color:var(--iyi);font-weight:600}td.kotu{color:var(--kotu)}td.soluk{color:var(--soluk)}td.kalin{font-weight:700}
.sorgu{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
.sorgu label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--soluk)}
input,select{font:inherit;color:var(--yazi);background:var(--bg);border:1px solid var(--cizgi);border-radius:8px;padding:8px 10px}
.sorgu input{font-size:22px;width:140px;font-weight:700}
.cevap{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px;margin-top:14px}
.cevap div{background:var(--bg);border-radius:10px;padding:12px 14px}.cevap b{font-size:24px;display:block}
.cevap span{font-size:13px;color:var(--soluk)}
.filtre{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 10px}.filtre label{font-size:12px;color:var(--soluk);display:flex;flex-direction:column;gap:3px}
.kaydir{max-height:520px;overflow:auto}.kaydir thead th{position:sticky;top:0;background:var(--kart)}
table.siralanir th{cursor:pointer;user-select:none}table.siralanir th[data-yon=azalan]::after{content:" ▼"}
table.siralanir th[data-yon=artan]::after{content:" ▲"}
@media (max-width:520px){.kasa{grid-template-columns:repeat(2,1fr)}.oran{font-size:18px}.kart{padding:14px}}
"""

JS = """
var sekmeler=document.querySelectorAll('.sekmeler button');
function sekmeAc(ad){
  if(!document.getElementById('sekme-'+ad)) ad='kuponlar';
  sekmeler.forEach(function(b){b.classList.toggle('aktif',b.dataset.sekme===ad)});
  document.querySelectorAll('.sekme').forEach(function(s){s.classList.toggle('aktif',s.id==='sekme-'+ad)});
  window.scrollTo(0,0);
}
sekmeler.forEach(function(b){b.addEventListener('click',function(){
  if(history.replaceState) history.replaceState(null,'','#'+b.dataset.sekme); sekmeAc(b.dataset.sekme);
})});
window.addEventListener('hashchange',function(){sekmeAc(location.hash.slice(1))});
if(location.hash) sekmeAc(location.hash.slice(1));

function yuzde(x){return '%'+(100*x).toFixed(1)}
function getiriTd(x){return '<td data-d="'+x+'" class="'+(x>1?'iyi':'kotu')+'">'+x.toFixed(3)+'</td>'}
var veriler={};
function yukle(ad){ if(!veriler[ad]) veriler[ad]=fetch('veri/'+ad).then(function(r){return r.json()}); return veriler[ad]; }

document.querySelectorAll('.oran-tablosu').forEach(function(kutu){
  var t=kutu.querySelector('table'), say=kutu.querySelector('.sayac'), f=kutu.querySelector('.filtre'), maks=kutu.dataset.maks==='1';
  yukle(kutu.dataset.kaynak).then(function(v){
    var a=v.alanlar, h=[];
    v.satirlar.forEach(function(s){
      var r={}; a.forEach(function(k,i){r[k]=s[i]});
      h.push('<tr data-secim="'+r.secim+'" data-oran="'+r.oran+'" data-ornek="'+r.ornek+'">'
        +'<td class="sol kalin" data-d="'+r.oran+'">'+r.oran+'</td><td data-d="'+r.ornek+'">'+r.ornek.toLocaleString('tr-TR')+'</td>'
        +'<td data-d="'+r.tutma+'">'+yuzde(r.tutma)+'</td><td data-d="'+r.vaat+'">'+yuzde(r.vaat)+'</td>'
        +getiriTd(r.getiri)+'<td data-d="'+r.hata+'" class="soluk">±'+r.hata.toFixed(2)+'</td>'
        +(maks?getiriTd(r.getiri_maks):'')+'</tr>');
    });
    t.tBodies[0].innerHTML=h.join(''); uygula();
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

document.querySelectorAll('table.siralanir th').forEach(function(th){
  th.addEventListener('click',function(){
    var t=th.closest('table'), i=[].indexOf.call(th.parentNode.children,th), azalan=th.dataset.yon!=='azalan';
    t.querySelectorAll('th').forEach(function(x){delete x.dataset.yon});
    th.dataset.yon=azalan?'azalan':'artan';
    var s=[].slice.call(t.tBodies[0].rows);
    s.sort(function(a,b){var x=+a.cells[i].dataset.d, y=+b.cells[i].dataset.d; return azalan?y-x:x-y});
    s.forEach(function(r){t.tBodies[0].appendChild(r)});
  });
});

(function(){
  var kutu=document.getElementById('sorgu'); if(!kutu) return;
  var giris=kutu.querySelector('input'), sec=kutu.querySelector('select'), cevap=kutu.querySelector('.cevap'),
      pay=+kutu.dataset.pay;
  function bul(){
    var o=parseFloat(giris.value.replace(',','.')), s=sec.value;
    if(!(o>1)){cevap.innerHTML='';return}
    Promise.all([yukle('gecmis_ms.json'),yukle('ms_olasilik.json')]).then(function(r){
      var tablo=r[0], ol=r[1], secimler=s==='hepsi'?['1','0','2']:[s], etiket=o.toFixed(2);
      var n=0,t=0;
      tablo.satirlar.forEach(function(x){ if(x[0]!=='hepsi' && secimler.indexOf(x[0])>=0 && x[1]===etiket){n+=x[2]; t+=x[2]*x[3];} });
      var q=Math.min(99,Math.floor(100/(o*pay))), n2=0,t2=0;
      secimler.forEach(function(k){ for(var i=Math.max(0,q-2);i<=Math.min(99,q+2);i++){n2+=ol[k][i][0]; t2+=ol[k][i][1];} });
      var h='';
      if(n){var tm=t/n, g=tm*o, hp=1.96*o*Math.sqrt(tm*(1-tm)/n);
        h+='<div><span>Geçmişte tam '+etiket+' oranlı '+n.toLocaleString('tr-TR')+' seçim (yabancı şirket oranı)</span><b>'+yuzde(tm)+' tuttu</b>'
          +'<span>1 TL → <strong class="'+(g>1?'sonuc-iyi':'sonuc-kotu')+'">'+g.toFixed(2)+' TL</strong> (hata payı ±'+hp.toFixed(2)+')</span></div>';}
      else h+='<div><span>Geçmişte tam bu oranla seçim yok.</span></div>';
      if(n2){var tm2=t2/n2, g2=tm2*o;
        h+='<div><span>iddaa\\'da '+etiket+' görürsen (iddaa\\'nın kâr payı düşülerek, '+n2.toLocaleString('tr-TR')+' benzer seçim)</span><b>'+yuzde(tm2)+' tutar</b>'
          +'<span>1 TL → <strong class="'+(g2>1?'sonuc-iyi':'sonuc-kotu')+'">'+g2.toFixed(2)+' TL</strong></span></div>';}
      cevap.innerHTML=h;
    });
  }
  giris.addEventListener('input',bul); sec.addEventListener('input',bul); bul();
})();
"""


def _e(x) -> str:
    return html.escape(str(x))


def _saat(iso_metin: str) -> str:
    z = iso_oku(iso_metin).astimezone(config.TR)
    return f"{GUNLER[z.weekday()]} {z.strftime('%d.%m %H:%M')}"


def _tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")


def _tablo(basliklar: list[str], satirlar: list[list], sol: int = 1) -> str:
    if not satirlar:
        return '<p class="bos">Henüz veri yok.</p>'
    bas = "".join(f'<th class="{"sol" if i < sol else ""}">{_e(b)}</th>' for i, b in enumerate(basliklar))
    govde = "".join("<tr>" + "".join(h if isinstance(h, str) and h.startswith("<td") else
                                     f'<td class="{"sol" if i < sol else ""}">{_e(h)}</td>' for i, h in enumerate(s))
                    + "</tr>" for s in satirlar)
    return f'<div class="tablo"><table><thead><tr>{bas}</tr></thead><tbody>{govde}</tbody></table></div>'


def _getiri_td(x: float) -> str:
    return f'<td class="{"iyi" if x > 1 else "kotu"}">{x:.2f}</td>'


def _secim_etiketi(s: dict) -> str:
    if s["market"] == "Toplam gol":
        return s["secim"]
    return f"{'MS' if s['market'] == 'MS' else 'İY/MS'} {s['secim']}"


ACIKLAMALAR = {
    "iyms": f"Oranı {config.KUPON_MIN_ORAN:g}–{config.KUPON_MAX_ORAN:g} arası İY/MS seçeneklerinden en yüksek oranlı "
            f"{config.KUPON_MAC_SAYISI} maç. Piyango mantığı.",
    "ms": f"Oranı {config.MS_KUPON_MIN_ORAN:.2f}–{config.MS_KUPON_MAX_ORAN:.2f} arası 1-0-2 seçimlerinden, geçmişte "
          f"1 TL'ye en çok para döndüren {config.KUPON_MAC_SAYISI} seçim.",
    "iyms_deger": "Her maçta, ev sahibinin gücüne göre geçmişte 1 TL'ye en çok para döndüren İY/MS seçimi; en iyi "
                  f"{config.KUPON_MAC_SAYISI} maç.",
    "gol": "Toplam gol (0-1 / 2-3 / 4-5 / 6+). 2.5 Alt/Üst oranı benzer geçmiş maçların gol dağılımına göre 1 TL'ye "
           f"en çok para döndüren seçim; en iyi {config.KUPON_MAC_SAYISI} maç.",
}


def _istatistik_notu(s: dict) -> str:
    tutma, beklenen = s.get("tutma"), s.get("beklenen")
    if tutma in ("", None) or beklenen in ("", None):
        return ""
    return f"geçmişte %{100 * float(tutma):.0f} · 1 TL → {float(beklenen):.2f}"


def _secim_satirlari(secimler: list[dict], sonuc_goster: bool) -> str:
    satirlar = []
    for s in secimler:
        sonuc = ""
        if sonuc_goster:
            if s.get("tuttu") == "1":
                sonuc = f'<span class="kucuk sonuc-iyi">✅ tuttu ({_e(s["gercek"])})</span>'
            elif s.get("tuttu") == "0":
                sonuc = f'<span class="kucuk sonuc-kotu">❌ yattı (sonuç {_e(s["gercek"])})</span>'
            elif s.get("tuttu") == "iptal":
                sonuc = '<span class="kucuk">iptal (oran 1)</span>'
            elif s.get("tuttu") == "?":
                sonuc = '<span class="kucuk">sonuç bulunamadı</span>'
        not_ = _istatistik_notu(s)
        satirlar.append(
            f'<div class="secim"><div class="mac"><b>{_e(s["ev"])} – {_e(s["dep"])}</b>'
            f'<span>{_e(s["lig"])} · {_e(_saat(s["baslama_utc"]))}</span></div>'
            f'<div class="tahmin"><div class="ust-satir"><span class="pill">{_e(_secim_etiketi(s))}</span>'
            f'<span class="oran">{float(s["oran"]):.2f}</span></div>'
            + (f'<span class="kucuk">{_e(not_)}</span>' if not_ else "") + sonuc + "</div></div>")
    return f'<div class="secimler">{"".join(satirlar)}</div>'


DURUM = {"bekliyor": ("Sabitlendi · bekliyor", "sabit"), "kazandi": ("KAZANDI", "kazandi"),
         "kaybetti": ("Kaybetti", "kaybetti"), "belirsiz": ("Sonuç bulunamadı", "")}


def _kupon_karti(tur: str, ad: str, sabit: list[dict] | None, adaylar: list[dict], kasa: dict) -> str:
    aciklama = ACIKLAMALAR.get(tur, "")
    if sabit and sabit[0]["durum"] != "aday_yok":
        etiket, sinif = DURUM.get(sabit[0]["durum"], (sabit[0]["durum"], ""))
        ilk = sabit[0]
        toplam = float(ilk["toplam_oran"])
        govde = _secim_satirlari(sabit, True)
        alt = (f'<div class="alt-bilgi"><span>Toplam oran <b>{toplam:,.2f}</b></span>'
               f'<span>{_tl(float(ilk["tutar"]))} → <b>{_tl(float(ilk["tutar"]) * toplam)}</b></span>'
               + (f'<span>Kazanç <b>{_tl(float(ilk["kazanc"]))}</b></span>' if ilk["durum"] == "kazandi" else "")
               + "</div>")
    else:
        etiket, sinif = "Önizleme", "onizleme"
        secilen = adaylar[:config.KUPON_MAC_SAYISI]
        if sabit:
            aciklama += f" Bu sabah yeterli aday yoktu; aşağıdaki şu anki oranlarla seçilecek olan."
        else:
            aciklama += " Sabah 09:43'te sabitlenir; aşağıdaki şu anki oranlarla seçilecek olan."
        if len(secilen) < config.KUPON_MAC_SAYISI:
            govde = (f'<p class="bos">Şu an yeterli aday yok ({len(adaylar)} aday). '
                     "Bülten her saat kontrol ediliyor, oranlar açılınca burada görünür.</p>")
            alt = ""
        else:
            toplam = 1.0
            for a in secilen:
                toplam *= a["oran"]
            govde = _secim_satirlari(secilen, False)
            alt = (f'<div class="alt-bilgi"><span>Toplam oran <b>{toplam:,.2f}</b></span>'
                   f'<span>{_tl(config.KUPON_TUTARI)} → <b>{_tl(config.KUPON_TUTARI * toplam)}</b></span></div>')
    kasa_html = ('<div class="kasa">'
                 + "".join(f"<div><b>{_e(v)}</b><span>{_e(k)}</span></div>" for k, v in [
                     ("Oynanan kupon", kasa["kupon"]), ("Kazanan", kasa["kazanan"]),
                     ("Net", _tl(kasa["net"])), ("Bütçeden kalan", _tl(kasa["kalan"]))]) + "</div>")
    return (f'<div class="kart"><h2>{_e(ad)} <span class="rozet {sinif}">{_e(etiket)}</span></h2>'
            f'<p class="aciklama">{_e(aciklama)}</p>{govde}{alt}{kasa_html}</div>')


def _aday_tablosu(adaylar: list[dict]) -> str:
    satirlar = []
    for a in adaylar[:40]:
        satirlar.append([f'<td class="sol mac-hucre"><b>{_e(a["ev"])} – {_e(a["dep"])}</b><span>{_e(a["lig"])}</span></td>',
                         _saat(a["baslama_utc"]), _secim_etiketi(a), f'<td class="kalin">{a["oran"]:.2f}</td>',
                         f"%{100 * float(a['tutma']):.0f}" if a.get("tutma") not in ("", None) else "-",
                         _getiri_td(float(a["beklenen"])) if a.get("beklenen") not in ("", None) else "<td>-</td>"])
    return _tablo(["Maç", "Başlama", "Seçim", "Oran", "Geçmişte tuttu", "1 TL →"], satirlar, sol=1)


def _oran_tablosu(kaynak: str, maks: bool) -> str:
    secimler = {"hepsi": "Tümü", "1": "Ev sahibi (1)", "0": "Beraberlik (0)", "2": "Deplasman (2)"}
    secenekler = "".join(f'<option value="{k}">{_e(v)}</option>' for k, v in secimler.items())
    basliklar = ["Oran", "Kaç kez", "Tuttu", "Oranın vaadi", "1 TL →", "Hata payı"] + (["1 TL → (en iyi oran)"] if maks else [])
    return (f'<div class="oran-tablosu" data-kaynak="{kaynak}" data-maks="{int(maks)}">'
            f'<div class="filtre"><label>Seçim <select class="f-secim">{secenekler}</select></label>'
            '<label>Oran <input class="f-oran" type="search" inputmode="decimal" placeholder="ör. 1.55"></label>'
            '<label>En az örnek <select class="f-ornek"><option value="1">hepsi</option><option value="30">30</option>'
            f'<option value="100">100</option><option value="300" {"selected" if maks else ""}>300</option>'
            '<option value="1000">1000</option></select></label></div>'
            '<div class="tablo kaydir"><table class="siralanir"><thead><tr>'
            + "".join(f'<th class="{"sol" if i == 0 else ""}">{_e(b)}</th>' for i, b in enumerate(basliklar))
            + '</tr></thead><tbody></tbody></table></div><p class="aciklama sayac">Yükleniyor…</p></div>')


def _oran_json(satirlar: list[dict]) -> dict:
    return {"alanlar": MS_ALANLARI,
            "satirlar": [[r["secim"], r["oran"], r["ornek"], round(r["tutma"], 4), round(r["vaat"], 4),
                          round(r["getiri"], 4), round(r.get("hata") or 0, 4), round(r.get("getiri_maks") or 0, 4)]
                         for r in satirlar]}


def iddaa_payi(oranlar: dict) -> float:
    """Toplanan iddaa MS oranlarından ortalama kâr payı çarpanı (1/o toplamı)."""
    toplamlar = []
    for marketler in oranlar.values():
        ms = (marketler.get(analiz.MS) or {}).get("oranlar", {})
        if all(s in ms for s in analiz.MS_SECENEKLERI):
            toplamlar.append(sum(1 / ms[s] for s in analiz.MS_SECENEKLERI))
    return round(sum(toplamlar) / len(toplamlar), 3) if len(toplamlar) >= 10 else VARSAYILAN_IDDAA_PAYI


def olustur(simdi: datetime | None = None) -> tuple[str, dict[str, dict]]:
    """(index.html içeriği, {dosya adı: json içeriği})"""
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    bugun = simdi.astimezone(config.TR).date().isoformat()
    kayitlar = depo.maclari_oku()
    sonuclar = depo.sonuclari_oku()
    kuponlar = kupon.kuponlara_ayir(kupon.kuponlari_oku())
    adaylar = kupon.oneriler(simdi)
    son = analiz.son_oranlar(simdi, {analiz.MS})
    pay = iddaa_payi(son)
    kapanis_tum = analiz.kapanis_oranlari(kayitlar, {config.IYMS, analiz.MS})
    kapanis_iyms = {m: v[config.IYMS] for m, v in kapanis_tum.items() if config.IYMS in v}
    ozet_gecmis = depo.json_oku(analiz.analiz_yolu("gecmis_ozet.json")) or {}
    kosullu = analiz.kosullu_oku()
    json_dosyalari = {"gecmis_ms.json": _oran_json([r for r in analiz.ms_tablosu_oku() if r["ornek"] >= 30]),
                      "iddaa_ms.json": _oran_json(analiz.iddaa_ms_tablosu(kapanis_tum, sonuclar)),
                      "ms_olasilik.json": analiz.ms_olasilik_oku() or {s: [[0, 0]] * 100 for s in "102"}}

    # --- Kuponlar ---
    kartlar = "".join(_kupon_karti(tur, ad, kuponlar.get((bugun, tur)), adaylar[tur], kupon.kasa(kuponlar, tur))
                      for tur, ad in kupon.TURLER.items())
    sekme_kupon = (
        '<div class="bilgi">Dört ayrı kupon: <b>İY/MS</b> yüksek oranlı sürpriz, <b>1-0-2</b>, <b>İY/MS değer</b> ve '
        "<b>Gol</b>; son üçü geçmiş veriye göre 1 TL'ye en çok para döndüren seçimler. <b>1 TL →</b> değeri 1'in "
        "altındaysa o seçim uzun vadede kaybettirir. Kağıt üstü; para yatırılmaz.</div>"
        f'<div class="kartlar">{kartlar}</div>'
        f'<div class="kart"><h2>Şu anki adaylar</h2><p class="aciklama">Önümüzdeki 24 saat, her saat güncellenir. '
        "Geçmişte tuttu: iddaa'nın kâr payı düşülerek, benzer geçmiş maçlarda o seçimin tutma oranı.</p>"
        + "".join(f"<details{' open' if i == 0 else ''}><summary>{_e(ad.replace(' kuponu', ''))} adayları "
                  f"({len(adaylar[tur])})</summary>{_aday_tablosu(adaylar[tur])}</details>"
                  for i, (tur, ad) in enumerate(kupon.TURLER.items()))
        + "</div>")

    # --- Oran sorgula ---
    sekme_oran = (
        f'<div class="kart" id="sorgu" data-pay="{pay}"><h2>Bir oran yaz, geçmişte ne kadar tuttuğunu gör</h2>'
        f"<p class=\"aciklama\">{ozet_gecmis.get('mac', 0):,} maç, {ozet_gecmis.get('lig', 0)} lig, "
        f"{ozet_gecmis.get('ilk', '')[:4]}–{ozet_gecmis.get('son', '')[:4]}. iddaa'nın kâr payı şu an ortalama "
        f"%{100 * (pay - 1):.0f}; yabancı şirketlerde ~%5. Bu yüzden iddaa'daki aynı oran daha az tutar.</p>"
        '<div class="sorgu"><label>Oran<input type="text" inputmode="decimal" value="1.55"></label>'
        '<label>Seçim<select><option value="hepsi">Hepsi</option><option value="1">Ev sahibi (1)</option>'
        '<option value="0">Beraberlik (0)</option><option value="2">Deplasman (2)</option></select></label></div>'
        '<div class="cevap"></div></div>'
        '<div class="kart"><h2>Tüm oranlar</h2><p class="aciklama">Yabancı şirket oranlarıyla. Hata payı: sonuç şans eseri '
        "bu kadar oynayabilir; payın içindeki farklar tesadüf olabilir. Başlığa tıklayıp sırala.</p>"
        + _oran_tablosu("gecmis_ms.json", maks=True) + "</div>")

    # --- Kupon geçmişi ---
    satirlar = []
    for (tarih, tur) in sorted(kuponlar, reverse=True):
        grup = kuponlar[(tarih, tur)]
        if grup[0]["durum"] == "aday_yok":
            satirlar.append([tarih, kupon.TURLER.get(tur, tur), "aday yok", "", "", "", ""])
            continue
        for s in grup:
            sonuc = {"1": f'<td class="iyi">✅ {_e(s["gercek"])}</td>', "0": f'<td class="kotu">❌ {_e(s["gercek"])}</td>',
                     "iptal": '<td class="soluk">iptal</td>', "?": '<td class="soluk">sonuç yok</td>'}.get(s["tuttu"], "<td>bekliyor</td>")
            satirlar.append([tarih, kupon.TURLER.get(tur, tur), f"{s['ev']} – {s['dep']}", _secim_etiketi(s),
                             f"{float(s['oran']):.2f}", sonuc, DURUM.get(s["durum"], (s["durum"],))[0]])
    sekme_gecmis = ('<div class="kart"><h2>Kupon geçmişi</h2>'
                    + _tablo(["Tarih", "Kupon", "Maç", "Seçim", "Oran", "Sonuç", "Kupon durumu"], satirlar[:150], sol=3)
                    + "</div>")

    # --- Analiz ---
    kosullu_satirlar = []
    for d, t in sorted(kosullu.items(), key=lambda kv: float(kv[0].split("–")[0].lstrip("%"))):
        if t["ornek"] >= analiz.MIN_DILIM_ORNEGI:
            kosullu_satirlar.append([d, f"{t['ornek']:,}"] + [f"{t['ornek'] / t[s]:.1f}" if t[s] else "-" for s in IYMS_SIRASI])
    iyms_tablo = iyms_istatistik(kapanis_iyms, sonuclar)
    iyms_satirlari = [[s, t["n"], f"%{100 * t['tuttu'] / t['n']:.1f}", f"%{100 * t['vaat'] / t['n']:.1f}",
                       _getiri_td(t["donus"] / t["n"])] for s, t in iyms_tablo.items() if t["n"]]
    durumlar = {d: sum(1 for s in sonuclar.values() if s.get("durum") == d) for d in ("tamam", "iptal", "belirsiz")}
    sekme_analiz = (
        '<div class="kart"><h2>İY/MS adil oranları (geçmiş)</h2><p class="aciklama">Ev sahibinin kazanma olasılığına göre '
        "her İY/MS sonucunun adil oranı (1 / gerçekleşme sıklığı). iddaa bundan yüksek veriyorsa seçim değerlidir.</p>"
        + _tablo(["Ev kazanma olasılığı", "Maç"] + IYMS_SIRASI, kosullu_satirlar) + "</div>"
        '<div class="kart"><h2>iddaa verisi (sistemin topladığı)</h2><p class="aciklama">Kapanış oranları ve sonuçlar. '
        "Sonuçlar geldikçe büyür.</p><h3>MS oranları</h3>" + _oran_tablosu("iddaa_ms.json", maks=False)
        + "<h3>İY/MS seçimleri</h3>" + _tablo(["Seçim", "Örnek", "Tuttu", "Oranın vaadi", "1 TL →"], iyms_satirlari)
        + "</div>"
        '<div class="kart"><h2>Veri durumu</h2><p class="aciklama">Sonuçlar Mackolik\'ten, iddaa maç numarasıyla eşleştirilir.</p>'
        + _tablo(["Maç", "İY/MS'li", "Sonuçlanan", "İptal", "Sonuç yok", "Kapanış oranı olan"],
                 [[len(kayitlar), sum(1 for k in kayitlar.values() if k.get("iyms_var") == "1"), durumlar["tamam"],
                   durumlar["iptal"], durumlar["belirsiz"], len(kapanis_tum)]]) + "</div>")

    sekmeler = [("kuponlar", "Kuponlar", sekme_kupon), ("oran", "Oran sorgula", sekme_oran),
                ("gecmis", "Kupon geçmişi", sekme_gecmis), ("analiz", "Analiz", sekme_analiz)]
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
