"""iddaa.com'un herkese açık JSON servisleri için ince bir istemci."""
import logging
import random
import time

import requests

from .config import ISTEK_ARALIGI

log = logging.getLogger(__name__)

SPORTSBOOK = "https://sportsbookv2.iddaa.com/sportsbook"
STATISTICS = "https://statisticsv2.iddaa.com/statistics"
FUTBOL = 1

BASLIKLAR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Origin": "https://www.iddaa.com",
    "Referer": "https://www.iddaa.com/",
}


class IddaaHatasi(Exception):
    pass


class EngellendiHatasi(IddaaHatasi):
    """403/429 gibi erişim engeli. Tekrar denemek anlamsız, çalışmayı durdurmak gerekir."""


class IddaaIstemci:
    def __init__(self, aralik: float = ISTEK_ARALIGI, zaman_asimi: float = 20, deneme: int = 3):
        self.oturum = requests.Session()
        self.oturum.headers.update(BASLIKLAR)
        self.aralik = aralik
        self.zaman_asimi = zaman_asimi
        self.deneme = deneme
        self._son_istek = 0.0
        self.istek_sayisi = 0

    def _bekle(self):
        kalan = self.aralik - (time.monotonic() - self._son_istek)
        if kalan > 0:
            time.sleep(kalan)

    def getir(self, url: str, params: dict | None = None):
        """JSON yanıtının `data` alanını döner. 404'te None döner."""
        for deneme in range(1, self.deneme + 1):
            self._bekle()
            try:
                yanit = self.oturum.get(url, params=params, timeout=self.zaman_asimi)
                self._son_istek = time.monotonic()
                self.istek_sayisi += 1
                if yanit.status_code == 404:
                    return None
                if yanit.status_code in (401, 403, 429):
                    raise EngellendiHatasi(f"{yanit.status_code} {url}")
                yanit.raise_for_status()
                govde = yanit.json()
                if isinstance(govde, dict) and "isSuccess" in govde:
                    if not govde["isSuccess"]:
                        raise IddaaHatasi(f"isSuccess=false {url}: {govde.get('message')}")
                    return govde.get("data")
                return govde
            except EngellendiHatasi:
                raise
            except (requests.RequestException, ValueError, IddaaHatasi) as hata:
                if deneme == self.deneme:
                    raise IddaaHatasi(f"{url} {deneme} denemede alınamadı: {hata}") from hata
                bekleme = 2 ** deneme + random.random()
                log.warning("%s hata (%s), %.1f sn sonra tekrar", url, hata, bekleme)
                time.sleep(bekleme)

    # --- sportsbook ---
    def bulten(self, canli: bool = False):
        params = {"st": FUTBOL, "type": 0, "version": 0}
        if canli:
            params["live"] = "true"
        return self.getir(f"{SPORTSBOOK}/events", params)

    def mac(self, mac_id: int):
        return self.getir(f"{SPORTSBOOK}/event/{mac_id}")

    def market_ayarlari(self):
        return self.getir(f"{SPORTSBOOK}/get_market_config")

    def ligler(self):
        return self.getir(f"{SPORTSBOOK}/competitions")

    def secenek_oynanma(self):
        return self.getir(f"{SPORTSBOOK}/outcome-play-percentages", {"sportType": FUTBOL})

    def mac_oynanma(self):
        return self.getir(f"{SPORTSBOOK}/played-event-percentage", {"sportType": FUTBOL})

    # --- statistics ---
    def son_maclar(self, mac_id: int):
        return self.getir(f"{STATISTICS}/soccer/recent-matches/{mac_id}")
