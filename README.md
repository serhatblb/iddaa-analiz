# iddaa-analiz

iddaa.com futbol bülteninden oranları ve sonuçları düzenli toplayan, İY/MS başta olmak üzere
"hangi seçim oranının vaat ettiğinden sık tutuyor" sorusunu veriyle cevaplamaya çalışan kişisel analiz projesi.
Bahis oynamaz, siteye giriş yapmaz; sadece herkese açık bülten verisini okur. Kuponlar kağıt üstündedir.

## Nasıl çalışır

Her şey GitHub Actions'ta çalışır, bilgisayarın açık olması gerekmez.

| Workflow | Zaman | İş |
|---|---|---|
| Saatlik toplama | Her saat :17 | Bülten, oranlar, en çok oynananlar; biten maçların sonuçları (Mackolik); panel |
| Günlük kupon ve rapor | Her gün 09:43 | Dünkü kuponları değerlendirir, bugünün İY/MS ve 1-0-2 kuponlarını seçer, rapor yazar ve mail atar |
| Geçmiş veri ve analiz | Her pazartesi 06:23 | football-data.co.uk'tan 22 lig, 2012'den bugüne maçlar; MS oran aralığı ve İY/MS adil oran tabloları |
| Testler | Kod değişince | `pytest` |

Toplama kuralları:
- Maç ilk görüldüğünde tüm maç önü marketler **açılış** olarak kaydedilir.
- İY/MS'si olan maçların İY/MS oranları **her saat** kaydedilir.
- Başlamaya 75 dakika kala tüm marketler bir kez **kapanış** olarak kaydedilir.
- İY/MS'si olmayan yakın maçlar 2 saatte bir tekrar kontrol edilir.

Kuponlar (20 TL, kağıt üstü), önümüzdeki 24 saatte başlayacak maçlardan:
- **İY/MS kuponu:** oranı 20–30 arası İY/MS seçenekleri; her maçtan en yüksek oranlı olan aday olur, en yüksek 3 aday seçilir.
- **1-0-2 kuponu:** oranı 1.40–5.00 arası MS seçimleri; her seçimin geçmişte ne sıklıkla tuttuğu, iddaa'nın kâr payı
  ayıklanmış olasılığı benzer (±2 puan) geçmiş seçimlerden bulunur. 1 TL'ye beklenen dönüşü en yüksek 3 seçim (farklı maçlar).

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
  raporlar/YYYY-MM-DD.md                günlük raporlar
  ligler.csv, market_ayarlari.json      lig ve market isimleri
```

Market anahtarı `t_st` formatındadır; İY/MS `2_90`, Maç Sonucu `1_1`. İY/MS seçeneklerinde `0` beraberliktir.
Tüm zamanlar UTC tutulur, raporlarda Türkiye saatine çevrilir.

## Panel

Her çalışmada `docs/index.html` yeniden üretilir: kasa ve kuponlar, önümüzdeki 24 saatin değerli görünen seçimleri,
geçmiş veride MS 1-0-2 oran aralıkları, ev sahibinin gücüne göre İY/MS adil oranları ve toplanan iddaa verisinin
istatistikleri. Statik tek dosya; GitHub Pages (kaynak: `main` / `docs`) veya Vercel (kök dizin: `docs`) ile yayınlanabilir.

## Değer hesabı

Geçmiş maçlar ev sahibinin kazanma olasılığına (oranlardan, kâr payı ayıklanarak) göre %5'lik dilimlere ayrılır.
Her dilimde 9 İY/MS sonucunun ve 1-0-2'nin gerçek sıklığı ölçülür. Bugünkü bir iddaa maçı, iddaa'nın MS oranlarından
aynı şekilde dilimine yerleştirilir; beklenen dönüş = iddaa oranı × o dilimdeki gerçek sıklık.

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
- [ ] Haftalık analiz raporu: market × oran aralığı × lig
- [ ] Keşif/doğrulama ayrımıyla onaylı grupların günlük önerisi
