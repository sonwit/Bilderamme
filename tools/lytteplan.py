#!/usr/bin/env python3
"""
lytteplan.py — naar utedelen skal vaakne, regnet ut paa serveren.

Utedelen hadde en fast plan i firmwaren: 04-08 hver halvtime, 09-21 hver time.
To ting var galt med den.

Den foelger ikke sola. I Oslo staar sola opp 03:55 i juni og 09:15 i desember
-- over fem timer forskjell. En fast morgenrunde fra kl. 04 treffer
morgenkoret i juni og et bekmoerkt desember. Her regnes soloppgangen ut for
hver dag, og finvinduet legges rundt den.

Den lyttet for lite. 24 opptak à ett minutt er 2,4 % av doegnets vaakne timer,
og 70 % av de sikre artsfunnene hang paa ETT enkelt minutt -- altsaa arter som
saa vidt ble fanget. Med tettere sampling finner vi mer.

Firmwaren kjenner bare ETT intervall:

    step = (h <= dawn_end) ? dawn_interval_min : 60

-- dagintervallet er hardkodet til 60. Vi kommer likevel rundt det uten aa
flashe paa nytt, fordi brikka henter GET /config etter HVER opplasting: vi
setter dawn_end til slutten av dagen, saa dawn_interval_min styrer alt, og
svarer med FORSKJELLIG intervall alt etter naar brikka spoer. Innenfor
finvinduet faar den 10 minutter, resten av dagen 20. Nye verdier gjelder fra
neste oekt, saa overgangen henger ett hopp etter -- det er greit.

Batteriet er den virkelige grensen. Solcella er netto positiv i august med 24
oekter (3,51 V den 25. -> 4,06 V den 29.), men planen her er 2,7 ganger saa
mange oppvaakninger, og jo moerkere det blir, jo senere staar sola opp OG jo
mindre gir panelet. Derfor trappes planen ned av seg selv naar spenningen
faller. Utedelen skal overleve november.

    from lytteplan import plan
    plan(datetime.now(), volt=4.06)   -> dict med noeklene ESP-en venter
"""

from __future__ import annotations

import datetime
import math

# Hagen. Samme koordinater som resten av prosjektet -- FUGLERAMME_LAT/LON i
# frame_server.env, se oppsett.py.
from oppsett import LAT, LON  # noqa: E402

# Finvinduet: fra en time FOER soloppgang til fire timer etter. Morgenkoret
# begynner foer sola er oppe -- roedstrupe og maaltrost gaar i gang i
# skumringen -- og ebber ut utover formiddagen.
FOER_SOL_MIN = 60
VINDU_TIMER = 4

# Siste oekt for dagen. Uglene synger seinere, men da er batteriet viktigere.
DAG_SLUTT = 21

# Trappene. (nedre spenning, minutter i finvinduet, minutter resten av dagen).
# Foerste rad som spenningen naar opp til vinner. Under den nederste kjoerer vi
# firmwarens gamle plan, som holdt batteriet i live gjennom hele august.
TRAPPER = [
    (3.80, 10, 20),
    (3.65, 15, 30),
    (0.00, 30, 60),
]


