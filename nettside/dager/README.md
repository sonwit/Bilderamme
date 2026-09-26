# nettside/dager/ — én dag om gangen

Hver dag siden skal kunne vise ligger her som to filer med samme navn:

- `YYYY-MM-DD.png`: illustrasjonen uten tekst, slik `compose_branch.py`
  skriver `plates/dagens-bakgrunn.png`. 1200×1600, hvit bakgrunn.
- `YYYY-MM-DD.json`: det siden trenger for å tegne listen oppå.

```json
{
  "dato": "2026-09-24",
  "tegnet": "16:00",
  "periode": "05:46–15:59",
  "opptak": 44,
  "vaer": "Overskyet · 13° · 3 m/s",
  "antall_arter": 10,
  "hoert": [
    {"nr": 1, "norsk": "Skjære", "latin": "Pica pica", "sikkerhet": 99,
     "tid": "14:19", "belegg": "1 ggr",
     "boks": [592, 1144, 964, 1418], "merke": [675, 1386]},
    {"norsk": "Kaie", "latin": "Corvus monedula", "sikkerhet": 83,
     "tid": "09:39", "belegg": "5 ggr"}
  ],
  "ogsaa": ["Myrrikse", "Kjøttmeis"],
  "bilde": "2026-09-24.png",
  "doegn": [
   {"t": "04:59", "arter": [["Kattugle", "Strix aluco", 60]]},
   {"t": "05:29", "arter": []},
   {"t": "06:59", "arter": [["Kjøttmeis", "Parus major", 92], ["Bokfink", "Fringilla coelebs", 57]]}
  ]
}
```

`doegn` er dagsoversikten: ett innslag per opptak, i klokkerekkefølge, med
tidspunktet og artene i nettopp det opptaket som `[norsk, latin, prosent]`.
Terskelen er den samme som hovedlisten på arket bruker (50 %), så et opptak
der bare et usikkert treff lå under, står med tom liste — det samme gjør et
opptak der ingenting ble hørt. De tomme er halve poenget: de viser når
mikrofonen sto på uten at noen sang. Listen kan inneholde en art som ikke er
på arket, siden arket har plass til et begrenset antall linjer.

Ingen filnavn, ingen lyd, ingen kamerabilder: dette repoet er offentlig, og
dagsfilen skal tåle å ligge der. Feltet kan mangle helt — dagene som ble lagt
inn for hånd fra arkivet har det ikke, og da viser siden ingen døgn-seksjon.

`nr`, `boks` og `merke` finnes bare for artene som faktisk står på grenen;
de kommer fra `dagens-bakgrunn.json` og er i bildets koordinater. Arter uten
plansje står i listen uten nummer, som på veggen. `ogsaa` er fotnoten.

Ingen posisjon. Siden viser aldri koordinater, uansett hva veggen viser.

Serveren skriver disse to filene selv etter hver tegning, med
`tools/eksporter_dag.py`, og pusher dem hit sammen med `statistikk.json`. Hver
push bygger siden. Lista settes sammen med de samme funksjonene som veggen,
så JSON-en sier det samme som arket. Eksporten går noen minutter etter
tegningen, så et opptak eller to kan ha kommet til siden. Dagene til og med
23. september 2026 ble lagt inn for hånd fra arkivet, med `ferdig_side`.
