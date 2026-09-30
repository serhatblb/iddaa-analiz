"""Proje genelindeki sabitler. Ortam değişkenleriyle ezilebilir."""
import os
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VERI_DIZINI = Path(os.environ.get("IDDAA_VERI", "data"))
TR = ZoneInfo("Europe/Istanbul")

# iddaa market anahtarları: "{t}_{st}"
IYMS = "2_90"                      # 1. Yarı / Maç Sonucu
MAC_ONCESI_TIPLER = (1, 2)         # t=4 canlı marketler, toplanmıyor
# Bültende gelen ve her saat izlenen marketler: MS, toplam gol, 1. yarı sonucu, karşılıklı gol, İY/MS, alt/üst.
# Sadece oranı değişen marketler yazılır (bir seçenek değişse marketin bütün seçenekleri).
SAATLIK_MARKETLER = {"1_1", "2_4", "2_88", "2_89", "2_90", "2_101"}

# Toplama kuralları
KAPANIS_ONCESI = timedelta(minutes=75)   # başlamaya bu kadar kala tüm marketlerin kapanış anlığı
IYMS_TEKRAR_KONTROL = timedelta(hours=2) # İY/MS'si olmayan maçlar bu aralıkla tekrar kontrol edilir
IYMS_KONTROL_UFKU = timedelta(hours=36)  # sadece bu süre içinde başlayacak maçlar tekrar kontrol edilir
ISTEK_ARALIGI = float(os.environ.get("IDDAA_ISTEK_ARALIGI", "0.4"))  # saniye

# Sonuç arama
SONUC_ARAMA_UFKU = timedelta(days=10)
IPTAL_SURESI = timedelta(days=3)                # bu süre sonunda sonuç yoksa "belirsiz" sayılır

# Kağıt üstü kupon
# İY/MS hayal kuponu: önce bu orandan yüksek (iddaa'nın tavanı ~36) seçenekler, yetmezse yedek alt sınır
HAYAL_MIN_ORAN = float(os.environ.get("HAYAL_MIN_ORAN", "30"))
KUPON_MIN_ORAN = float(os.environ.get("KUPON_MIN_ORAN", "20"))
KUPON_MAX_ORAN = float(os.environ.get("KUPON_MAX_ORAN", "30"))
KUPON_MAC_SAYISI = int(os.environ.get("KUPON_MAC_SAYISI", "3"))
KUPON_TUTARI = float(os.environ.get("KUPON_TUTARI", "20"))
KUPON_BUTCE = float(os.environ.get("KUPON_BUTCE", "1000"))
MS_KUPON_MIN_ORAN = float(os.environ.get("MS_KUPON_MIN_ORAN", "1.40"))
MS_KUPON_MAX_ORAN = float(os.environ.get("MS_KUPON_MAX_ORAN", "5.00"))
