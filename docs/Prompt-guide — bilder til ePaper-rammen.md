# Prompt-guide — bilder til ePaper-rammen

Gjenbrukbare prompts, tilpasset skjermen. Oppdatert etter første tester: panelet
liker **tydelige, flate farger** mye bedre enn myk akvarell.

---

## Viktigst: hvordan skjermen faktisk gjengir farger

Panelet kjenner bare **6 rene farger** — svart, hvit, rød, gul, blå, grønn. Alt
annet lages ved *dithering* (blanding av fargeprikker). Det gir én avgjørende regel:

- **Flate, rene, mettede farger → skarpt og fint.** Røde, gule, blå, grønne felt,
  og rein hvit bakgrunn, gjengis rent.
- **Myke, beige, pastell- og gråtoner → «støy».** De finnes ikke i paletten, så de
  blir et spraglete prikkemønster. (Det var derfor den beige akvarell-bakgrunnen
  ble stygg på skjermen.)

Derfor: gå for stiler med **flate fargeflater, tydelige konturer og enkel, ren
bakgrunn** — tegneserie, plakat, tresnitt, risograph. Unngå bløt akvarell,
tåke, gråtone-gradienter og beige.

**Se resultatet før du sender:** kjør bildet gjennom forhåndsvisningen først, så
ser du nøyaktig hvordan panelet gjengir det (og fanger støy-bakgrunner):

```
python3 send_to_frame.py bilde.png --preview forhaandsvisning.png
```

**Velg konverteringsmetode med `--dither`:**

- **`atkinson` (standard)** — beste allrounder. Rene flater, naturlige farger,
  lett trykk-tekstur. Funker bra på både tegneserie, foto og akvarell.
- **`none` (eller `--flat`)** — djervest/mest plakataktig for flat tegneserie:
  hver flate snappes til nærmeste palett-farge (kan bli posterisert, f.eks. lys
  hud → hvit, beige → gul).
- **`bluenoise`** — alternativ for foto (naturlig korn).
- Unngå **`floyd`** (Floyd-Steinberg) på dette panelet — den overdiffunderer og
  gir støy og grønt hud-stikk.

```
python3 send_to_frame.py bilde.png                    # atkinson
python3 send_to_frame.py bilde.png --dither none      # flat/plakat
```

Ser bakgrunnen prikkete ut → be modellen om ren hvit eller en flat palett-farge,
og prøv igjen. Velg gjerne motiv/farger nær rød/gul/blå/grønn/svart/hvit.

---

## Stiler å teste (bytt inn i `[STIL]` under)

Alle disse gjengis godt på 6-fargepanelet. Kopiér én inn der malene sier `[STIL]`.

1. **Flat vektor/plakat**
   `bold flat vector illustration, poster style, clean thick outlines, large flat areas of saturated color, minimal shading, plain background`

2. **Tegneserie/cartoon**
   `modern cartoon illustration, clear bold outlines, cel shading, bright saturated colors, simple clean background`

3. **Japansk tresnitt (ukiyo-e)**
   `ukiyo-e woodblock print style, flat color areas, bold outlines, limited palette, clean composition`

4. **Risograph/silketrykk**
   `risograph print style, 3-4 bold spot colors, flat layered shapes, slight grain, clean paper background`

5. **Barnebok-illustrasjon**
   `bold children's book illustration, simple flat shapes, warm saturated colors, clear outlines, uncluttered background`

Fellesnevner som holder det rent på panelet (ta gjerne med i alle):
`bold saturated colors, flat color areas, clear outlines, simple clean background, minimal fine detail, vertical 3:4 composition`

---

## 1. Grunn-mal (daglig bilde)

Plassholdere i `{ }` fylles inn — manuelt, eller automatisk fra BirdNET (fugler)
og yr (api.met.no) (vær/årstid). Bytt `[STIL]` med en av stilene over.

```
A [STIL] of a Norwegian suburban garden at {time_of_day}.
{bird_subject}. {weather}, {season}.
Bold saturated colors (red, yellow, blue, green), flat color areas,
clear outlines, one clear focal subject, simple clean background,
minimal fine detail. Vertical 3:4 composition.
```

**Utfylt eksempel (tegneserie-stil):**

```
A modern cartoon illustration with clear bold outlines and cel shading
of a Norwegian suburban garden at dawn. A song thrush perches on a birch
branch, a great tit sits below. Light rain, early summer. Bright saturated
colors (red, yellow, blue, green), flat color areas, one clear focal
subject, simple clean sky background, minimal fine detail.
Vertical 3:4 composition.
```

**Byggeklosser å variere:**

- `{time_of_day}`: dawn, bright morning, midday, afternoon, dusk
- `{bird_subject}`: «A {bird} perches on a {branch/feeder/fence}», evt. flere fugler
- `{weather}`: clear blue sky, light rain, overcast, first snow, frost
- `{season}`: early spring, summer, autumn, winter

> Tips: be eksplisitt om **ren/enkel bakgrunn** («simple clean sky background»,
> «plain white background»). Det er bakgrunnen som oftest blir støy.

---

## 2. Komposisjons-mal (kombinere flere foto → ett motiv)

For bilder der du vil ha **personer og/eller hunden Oskar** hentet fra forskjellige
foto satt inn i samme scene.

**Verktøy:** bruk **Nano Banana (Google Gemini sitt bildemodell)** — den gjorde
det klart best i testene dine på å beholde ansikter og følge instruksjoner med
flere referansebilder. Last opp fotoene som referanser og bruk prompten under.

**Prompt (bytt `[STIL]`):**

```
Combine the people and the dog from the reference photos into one image,
in [STIL]. Place the two adults standing close together in a Norwegian
garden, the dog in front. Keep their faces and features clearly
recognizable. Bold saturated colors, flat color areas, clear outlines,
simple clean background, minimal fine detail. Vertical 3:4 composition.
```

**Tips:**
- Beskriv hvem som er hvem hvis modellen støtter det: «two adults and a
  medium-sized cream wheaten dog».
- Vil du ha en spesifikk setting, bytt ut «Norwegian garden».
- Hold bakgrunnen enkel og ren — da blir gruppa tydelig og panelet gjengir det rent.
- Kjør alltid `--preview` før du sender, så ser du hvordan ansikter og bakgrunn blir.

---

## 3. Ting å unngå (negativ-prompt ved behov)

```
watercolor, soft gradients, muted colors, beige, pastel, grey tones,
misty, photographic realism, tiny intricate details, busy cluttered
background, noise, text, watermark
```

---

## Neste steg
Når det automatiske oppsettet kommer, flettes fugler (BirdNET) og vær (yr (api.met.no))
rett inn i grunn-malens plassholdere. Velg én fast stil du liker, så blir de
daglige bildene konsistente. Komposisjons-malen er for de personlige bildene du
lager manuelt (Nano Banana).
