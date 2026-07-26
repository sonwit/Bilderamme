# Webapp: galleri, send-på-nytt og generering

`frame_server.py` serverer nå også en liten webapp på
`http://192.168.1.38:8090/` (samme server/port som Siri-endepunktet). Åpne den
i nettleseren på mobil eller Mac — så lenge du er på hjemme-WiFi.

Hva den kan:

- **Galleri** over alle genererte bilder (leses fra `www/arkiv/`, nyeste først,
  med emne og tidspunkt).
- **Send til rammen** på hvert bilde — sender et tidligere bilde til skjermen på
  nytt (henter arkiv-originalen, dithrer og pusher — ingen ny Gemini-generering).
- **Lag nytt bilde** med litt mer enn bare tekst:
  - *Emne* (fritekst).
  - *Stil* — nedtrekksmeny (tegneserie/plakat/tresnitt/risograph/barnebok), samme
    panel-vennlige stiler som prompt-guiden anbefaler.
  - *Referansebilde(r)* — valgfritt: last opp inntil 3 bilder som seed. Da kjører
    modellen **bilde-til-bilde** (tegner om referansen i valgt stil). Fint til å
    lage en tegneserieversjon av et foto, eller variere et tidligere bilde.

Alt bruker de samme byggeklossene som før: samme dithering, samme portrett-format,
samme push til rammen med retries. Bare én jobb kjøres om gangen — starter du noe
mens rammen tegner, får du beskjed om å vente litt.

## Ta det i bruk

Webappen ligger i `frame_server.py`, så den følger med når du deployer serveren:

```bash
~/workspace/fugleramme/deploy/deploy.sh
```

(eller manuelt: `scp tools/frame_server.py tools/generate_daily_image.py
bruker@192.168.1.38:/opt/fugleramme/` + `sudo systemctl restart
fugleramme-frame-server`). `generate_daily_image.py` må være med, siden
seed-bilde-støtten ligger der.

Så åpner du `http://192.168.1.38:8090/` i nettleseren.

> **Tips:** lagre siden som ikon på hjemskjermen (Del → «Legg til på Hjem-skjerm»)
> på iPhone, så føles den som en app.

## API-et bak (hvis du vil bygge videre)

| Kall | Effekt |
|---|---|
| `GET /api/images` | JSON: liste over arkiverte bilder |
| `GET /arkiv/<fil>` | serverer et arkivert bilde |
| `POST /api/generate` | JSON `{emne, stil?, seeds?[]}` (seeds = data-URL/base64) → generer + send |
| `POST /api/send` | JSON `{name}` → send et arkivbilde til rammen på nytt |

Setter du `FRAME_TOKEN` i `frame_server.env`, må du åpne webappen med
`?token=din-token` i URL-en (den sender token videre på alle kall automatisk).

## Mulige neste steg (ikke gjort ennå)

- Miniatyrbilder i galleriet (nå lastes fulle PNG-er — greit for titalls bilder,
  tyngre for hundrevis).
- Slette-knapp for bilder du ikke vil beholde.
- «Regenerer med samme emne»-snarvei rett fra et galleribilde.
