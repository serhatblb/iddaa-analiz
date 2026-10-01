# iddaa-analiz

iddaa.com futbol bülteninden oranları ve sonuçları düzenli toplayan, İY/MS başta olmak üzere
"hangi seçim oranının vaat ettiğinden sık tutuyor" sorusunu veriyle cevaplamaya çalışan kişisel analiz projesi.
Bahis oynamaz, siteye giriş yapmaz; sadece herkese açık bülten verisini okur. Kuponlar kağıt üstündedir.

## Nasıl çalışır

Her şey GitHub Actions'ta çalışır, bilgisayarın açık olması gerekmez.

| Workflow | Zaman | İş |
|---|---|---|
| Saatlik toplama | Her saat (zincir, cron yedek) | Bülten, oranlar, en çok oynananlar; sonuçlar ve lig eşleştirme (Mackolik); kuponlar, sanal tekliler; panel |
| Günlük kupon ve rapor (yedek) | Her gün 09:43 | Saatlik çalışma zaten 09:40'tan sonraki ilk çalışmada bugünün dört kuponunu seçer, rapor yazar ve mail atar; bu workflow sadece yedek |
| Mackolik arşivi | Her pazartesi 08:11 | 2019'dan bugüne bitmiş bütün iddaa maçları: skorlar, lig, iddaa MS ve 2.5 A/Ü oranları |
| Geçmiş maç oranları | Her gece 04:23 | Arşivdeki maçların Mackolik sayfalarından İY/MS, toplam gol, KG, İY, alt/üst, çifte şans oranları ve MBS (en yeniden eskiye, kaldığı yerden); sonra model |
| Geçmiş veri ve analiz | Her pazartesi 06:23 | football-data.co.uk verisi (karşılaştırma için) ve model |
| Keşif | Elle | Deneme betiklerini GitHub'da çalıştırıp çıktıyı `kesif/<isim>` dalına yazar |
| Testler | Kod değişince | `pytest` |

Toplama kuralları:
- Maç ilk görüldüğünde tüm maç önü marketler **açılış** olarak kaydedilir.
- İY/MS'si olan maçların İY/MS oranları **her saat** kaydedilir.
- Başlamaya 75 dakika kala tüm marketler bir kez **kapanış** olarak kaydedilir.
- İY/MS'si olmayan yakın maçlar 2 saatte bir tekrar kontrol edilir.

