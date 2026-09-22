#!/usr/bin/env python3
"""
oppsett.py -- det som er personlig i et ellers offentlig repo: hvor hagen
er, og hvem som skal kontaktes om et nettkall gaar galt.

Begge leses fra miljoeet. Paa serveren staar de i frame_server.env, som
baade cron-jobben og systemd-tjenestene leser:

    FUGLERAMME_LAT=59.98
    FUGLERAMME_LON=10.93
    FUGLERAMME_KONTAKT=https://github.com/sonwit/Bilderamme

Koordinatene styrer vaervarselet (api.met.no), BirdNETs artsfilter (hvilke
arter som er plausible her akkurat naa) og soloppgangen i lytteplanen.
Standardverdien er avrundet til to desimaler -- rundt en kilometer -- og det
holder for alle tre; ingen av dem skiller finere. Hagen selv skal ikke staa
i koden.

Kontakten gaar inn i User-Agent mot api.met.no og Wikimedia Commons, som
begge krever at klienten sier hvem den er. E-post eller URL; standard peker
til repoet.

    from oppsett import LAT, LON, user_agent
    requests.get(url, headers={"User-Agent": user_agent("fugleramme-epaper/1.0")})
"""

import os

# `or`, ikke bare get(): en tom linje i env-fila skal bety «standard», ikke krasj.
LAT = float(os.environ.get("FUGLERAMME_LAT") or "59.98")
LON = float(os.environ.get("FUGLERAMME_LON") or "10.93")

KONTAKT = os.environ.get("FUGLERAMME_KONTAKT") or "https://github.com/sonwit/Bilderamme"


def user_agent(navn: str) -> str:
    """Identifiserende User-Agent: «produkt/versjon (kontakt)»."""
    return f"{navn} ({KONTAKT})"
