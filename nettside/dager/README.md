# nettside/dager/ — én dag om gangen

Hver dag sida skal kunne vise ligger her som to filer med samme navn:

- `YYYY-MM-DD.png`: illustrasjonen uten tekst, slik `compose_branch.py`
  skriver `plates/dagens-bakgrunn.png`. 1200×1600, hvit bakgrunn.
- `YYYY-MM-DD.json`: det sida trenger for å tegne lista oppå.

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
  "bilde": "2026-09-24.png"
}
```

`nr`, `boks` og `merke` finnes bare for artene som faktisk står på grenen;
de kommer fra `dagens-bakgrunn.json` og er i bildets koordinater. Arter uten
plansje står i lista uten nummer, som på veggen. `ogsaa` er fotnoten.

Ingen posisjon. Sida viser aldri koordinater, uansett hva veggen viser.

Fase to: serveren skriver disse to filene selv etter hver tegning og pusher
dem hit, så dagvelgeren oppdaterer seg uten at noen gjør noe. Til det er på
plass legges dager inn for hånd.