Kuponlar (20 TL, kağıt üstü), bugün (Türkiye saatiyle gece 24:00'e kadar) başlayacak maçlardan; her maçtan en fazla bir seçim:
- **İY/MS hayal kuponu:** hep 3 maç. iddaa İY/MS oranlarına tavan koyuyor (~36 Kral oran); günün en yüksek oranlı
  (30 ve üstü, yetmezse 20 ve üstü) İY/MS seçenekleri arasından, maçın MS ve 2.5 A/Ü oranlarına benzer geçmiş maçlarda
  (2019'dan beri bütün arşiv) en sık tutmuş 3 maç. Tavandaki sürprizler aynı oranı alsa da gerçek şansları farklı:
  modelin görmediği 12 ayda en olası dilim %2.6, en az olası %0.8 tuttu. Kupon oranı ~30–47 bin.
- **1-0-2 kuponu:** oranı 1.40–5.00 arası MS seçimlerinden beklenen dönüşü en yüksekler.
- **İY/MS değer kuponu:** her maçın beklenen dönüşü en yüksek İY/MS seçimi.
- **Gol kuponu:** toplam gol (0-1 / 2-3 / 4-5 / 6+) seçimlerinden beklenen dönüşü en yüksekler.

Beklenen dönüş = iddaa.com oranı (Kral) × modelin olasılığı. Son üç kuponda maç sayısı MBS'ye göre seçilir: 1, 2 ve 3
maçlık kuponlardan (her seçimin MBS'si maç sayısını geçmemeli) beklenen dönüşü en yüksek olan; eşitlikte az maçlı olan.
Her eklenen maç iddaa'nın payını bir kez daha çarpar.

Sanal tekliler (`tekler.py`): başlamasına 20 dk – 4 saat kala her maçın beklenen dönüşü 1'in üstündeki bütün seçimleri
1 TL oynanmış gibi kaydedilir; sonuç ve kapanış oranıyla (CLV) değerlendirilir. Modelin gerçekten işe yarayıp
yaramadığını kuponlardan çok daha hızlı gösterir.

## Model (iddaa'nın kendi geçmişi)

`kalibrasyon.py`: "iddaa bu seçeneğe kâr payı ayıklanınca %q şans veriyordu; gerçekte ne sıklıkla tuttu?"
Market ve seçenek başına logit(p) = a + b·logit(q) + c·logit(q)² eğrisi, üstüne lig düzeltmesi (az maçlı ligler genel
ortalamaya çekilir, ampirik Bayes). Aynı marketin seçenekleri toplamı 1 olacak şekilde normalleştirilir.
Veri: Mackolik arşivi (skorlar, lig, MS ve 2.5 A/Ü oranları) + maç sayfalarındaki oranlar (İY/MS, toplam gol, KG, İY,
1.5/2.5/3.5 A/Ü). Mackolik'teki oranlar standart iddaa oranıdır; iddaa.com ve bayilerdeki Kral oran bunların 1.04 katı.

Çıktılar (`data/analiz/`): `kalibrasyon.json` (model, son 36 ay), `geriye_test.json` (model son 12 ayı görmeden
kurulur, o 12 ayda stratejiler denenir), `iddaa_senaryolar.json` (bütün geçmiş: her seçime / oran aralığına 1 TL),
`iddaa_oran_tablosu.json` (Kral oran başına kaç kez oynandı, kaç kez tuttu).

İlk bulgular (Ağustos 2019 – Eylül 2026, 396 bin maç): MS'de her seçime 1 TL → 0.83; favoriler (1.00–1.50) 0.90,
5.00 üstü 0.69; 2.5 A/Ü 0.86. Hiçbir oran aralığı kâr ettirmiyor; oran yükseldikçe kayıp büyüyor (sürprizlere fazla şans
veriliyor). iddaa her maçta bütün marketlere neredeyse aynı kâr payını koyuyor (standart oranla ~%22, İY/MS ~%31).

Sonuçlar Mackolik'in günlük canlı sonuç verisinden (`vd.mackolik.com/livedata?date=GG/AA/YYYY`) iddaa maç
numarasıyla eşleştirilerek alınır. MS için 90 dakika skoru kullanılır; ertelenen, hükmen ve yarıda kalan maçlar iptal
(oran 1) sayılır. 3 gün içinde sonucu bulunamayan maç "belirsiz" olur ve o kupon kasaya katılmaz.
Ayarlar `iddaa/config.py` içinde (ortam değişkenleriyle de değiştirilebilir).

## Veri düzeni

```
data/
  maclar/YYYY-MM.csv                    maç kayıtları (lig, takımlar, başlama, bayraklar)
  sonuclar/YYYY-MM.csv                  İY ve MS skorları
  oranlar/YYYY/MM/DD/HHMM.csv.gz         çalışma başına oran anlıkları (tip: acilis/saatlik/kapanis)
  oynanma/secenek/YYYY/MM/DD/HHMM.csv.gz seçenek bazında oynanma yüzdeleri
  oynanma/mac/YYYY/MM/DD/HHMM.csv.gz     maç bazında oynanma payı
  kuponlar.csv                          kağıt üstü kuponlar
  adaylar/YYYY-MM-DD.json               o günün tüm kupon adayları
  tekler/YYYY-MM.csv                    sanal tekliler (maça yakın değerli seçimler)
  arsiv/YYYY-MM.csv.gz                  Mackolik arşivi: bitmiş iddaa maçları, skorlar, lig, MS ve 2.5 A/Ü oranları
  arsiv_oran/YYYY-MM.csv.gz             maç sayfalarından geçmiş oranlar (İY/MS, toplam gol, KG, İY, A/Ü, ÇŞ) ve MBS
  analiz/                               model ve analiz tabloları
  raporlar/YYYY-MM-DD.md                günlük raporlar
  ligler.csv, market_ayarlari.json      lig ve market isimleri
```

Market anahtarı `t_st` formatındadır; İY/MS `2_90`, Maç Sonucu `1_1`. İY/MS seçeneklerinde `0` beraberliktir.
Tüm zamanlar UTC tutulur, raporlarda Türkiye saatine çevrilir.

## Zamanlama notu

GitHub'ın zamanlanmış (cron) tetikleyicileri Ağustos 2026'dan beri bazı repolarda saatlerce gecikiyor ya da hiç
çalışmıyor. Bu yüzden saatlik çalışma bir zincir: her çalışma bitince `bekleme` ortamının 55 dakikalık bekleme süresi
dolunca bir sonrakini kendisi başlatır. Cron sadece yedek. Zincir için repo ayarlarında bir kez
Settings → Environments → `bekleme` → Wait timer 55 dakika tanımlanmalı; tanımlı değilse zincir kendini durdurur
(uyarı yazar), cron ile devam edilir. Günlük kupon ayrı bir zamanlamaya bağlı değil, saatlik çalışmanın içinde.
Saatlik çalışma elle de başlatılabilir: Actions → Saatlik toplama → Run workflow.

## Panel

Her çalışmada `docs/index.html` yeniden üretilir. Üç sekme: **Bugün** (dört kupon ve kasa), **Geçmiş** (kupon başına bir
satır, ✅/❌) ve **Oran sorgula** (bir oran yaz, iddaa'nın 2019'dan beri kendi oranlarıyla ne sıklıkla tuttuğunu gör).
Günlük mail de kısa: bugünün kuponları, dünün sonuçları, kasa. Model, geriye dönük test ve sanal tekliler
`data/analiz/` ve `data/tekler/` altında tutulur, panelde gösterilmez.

## Eski değer hesabı (yedek)

Model bir marketi henüz kapsamıyorsa (ör. maç sayfası oranları inmeden önce İY/MS) football-data.co.uk verisiyle kurulan
eski tablolar kullanılır: geçmiş maçlar ev sahibinin kazanma olasılığına göre %5'lik dilimlere ayrılır, her dilimde
9 İY/MS sonucunun ve 1-0-2'nin gerçek sıklığı ölçülür; beklenen dönüş = iddaa oranı × o dilimdeki gerçek sıklık.

## SQL ile analiz

Dosyalar doğrudan DuckDB ile sorgulanabilir (`pip install duckdb`):

```sql
-- Kapanış İY/MS oranları ve sonuçlar: oran aralığına göre tutma oranı ve getiri
WITH kapanis AS (
  SELECT o.mac_id, o.secenek, o.oran,
         row_number() OVER (PARTITION BY o.mac_id, o.secenek ORDER BY o.zaman_utc DESC) AS sira
  FROM read_csv('data/oranlar/*/*/*/*.csv.gz') o
  JOIN read_csv('data/maclar/*.csv') m USING (mac_id)
  WHERE o.market = '2_90' AND o.zaman_utc < m.baslama_utc
), sonuc AS (
  SELECT mac_id,
         CASE WHEN iy_ev > iy_dep THEN '1' WHEN iy_ev < iy_dep THEN '2' ELSE '0' END || '/' ||
         CASE WHEN ms_ev > ms_dep THEN '1' WHEN ms_ev < ms_dep THEN '2' ELSE '0' END AS gercek
  FROM read_csv('data/sonuclar/*.csv') WHERE durum = 'tamam'
)
SELECT floor(oran / 5) * 5 AS oran_araligi,
       count(*) AS ornek,
       avg((k.secenek = s.gercek)::int) AS tutma_orani,
       avg(1 / oran) AS vaat_edilen,
       sum(CASE WHEN k.secenek = s.gercek THEN oran ELSE 0 END) / count(*) AS getiri
FROM kapanis k JOIN sonuc s USING (mac_id)
WHERE sira = 1
GROUP BY 1 ORDER BY 1;
```

Getiri 1'in üstündeyse o grup uzun vadede kazandırıyor demektir. Çok sayıda gruba bakıldığında bazıları
şans eseri iyi görünür; bir örüntüyü ancak sonradan toplanan veride de tutuyorsa ciddiye al.

## Mail kurulumu

Rapor maili için repo → Settings → Secrets and variables → Actions altına:
- `GMAIL_ADRES`: gönderen Gmail adresi
- `GMAIL_UYGULAMA_SIFRESI`: Google hesabı → Güvenlik → 2 Adımlı Doğrulama → Uygulama şifreleri
- `MAIL_ALICI` (isteğe bağlı): farklı bir alıcı

Secret'lar yoksa rapor sadece `data/raporlar/` altına yazılır.

## Yerelde çalıştırma

```bash
pip install -r requirements.txt
python -m iddaa.topla     # tek seferlik toplama
python -m iddaa.sonuc     # sonuçlar
python -m iddaa.kupon     # bugünün kuponu
python -m iddaa.rapor     # rapor
python -m pytest -q
```

## Yol haritası

- [x] Toplayıcı, sonuçlar, kağıt kupon, günlük rapor
- [x] football-data.co.uk geçmiş verisiyle MS ve İY/MS analizi, değer adayları, statik panel
- [x] Mackolik arşivi: iddaa'nın kendi geçmiş oranları (2019'dan beri, bütün ligler)
- [x] Kalibrasyon modeli, lig düzeltmesi, geriye dönük test, MBS'ye göre kupon, sanal tekliler
- [ ] Bütün yılların maç sayfası oranları (her gece devam ediyor)
- [ ] Oran hareketi (açılıştan kapanışa) ve "en çok oynananlar" etkisinin modele eklenmesi
