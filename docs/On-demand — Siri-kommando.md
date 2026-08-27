# On-demand: «Hei Siri, tegn X på fuglerammen»

Utover det daglige automatiske bildet kan du be om et bilde med **fritt emne**
når som helst, og få det tegnet på rammen med en gang. Dette gjøres med en liten
HTTP-server på hjemmeserveren (`frame_server.py`) + en Siri-snarvei.

Samme endepunkt funker også fra Home Assistant, IFTTT eller en nettleser — Siri
er bare den enkleste veien på Apple-utstyr, og krever ingen tredjeparts-tjeneste.

```
[iPhone/Mac]  "Hei Siri, tegn på fuglerammen"
   → Siri: "Hva vil du tegne?"  → du sier f.eks. "en ridderborg med en drage"
   → Snarvei POST-er teksten til  http://192.168.1.38:8090/generate
        [Hjemmeserver: frame_server.py]
          → bygger prompt rundt emnet (samme panel-vennlige stil som daglig)
          → Gemini genererer → dither → skriv frame.bin
          → push til rammen (fugleramme.local)
             [ESP32-rammen tegner bildet, spiller et "pling" når det lander]
```

Siri svarer «Tegner et bilde av …, klart om ett minutt» med en gang — selve
jobben kjører i bakgrunnen på serveren, så du slipper å stå og vente.

---

## Del 1 — Sett opp serveren (én gang)

Filene ligger i repoet: `tools/frame_server.py`,
`deploy/fugleramme-frame-server.service`, `deploy/frame_server.env.example`.

**1. Kopier filene til hjemmeserveren** (fra Macen):
```bash
scp tools/frame_server.py bruker@192.168.1.38:/opt/fugleramme/
scp deploy/fugleramme-frame-server.service bruker@192.168.1.38:/tmp/
scp deploy/frame_server.env.example bruker@192.168.1.38:/opt/fugleramme/frame_server.env
```
(`frame_server.py` bruker `generate_daily_image.py` og `push_to_frame.py` som
allerede ligger i `/opt/fugleramme/` — sørg for at de er den nyeste versjonen.)

**2. Fyll inn hemmeligheter** (på serveren, `ssh` inn):
```bash
nano /opt/fugleramme/frame_server.env
```
Sett minst `GEMINI_API_KEY` (samme nøkkel som det daglige scriptet bruker) og
`FRAME_HOST=fugleramme.local`. Lagre. (Navn, ikke IP — rammen får adressen fra
DHCP og har byttet den før. Scriptet slår opp `.local` over mDNS selv.)

**3. Test at den starter** (på serveren):
```bash
cd /opt/fugleramme
set -a && . frame_server.env && set +a      # last inn env i skallet
venv/bin/python3 frame_server.py
```
Du skal se `Fugleramme frame-server lytter på :8090 ...`. La den stå, og fra
**Macen** i et nytt terminalvindu:
```bash
curl -X POST --data "en rød hytte ved en fjord" http://192.168.1.38:8090/generate
```
Svar: `Tegner et bilde av en rød hytte ved en fjord ...`, og rammen skal
oppdatere seg etter ~1 minutt. Stopp testserveren med `Ctrl+C` når det virker.

**4. Kjør den permanent som tjeneste** (på serveren, starter automatisk ved boot
og restarter hvis den krasjer):
```bash
sudo mv /tmp/fugleramme-frame-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fugleramme-frame-server
systemctl status fugleramme-frame-server          # skal vise "active (running)"
journalctl -u fugleramme-frame-server -f          # live-logg, Ctrl+C for å gå ut
```

> Tjenestefila peker på `venv/bin/python3` og leser `/opt/fugleramme/frame_server.env`.
> Kjører du `generate_daily_image.py` med en annen Python/venv, juster `ExecStart`
> tilsvarende.

---

## Del 2 — Lag Siri-snarveien (én gang, på iPhone eller Mac)

1. Åpne **Snarveier**-appen (Shortcuts). Trykk **+** for ny snarvei.
2. Legg til handling **«Be om inndata»** (Ask for Input):
   - Type: **Tekst**
   - Spørsmål: `Hva vil du tegne?`
3. Legg til handling **«Hent innhold fra URL»** (Get Contents of URL):
   - URL: `http://192.168.1.38:8090/generate`
   - Trykk på pila for å utvide, sett **Metode: POST**
   - **Forespørselstekst (Request Body): Skjema** (Form). Nyere versjoner av
     Snarveier tilbyr bare JSON / Fil / Skjema her — velg **Skjema**.
   - Trykk **Legg til nytt felt → Tekst**. Sett **Nøkkel (Key): `emne`** og
     **Verdi (Value): variabelen «Oppgitt inndata»** (Provided Input) fra steg 2
     (den dukker opp som forslag over tastaturet).
   - *(JSON funker også hvis du heller vil: felt `emne` = Oppgitt inndata.
     Serveren takler begge, pluss ren tekst fra curl.)*
4. *(Valgfritt)* Legg til handling **«Vis varsel»** eller **«Snakk tekst»** med
   variabelen **«Innhold fra URL»** (Contents of URL) — da leser Siri opp
   serverens svar («Tegner et bilde av …»).
5. Gi snarveien et navn, f.eks. **«Fugleramme»** (navnet blir Siri-frasen).
6. Ferdig. Si **«Hei Siri, Fugleramme»** → Siri spør «Hva vil du tegne?» → svar,
   og bildet kommer på skjermen om ~1 minutt.

> **Tips — enda kjappere:** vil du si alt i én setning uten mellomsteget, lag
> flere snarveier med faste emner (f.eks. «Fugleramme katt» som POST-er «en
> katt»). Men varianten over med «Be om inndata» er den fleksible «tegn hva som
> helst»-kommandoen.

### Viktig om nettverk
«Hent innhold fra URL» treffer `192.168.1.38`, som bare er nåbar på
hjemme-WiFi. Utenfor hjemmet virker ikke kommandoen med mindre du setter opp
fjerntilgang (f.eks. Tailscale eller VPN inn til hjemmenettet). For normal
bruk hjemme trenger du ingenting ekstra.

---

## Endepunkt-referanse (for HA / IFTTT / curl)

| Kall | Effekt |
|---|---|
| `POST /generate` med body = emnet | Tegn et bilde av emnet (anbefalt — ingen URL-koding) |
| `GET /generate?emne=<tekst>` | Samme, men emnet i URL-en (husk URL-koding av mellomrom/æøå) |
| `GET` eller `POST /daily` | Generer dagens standardbilde (som cron) |
| `GET /status` | Hva serveren jobber med akkurat nå |

Setter du `FRAME_TOKEN` i env-fila, må alle kall ha `?token=<token>` eller
header `X-Token: <token>` — en enkel sperre mot at tilfeldige enheter på nettet
trigger rammen.

**Home Assistant-eksempel** (`rest_command` i `configuration.yaml`):
```yaml
rest_command:
  fugleramme_tegn:
    url: "http://192.168.1.38:8090/generate"
    method: POST
    payload: "{{ emne }}"
    content_type: "text/plain; charset=utf-8"
```
Kall den fra en HA Assist-setning som fanger `{emne}` som fritekst.
