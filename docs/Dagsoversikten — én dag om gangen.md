# Dagsoversikten: én dag om gangen

`http://192.168.1.38:8090/dag` (`tools/dag.py`) svarer på ett spørsmål:
**hva skjedde i dag?** Når ble opptakene tatt, og hvilke fugler var i dem.

De to andre sidene svarer på noe annet, og det er derfor denne finnes:

| Side | Spørsmål |
|---|---|
| `/helse` | Virker anlegget? Batteri, dekning, siste push. |
| `/fugler` | Hva har vi hørt i det hele tatt? Arter over uker og måneder. |
| `/dag` | **Hva skjedde i dag?** Døgnet som forløp, opptak for opptak. |

## Hva sida viser

Øverst **dagvelgeren**: dagen med ukedag og dato, hvor mange opptak den
inneholder og hvilket tidsrom de dekker. Til høyre piler, datofelt og en
«i dag»-knapp.

Under den **bla-stripa** — én strek per dag fra første til siste dag i loggen,
der høyden er antall arter. Dagene uten opptak står som tomme streker, så
hullene (utedelen tom for strøm, serveren nede) er like synlige som dagene som
gikk bra. Klikk på en strek, eller bruk ←/→ på tastaturet, for å bla.

Så, for dagen som er valgt:

- **Nøkkeltall** — opptak, opptak med fugl, arter, artstreff, første og siste
  opptak.
- **«Når opptakene er tatt»** — døgnet fra 00 til 24 med ett merke per opptak:
  blått når noe ble hørt, grått når opptaket var tomt. Kameraet har sitt eget
  spor under. Hold musa over et merke for tid, nivå og arter; klikk for å hoppe
  ned til opptaket i forløpet.
- **«Hørt denne dagen»** — ett kort per art med plansjebildet sitt, antall
  opptak, tidsrommet den ble hørt i og beste sikkerhet. Klikk på en art for å
  filtrere forløpet til bare den, og få en lenke til hele historikken på
  fuglesida.
- **«Dagens forløp»** — hvert opptak på klokkeslettet sitt, med artene som
  «chips» (plansje + navn + sikkerhet), lydnivå i dBFS, og en ▶-knapp så lenge
  WAV-en ligger på serveren (21 dager). Kamerabildene er flettet inn på tiden
  sin. Tomme opptak står som «ingen fugl hørt» — også de forteller når det ble
  lyttet. Sorteringen kan snus (nyeste først / kronologisk), og to avkryssinger
  styrer hva som vises: *bare med fugl* og *vis usikre treff*.

### To terskler, ikke en glidebryter

BirdNET skriver alt fra 25 % og opp til `observations.jsonl`. Sida står på
**50 %** — det er det som telles som «hørt» i nøkkeltallene, i stripa og i
artslista. Hukes *vis usikre treff* av, faller terskelen til 25 %, og de
usikre treffene står stiplet og nedtonet. Alt regnes om, også stripa, så tallene
alltid hører sammen med det du ser.

## Deling og lenker

Alt som kan endre seg ligger i URL-hashen, som på fuglesida:

```
/dag#dato=2026-09-18&rekke=kron&bare=1&usikre=1&art=Parus%20major
```

En slik lenke åpner samme dag, samme sortering og samme filtre — og limer du
den inn i adressefeltet på en side som alt er åpen, hopper den dit.

## API-et bak

| Kall | Effekt |
|---|---|
| `GET /dag` | sida |
| `GET /api/dag` | JSON: siste dag med opptak + indeks over alle dager |
| `GET /api/dag?dato=YYYY-MM-DD` | JSON: den dagen (tom dag er et gyldig svar) |

Svaret er én dag (~10 kB) pluss indeksen — `{d, n, fugl, arter, kam}` per dag,
nok til å tegne stripa. Det er forskjellen på denne og `/api/fugler`, som sender
hele loggen på én gang fordi glidebryteren der skal svare uten å spørre
serveren. Lyd, kamerabilder og plansjer hentes fra de rutene som fantes fra før:
`/lyd/<opptak>.wav`, `/kamerabilde/<bilde>.jpg` og `/plansje/<art>.png`.

Datoen valideres mot `^\d{4}-\d{2}-\d{2}$` og brukes aldri som filsti — alt
annet faller tilbake til siste dag med opptak.

## Ta det i bruk

`dag.py` følger med deployen:

```bash
~/workspace/fugleramme/deploy/deploy.sh
```

(Undersidene `dag.py`, `fugler.py` og `helse.py` lå ikke i `deploy.sh` før nå —
de importeres av `frame_server.py` ved første kall, så uten dem svarer
`/dag`, `/fugler` og `/helse` med 500 mens resten av serveren ser frisk ut.)

Sida kan også kjøres frittstående mens du jobber med den:

```bash
python3 tools/dag.py > /tmp/dag.html     # HTML-en (henter data fra /api/dag)
python3 tools/dag.py --json 2026-09-18   # datagrunnlaget for én dag
```

## Mulige neste steg (ikke gjort ennå)

- Værdata på dagen (yr-kallet finnes alt i `render_daily_panel.py`) — «13 arter
  den dagen det regna».
- Lenke fra dagen til bildet som hang på veggen den morgenen.
- Ukesammendrag: sju dager side om side i stedet for én.
