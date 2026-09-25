# nettside/ — produktsiden på GitHub Pages

Siden som lenkes fra repoet og fra CV-en: hva rammen viser, fuglene i
biblioteket, hvordan det virker, valgene, og hvordan det er bygd. Statisk
HTML uten JavaScript, bygd av `bygg.py` fra det som alt ligger i repoet.

```bash
python3 nettside/bygg.py                          # -> nettside/ut/
python3 -m http.server 8765 --directory nettside/ut
```

Pillow er valgfritt. Med Pillow lages nedskalerte WebP-bilder av plansjefuglene,
grenene og bildene; uten kopieres originalene, og siden blir tung, men riktig.

| Fil | Hva |
|---|---|
| `bygg.py` | Generatoren. Leser `plates/`, `tools/bird_names.py`, `tools/lytteplan.py` og mappene under. |
| `innhold_nb.py`, `innhold_en.py` | All tekst, norsk og engelsk, med samme nøkler. Begge bygges hver gang: norsk i roten, engelsk under `en/`, med samme bilder. Språkvelgeren i toppen peker på samme side på det andre språket. |
| `stil.css` | Stilarket. Samme uttrykk som veggen: hvitt papir, svart blekk, seks farger, EB Garamond. |
| `fonter/` | EB Garamond som woff2, subsettet til latin. SIL Open Font License, se `OFL.txt`. |
| `bilder/` | Bildene på byggesiden og forsiden. |
| `statistikk.json` | Hvor mange dager hver art er hørt, fra `tools/artsstatistikk.py`. Biblioteket sorteres etter den; mangler den, blir det alfabetisk. |
| `dager/` | Dagene siden kan bla i: én PNG og én JSON per dag. Kontrakten står i `dager/README.md`. JSON-en er på norsk; den engelske siden slår opp artsnavn via latin i `plates/arter.json` og `innhold_en.py`, og oversetter værordene. |
| `ut/` | Resultatet. Ikke i git. |

Siden henter ingenting fra andre tjenester: fontene ligger her, og det er ingen
sporing. Den viser aldri koordinater, uansett hva veggen viser.

## Publisering

`.github/workflows/nettside.yml` bygger siden ved hver push til `main` og
legger `nettside/ut/` på GitHub Pages. Repoet må være offentlig, og Pages må
stå på «GitHub Actions» under Settings → Pages. Adressen blir
`https://sonwit.github.io/Bilderamme/`; `NETTSIDE_URL` overstyrer den for
`og:image`.

Serveren skriver `dager/<dato>.json` og `.png` selv etter hver tegning
(`tools/eksporter_dag.py`), regner statistikken og pusher. Oppsettet på
serveren står i `deploy/README.md`.

## Det som gjenstår

- Nye bilder av rammen etter at serveren har fått koden som runder bunnlinjen.
