"""iddaa bülten JSON'unu düz satırlara çeviren saf fonksiyonlar."""
from datetime import datetime, timezone

from .config import IYMS, MAC_ONCESI_TIPLER


def market_anahtari(market: dict) -> str:
    return f"{market.get('t')}_{market.get('st')}"


def baslama(mac: dict) -> datetime:
    return datetime.fromtimestamp(int(mac["d"]), tz=timezone.utc)


def iso(zaman: datetime) -> str:
    return zaman.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_oku(metin: str) -> datetime:
    return datetime.strptime(metin, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def mac_oncesi_marketler(mac: dict) -> list[dict]:
    return [m for m in mac.get("m") or [] if m.get("t") in MAC_ONCESI_TIPLER]


def iyms_var(mac: dict) -> bool:
    return any(market_anahtari(m) == IYMS for m in mac.get("m") or [])


def oran_satirlari(mac: dict, tip: str, zaman: datetime, sadece: set[str] | None = None) -> list[dict]:
    satirlar = []
    zaman_metni = iso(zaman)
    for market in mac_oncesi_marketler(mac):
        anahtar = market_anahtari(market)
        if sadece is not None and anahtar not in sadece:
            continue
        for secenek in market.get("o") or []:
            if secenek.get("odd") is None:
                continue
            satirlar.append({
                "mac_id": mac["i"],
                "market": anahtar,
                "market_id": market.get("i"),
                "cizgi": market.get("sov", ""),
                "secenek_no": secenek.get("no"),
                "secenek": secenek.get("n"),
                "oran": secenek.get("odd"),
                "wodd": secenek.get("wodd", ""),
                "tip": tip,
                "zaman_utc": zaman_metni,
                "mbs": market.get("mbc", ""),
            })
    return satirlar


def lig_satirlari(ligler: list[dict]) -> list[dict]:
    return [
        {"lig_id": l.get("i"), "ulke": l.get("cid", ""), "ad": (l.get("n") or "").strip(),
         "kisa_ad": (l.get("sn") or "").strip()}
        for l in ligler or []
        if str(l.get("si")) == "1"
    ]


def secenek_oynanma_satirlari(veri: dict, mac_idleri: set[str], zaman: datetime) -> list[dict]:
    """{maçId: {marketId: {seçenekNo: yüzde}}} -> satırlar (sadece takip edilen maçlar)."""
    satirlar = []
    zaman_metni = iso(zaman)
    for mac_id, marketler in (veri or {}).items():
        if str(mac_id) not in mac_idleri:
            continue
        for market_id, secenekler in (marketler or {}).items():
            for no, yuzde in (secenekler or {}).items():
                satirlar.append({"mac_id": mac_id, "market_id": market_id, "secenek_no": no,
                                 "yuzde": yuzde, "zaman_utc": zaman_metni})
    return satirlar


def mac_oynanma_satirlari(veri: dict, mac_idleri: set[str], zaman: datetime) -> list[dict]:
    zaman_metni = iso(zaman)
    return [
        {"mac_id": mac_id, "yuzde": yuzde, "zaman_utc": zaman_metni}
        for mac_id, yuzde in (veri or {}).items()
        if str(mac_id) in mac_idleri
    ]


def sonuc_isareti(ev: int, dep: int) -> str:
    return "1" if ev > dep else ("2" if dep > ev else "0")


def iyms_sonucu(iy_ev: int, iy_dep: int, ms_ev: int, ms_dep: int) -> str:
    """iddaa adlandırması: 0 = beraberlik. Örn. İY 1-0, MS 1-2 -> '1/2'."""
    return f"{sonuc_isareti(iy_ev, iy_dep)}/{sonuc_isareti(ms_ev, ms_dep)}"