def soloppgang(dato: datetime.date, lat: float = LAT, lon: float = LON) -> datetime.time:
    """Lokal soloppgang (NOAA-formelen). Regnes ut, ikke hentet.

    Med vilje uten nett: dette svaret ligger i veien for utedelens
    config-henting, og et API som er nede skal ikke kunne stoppe brikka i aa
    faa en plan. Formelen er noeyaktig paa et par minutter, og vi legger uansett
    en time slakk foran vinduet."""
    n = dato.toordinal() - datetime.date(2000, 1, 1).toordinal() + 0.5
    # Solas midlere lengde og anomali
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    # Deklinasjon og tidsligning
    dekl = math.asin(math.sin(math.radians(23.439)) * math.sin(lam))
    tidsligning = 4 * math.degrees(L - math.atan2(math.cos(math.radians(23.439))
                                                  * math.sin(lam), math.cos(lam)))
    tidsligning = (tidsligning + 180) % 360 - 180      # til [-180, 180) minutter
    # Timevinkel ved soloppgang, med standard refraksjon (-0,833°)
    cos_h = ((math.sin(math.radians(-0.833)) - math.sin(math.radians(lat)) * math.sin(dekl))
             / (math.cos(math.radians(lat)) * math.cos(dekl)))
    if cos_h >= 1:
        return datetime.time(11, 0)    # polarnatt: sola staar ikke opp
    if cos_h <= -1:
        return datetime.time(0, 0)     # midnattssol
    h = math.degrees(math.acos(cos_h))
    minutter = 720 - 4 * (lon + h) - tidsligning       # UTC-minutter
    minutter += 60 * _utc_offset_timer(dato)           # til lokal tid
    minutter %= 1440
    return datetime.time(int(minutter // 60), int(minutter % 60))


def _utc_offset_timer(dato: datetime.date) -> int:
    """CET/CEST. Sommertid fra siste soendag i mars til siste soendag i oktober."""
    def siste_soendag(aar, maaned):
        d = datetime.date(aar, maaned, 31 if maaned in (3, 10) else 30)
        return d - datetime.timedelta(days=(d.weekday() + 1) % 7)
    start = siste_soendag(dato.year, 3)
    slutt = siste_soendag(dato.year, 10)
    return 2 if start <= dato < slutt else 1


def trapp(volt: float | None) -> tuple[float, int, int]:
    """Hvilken trapp spenningen holder til. Ukjent spenning -> forsiktigste."""
    if volt is None:
        return TRAPPER[-1]
    for t in TRAPPER:
        if volt >= t[0]:
            return t
    return TRAPPER[-1]


def plan(naa: datetime.datetime, volt: float | None = None) -> dict:
    """Konfigurasjonen utedelen skal ha akkurat naa.

    Intervallet avhenger av naar brikka spoer, fordi firmwaren bare kan holde
    paa ett om gangen. dawn_end settes til dagens siste time, saa
    dawn_interval_min styrer hele det vaakne doegnet."""
    sol = soloppgang(naa.date())
    start = (datetime.datetime.combine(naa.date(), sol)
             - datetime.timedelta(minutes=FOER_SOL_MIN))
    slutt = start + datetime.timedelta(hours=VINDU_TIMER)

    grense, fint, grovt = trapp(volt)
    i_vinduet = start <= naa < slutt
    intervall = fint if i_vinduet else grovt

    # rev gjoer endringen synlig i helse-JSON-ens cfg_rev: dagnummer, intervall
    # og hvilket vindu vi er i. Ser du 241205, er det dag 241, 20 minutter,
    # utenfor finvinduet.
    rev = int(naa.strftime("%j")) * 1000 + intervall * 10 + (1 if i_vinduet else 2)

    return {
        "rev": rev,
        "dawn_start": start.hour,
        "dawn_end": DAG_SLUTT,          # ett intervall for hele det vaakne doegnet
        "dawn_interval_min": intervall,
        "day_start": start.hour,
        "day_end": DAG_SLUTT,
    }


def oekter_per_doegn(dato: datetime.date, volt: float | None = None) -> int:
    """Hvor mange oppvaakninger planen gir. Det er DETTE som koster batteri --
    hver oekt er ca. 65 sekunder med mikrofon, wifi og opplasting."""
    _, fint, grovt = trapp(volt)
    sol = soloppgang(dato)
    start = (datetime.datetime.combine(dato, sol)
             - datetime.timedelta(minutes=FOER_SOL_MIN))
    vaakent = (DAG_SLUTT - start.hour) * 60
    if vaakent <= 0:
        return 0
    fint_min = min(VINDU_TIMER * 60, vaakent)
    return round(fint_min / fint + (vaakent - fint_min) / grovt)


def forklar(naa: datetime.datetime, volt: float | None = None) -> str:
    sol = soloppgang(naa.date())
    grense, fint, grovt = trapp(volt)
    p = plan(naa, volt)
    return (f"soloppgang {sol:%H:%M} · finvindu "
            f"{p['dawn_start']:02d}:xx–{(p['dawn_start'] + VINDU_TIMER) % 24:02d}:xx "
            f"· trapp {grense:.2f}V gir {fint}/{grovt} min "
            f"· naa {p['dawn_interval_min']} min · rev {p['rev']}")


if __name__ == "__main__":
    import sys
    v = float(sys.argv[1]) if len(sys.argv) > 1 else None
    aar = datetime.date.today().year
    print(f"  {'dato':12s} {'soloppgang':>10s}   plan ved {v if v else 'ukjent'} V")
    for m in range(1, 13):
        d = datetime.datetime(aar, m, 15, 12, 0)
        rader = "  ".join(f"{vv:.2f}V: {oekter_per_doegn(d.date(), vv):3d}"
                          for vv in (4.00, 3.70, 3.55))
        print(f"  {d.date().isoformat():12s} {soloppgang(d.date()):%H:%M}"
              f"   vaakent fra {plan(d, 4.0)['dawn_start']:02d}:xx"
              f"   oekter/doegn -> {rader}")
