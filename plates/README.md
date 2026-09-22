# plates/ — plansjebiblioteket

Det som tegnes på fuglesida, lagd én gang per art og gjenbrukt hver dag arten
dukker opp. Biblioteket vokser med arter, ikke med dager.

```
plates/
├── <slekt-art>.jpg      kildeplansjen, skannet fra en gammel fuglebok (Commons, public domain)
├── plates.json          kilde, kunstner og lisens for hver plansje
├── arter.json           norsk navn, lengde i cm, habitat, overvintring (leses av bird_names.py)
├── fugler/
│   ├── <art>.png            1:1-fuglen: sittende, på hvitt, tegnet med plansjen som forelegg
│   ├── <art>-flyvende.png   flygende variant
│   ├── <art>-klatrende.png  for spettene
│   └── <art>.json           fotpunktet, og "kilde": "modell" eller "manuell"
├── maler/
│   ├── gren.png             den faste grenen, laget én gang med compose_hero.py --lag-gren
│   ├── gren-vaar.png …      årstidsvarianter (bjørk, rogn, gran, myr) med måneder i JSON
│   └── *.json               hvilke måneder, hvilken mal den bygger på, prompten
├── vasket/              hvitpunkt-korrigerte plansjer. Lages av prepare_plates.py, ikke i git.
└── dagens-*             dagens ferdige illustrasjon. Byttes hver morgen, ikke i git.
```

## Kildene

Wikimedia Commons har en `<Vitenskapelig navn> (illustrations)`-kategori for
nesten hver art, med plansjene fra Naumann, Gould, Keulemans, Morris og
Graves. Alle falt i det fri. Kategoriene er rotete, med frimerker, lydfiler
og 250 px-utsnitt, så `fetch_plates.py` lager en kortliste og nekter alt som
ikke er public domain eller CC0. Kilde og lisens noteres i `plates.json`, så
vi kan svare på hvor et bilde kommer fra.

Fuglene i `fugler/` og malene i `maler/` er tegnet av en bildemodell med
plansjene som forelegg, i samme stil. De er tegninger etter forelegg, ikke
oppslagsverk: en fugl her kan ha feil vingebånd.

## Å legge til en ny art

`ny_art.py` gjør hele jobben, på serveren i bilde-venv-et:

```bash
venv/bin/python ny_art.py --art "Chloris chloris"
venv/bin/python ny_art.py --mangler --birds birds.json     # alle dagens arter uten plansje
```

Den finner kandidatplansjene på Commons, lar modellen velge den som faktisk
er brukbar, vasker skanningen, skriver metadata til `arter.json`, tegner
sittende og flygende fugl, og måler fotpunktet. To bildekall og to
modellkall per art, én gang. Den daglige kjeden kjører den selv for inntil to
nye arter per kjøring (`NYE_ARTER`), så en ny gjest tegnes samme dag i stedet
for å stå i lista uten bilde til noen oppdager det.

For hånd, trinn for trinn:

```bash
python3 tools/fetch_plates.py --shortlist --birds birds.json --out plates/velg.html
python3 tools/fetch_plates.py --get "File:Keulemans Onze vogels 1 33.jpg" --for "Spinus spinus"
python3 tools/prepare_plates.py                       # papirtone -> rent hvitt
python3 tools/compose_branch.py --sjekk-foetter fotpunkter.png
```

Velg plansjer med **lyst papir**. En mørk, gulnet skanning lar seg ikke redde
av hvitpunkt-korreksjonen og blir grumsete på panelet. Kremgult papir finnes
ikke i palettens seks farger, så uten vask blir hele arket en gul støyflate.

Kontaktarket fra `--sjekk-foetter` viser hver fugl med et kryss der fotpunktet
er satt. Ser et feil ut, rett `fot` i artens `.json` og sett
`"kilde": "manuell"`. Da rører ingen senere kjøring det, heller ikke
`--nye-fotpunkter`.

## Malene

`maler/gren.png` er den faste grenen alle dager bruker som utgangspunkt.
Årstidsvariantene lages én gang med `compose_branch.py --lag-mal` fra en
prompt som ber modellen beholde nøyaktig samme grenform og bare bytte tre og
løv. JSON-en sier hvilke måneder malen gjelder. Bildene lages én gang og
sendes ikke til serveren for hver deploy; JSON-ene gjør det, fordi plassene i
dem hører sammen med koden.
