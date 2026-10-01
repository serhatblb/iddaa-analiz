"""Günlük iş: kuponları değerlendir, sabah 09:40'tan sonra bugünün kuponlarını bir kez oluştur, rapor ve mail.
Her çalışmada ayrıca başlamasına az kalan maçların değerli seçimleri sanal tekli olarak kaydedilir (`tekler.py`).

Saatlik çalışmanın içinden çağrılır; GitHub'ın zamanlanmış tetikleyicileri güvenilmez olduğu için günlük kupon
ayrı bir zamanlamaya bağlı değildir. Aynı gün ikinci kez kupon oluşturmaz, mail de sadece kupon oluşturulduğunda gider.
"""
import logging
import sys
from datetime import datetime, time, timezone

from . import config, depo, kupon, pinnacle, rapor, tekler

log = logging.getLogger("gunluk")
KUPON_SAATI = time(9, 40)


def calistir(simdi: datetime | None = None, zorla: bool = False) -> dict:
    simdi = (simdi or datetime.now(timezone.utc)).replace(microsecond=0)
    yerel = simdi.astimezone(config.TR)
    olustur = zorla or yerel.time() >= KUPON_SAATI
    ozet = kupon.calistir(simdi, olustur=olustur)
    ozet["tekler"] = tekler.calistir(simdi)
    if olustur:
        try:
            ozet["pinnacle"] = pinnacle.calistir(simdi)  # günde bir kez, anahtar yoksa atlanır
        except Exception as hata:  # deneme amaçlı; kuponları ve maili engellemesin
            log.warning("Pinnacle karşılaştırması yapılamadı: %s", hata)
    if ozet["yeni"]:
        r = rapor.olustur(simdi)
        yol = depo.kok() / "raporlar" / f"{yerel.date().isoformat()}.md"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text("\n".join(r.md), encoding="utf-8")
        ozet["mail"] = rapor.mail_gonder(r, f"iddaa kuponları {yerel.strftime('%d.%m.%Y')}")
    return ozet


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info("özet: %s", calistir(zorla="--zorla" in sys.argv))


if __name__ == "__main__":
    main()
