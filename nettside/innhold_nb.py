# Alt som er tekst på nettsida, på norsk. En engelsk utgave er en kopi av
# denne fila med samme nøkler, ikke en kodejobb. Tallene her har kilde i
# repoet: README, tools/ og docs/. Ikke legg inn tall som ikke kan forsvares.

SPRAAK = "nb"
TITTEL = "Fugleramme"
BESKRIVELSE = "En bilderamme som viser fuglene som ble hørt i hagen i dag."

NAV = [
    ("Fuglene", "fuglene/"),
    ("Slik virker det", "slik-virker-det/"),
    ("Valgene", "valgene/"),
    ("Slik bygde jeg det", "slik-bygde-jeg-det/"),
]
GITHUB = "https://github.com/sonwit/Bilderamme"
PERSONVERN = "https://sonwit.github.io/personvern/"

FORSIDE = {
    "kicker": "Hobbyprosjekt, i drift siden sommeren 2026",
    "tittel": "En bilderamme som viser fuglene som ble hørt i hagen i dag.",
    "ingress": ("Vi har en lytter i hagen som går på solcelle. En hjemmeserver kjenner igjen "
                "artene med BirdNET og tegner dagens fugler på en gren, i stil med de gamle "
                "fuglebøkene. Bildet vises på en e-papir-ramme på veggen. Denne sida viser hva "
                "som henger der nå, og hvordan det er laget."),
    "knapp_fugler": "Se fuglene",
    "knapp_hvordan": "Slik virker det",
    "under_ramma": ("Slik henger den på veggen. Fuglene på grenen er de som ble hørt den dagen, "
                    "og en kan holde over en rad i lista for å se hvilken fugl det er."),
    "deler": "Delene",
    "deler_lenke": "Hvordan de henger sammen",
    "bilder": "Slik ser det ut",
    "bilder_lenke": "Delene og hvordan de er satt sammen",
    "fugler": "Fuglene i biblioteket",
    "fugler_lenke": "Alle artene, etter habitat",
    "grener": "Grenene",
    "grener_tekst": "Samme gren hele året. Løvet følger måneden.",
    "mer": "Mer om prosjektet",
}

# Veggsida: faste ord. Stedet er bare et ord, ikke en adresse.
VEGG = {
    "kicker": "Fugler i dag",
    "sted": "Hagen",
    "hoert": "Hørt i dag",
    "ogsaa": "Også mulige:",
    "bunn": "utedelen i hagen",
    "opptak": "opptak",
    "arter": "arter på",
    "tegnet": "tegnet",
    "forrige": "Forrige dag",
    "neste": "Neste dag",
    "dager": "Siste dager",
}
UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
MAANEDER = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
            "september", "oktober", "november", "desember"]

DELER = [
    ("Utedel", "Lytter i hagen",
     "Et lite brett med mikrofon, drevet av solcelle. Det våkner etter soloppgangen, tar opp ett minutt og sender lyden til serveren.",
     ["XIAO ESP32-S3", "C++", "I2S", "deep sleep", "solcelle"]),
    ("Hjemmeserver", "Kjenner igjen og tegner",
     "Kjører BirdNET på opptakene og setter dagens arter på en gren, i riktig størrelse og med føttene på veden.",
     ["Python", "BirdNET", "systemd", "cron", "Gemini"]),
    ("Innedel", "Viser på veggen",
     "Tar imot bildet over HTTP og tegner det på e-papiret. Bildet står til neste kommer, også uten strøm.",
     ["ESP32-S3", "e-papir 13,3\"", "HTTP", "watchdog"]),
    ("Kamera", "Ser materen",
     "En telefon i vinduet tar bilde når noe rører seg ved materen. Serveren sier hvilken fugl det er.",
     ["Kotlin", "CameraX", "Android"]),
]

FOTO = [
    ("ramme.jpg", "Ramma på veggen, 24. september 2026."),
    ("boks-ute.jpg", "Boksen ute, på gjerdestolpen."),
    ("boks-inni.jpg", "Innsiden: batteriet, lademodulen og XIAO-brettet."),
]
FOTO_BYGGET = [
    ("ramme-naer.jpg", "Ramma på veggen, 24. september 2026."),
    ("boks-ute.jpg", "Boksen ute, på gjerdestolpen."),
    ("boks-inni.jpg", "Innsiden: batteriet, lademodulen og XIAO-brettet."),
]

DOERER = [
    ("Hvordan", "Slik virker det",
     "Delene, dataflyten og lytteplanen. Hver del med hva den gjør, hvorfor og hvor koden ligger.", "slik-virker-det/"),
    ("Hvorfor", "Valgene",
     "Hva som ble valgt underveis, hva som ble prøvd, og hva som ble forkastet.", "valgene/"),
    ("Maskinvaren", "Slik bygde jeg det",
     "Delelista, strømmen ute og tidslinja fra juli til september.", "slik-bygde-jeg-det/"),
]
LES_MER = "Les mer"

# Utvalget på forsida, latinske navn.
UTVALG = ["Parus major", "Cyanistes caeruleus", "Pica pica", "Chloris chloris",
          "Pyrrhula pyrrhula", "Dendrocopos major", "Ardea cinerea", "Strix aluco"]

GRENER = [
    ("gren-vaar", "Gren med knopper", "April og mai"),
    ("gren-sommer", "Bjørk om sommeren", "Juni til august"),
    ("gren-host", "Bjørk om høsten", "September og oktober"),
    ("gren-vinter", "Snødekt grankvist", "November til mars"),
]

HABITAT = {"tre": "Tre", "vaatmark": "Våtmark", "bakke": "Bakke", "luft": "Luft"}

FUGLENE = {
    "kicker": "Biblioteket",
    "tittel": "Alle fuglene som er hørt i hagen",
    "ingress": ("Hver art som er hørt i hagen har fått en tegning etter en gammel plansje. Her står de i "
                "samme innbyrdes størrelse som på veggen, skalert etter kroppslengde. Skalaen er komprimert, "
                "ellers hadde gråhegra tatt hele sida. Klikk på en fugl for å se forelegget."),
    "art": "art", "arter": "arter",
    "cm": "cm",
}

ART = {
    "lengde": "Lengde", "lengde_tekst": "{cm} cm, nebb til halespiss",
    "habitat": "Habitat",
    "overvintrer": "Overvintrer", "ja": "Ja", "nei": "Nei, trekker",
    "paa_grenen": "På grenen",
    "paa_grenen_tekst": "Skala {skala} av rødvingetrosten. {plass}",
    "plass_liten": "Får den tynne kvisten øverst.",
    "plass_stor": "Får den tykke greina nederst.",
    "plass_midt": "Får en av greinene i midten.",
    "forelegg": "Forelegg",
    "forelegg_tekst": "{kunstner}. Public domain, via Wikimedia Commons.",
    "se_plansjen": "Se plansjen",
    "tegnet": "Tegnet",
    "tegnet_tekst": "Én gang, etter plansjen{varianter}. Fotpunktet er målt så føttene lander på veden.",
    "var_fly": ", sittende og flygende",
    "var_klatre": ", sittende, flygende og klatrende",
    "i_lufta": "I lufta",
    "klatrende": "Klatrende",
    "tilbake": "Alle fuglene",
    "repo": "Biblioteket i repoet",
}

HVORDAN = {
    "kicker": "Slik virker det",
    "tittel": "Delene, og hvordan de henger sammen",
    "ingress": ("Utedelen sender lyd, serveren gjør jobben og rammen tegner det den får. Under står hver del "
                "med hva den gjør, hvorfor den er som den er og hvor koden ligger."),
    "delene": "Delene",
    "hva": "Hva", "hvorfor": "Hvorfor", "kode": "Hvor i koden",
    "doegn": "Døgnet på serveren",
    "plan": "Lytteplanen",
    "plan_tekst": "Regnet ut av samme kode som styrer utedelen",
    "trapper": "Trappes ned med batteriet",
    "trapper_tekst": "I finvinduet, og resten av dagen. Utedelen skal overleve november.",
    "over": "over", "under": "under",
    "farger": "Fargene på panelet",
    "farger_tekst": "Panelet har seks farger. Alt på veggen er tegnet i dem.",
    "farger_avsnitt": ("En farge som ikke finnes i paletten må lages med dithering, og dithret tekst blir "
                       "vanskelig å lese. Derfor er tekst, streker og puter rene palettfarger. Bare plansjene dithres."),
    "diagram": [
        ("Utedel", "XIAO ESP32-S3 · INMP441 · solcelle"),
        ("Hjemmeserver", "Python · BirdNET · systemd · cron"),
        ("Innedel", "ESP32-S3 · e-papir 1200×1600"),
        ("Kamera", "Android · Kotlin · CameraX"),
    ],
    "piler": {
        "upload": "POST /upload · 60 s WAV + helse-JSON",
        "config": "GET /config · lytteplanen tilbake",
        "display": "POST /display · 960 000 byte",
        "bilde": "POST /bilde · JPEG + meta",
        "vaer": "vær",
        "gemini": "én fugl om gangen · tolkning av bilder",
        "rammen": ["Rammen henter aldri noe selv.", "Uten strøm viser den det den sist fikk."],
    },
    "doegn_merker": [(7.12, "07:07 sida tegnes"), (9.62, "09:37 igjen"), (16.0, "16:00 dagen så langt"), (22.0, "22:00 statistikk")],
    "doegn_tekst": ["Lytting hvert 10. min i finvinduet", "Hvert 20. min til 21", "Vakta hvert kvarter, hele døgnet"],
    "sol_tekst": ["Soloppgang", "Finvindu: 1 t før til 4 t etter, én økt hvert 10. minutt", "I dag"],
}

KOMPONENTER = [
    ("Utedel", "firmware/outdoor_sensor/",
     "Tar opp ett minutt rett i PSRAM med radioen av, kobler til, synker klokka, laster opp og sover. Deep sleep er 14 µA.",
     "Den første utgaven på Raspberry Pi trakk 450 mA i tomgang og døde på solcelle. Vi trengte et brett som kan sove mellom øktene.",
     "firmware/README.md"),
    ("Hjemmeserver", "tools/",
     "Tar imot lyd og bilder, kjører BirdNET, regner lytteplanen, komponerer sida, dithrer og pusher. Websidene er ren standardbibliotek.",
     "Alt tungt skjer der strømmen er billig og loggene er lette å lese. Utedelen slipper å holde radioen på mens analysen kjører.",
     "tools/README.md"),
    ("Innedel", "firmware/indoor_frame/",
     "En HTTP-server som tar imot 960 000 byte og skyver dem til panelet. Watchdog og WiFi-gjenoppretting, ellers ingenting.",
     "Rammen skal ikke trenge klokke, plan eller nett. Den viser det den sist fikk, også uten strøm.",
     "firmware/README.md"),
    ("Kamera", "kamera-app/",
     "Overvåker hagen på 1x, tar telebilde ved materen når noe rører seg, klipper ut og sender. Serveren spør modellen hva som står der.",
     "Mikrofonen hører ikke alt. To troster på plenen ble aldri hørt, og det var starten på kameraet.",
     "kamera-app/README.md"),
]

FARGER = [("Svart", "#000000"), ("Hvit", "#ffffff"), ("Rød", "#c8102e"),
          ("Gul", "#f2c300"), ("Blå", "#1d4e9f"), ("Grønn", "#2e8b3d")]

VALGENE = {
    "kicker": "Valgene",
    "tittel": "Valgene som ble tatt underveis",
    "ingress": ("Det meste her ble ikke bestemt på forhånd. Vi prøvde noe, målte, og byttet ut det som ikke "
                "holdt. Hvert valg står med problemet, det som ble prøvd, det som ble målt og det som ble valgt."),
    "problemet": "Problemet", "proevd": "Prøvd", "maalt": "Målt", "valgt": "Valgt",
    "forkastet": "Prøvd og forkastet",
}
VALG = [
    ("Fast oppsett, ikke fritt bilde",
     "Et fritt AI-bilde hver dag var pent, uforutsigbart, og sa lite om hva som faktisk ble hørt.",
     "Fritt bilde av dagens fugl, juli til august 2026.",
     "Veggen viste en fugl. Ikke hvilke, ikke når, ikke hvor sikkert.",
     "Samme oppsett hver dag: artene med navn, klokkeslett og sikkerhet. Det frie bildet lever som reserve."),
    ("Koden setter fuglene på grenen",
     "Teksten trenger et tomt felt til venstre. Modellen bestemte selv hvor den tegnet.",
     "Be om tomt felt i klartekst, tre ganger. Gi den en ferdig gren som referanse.",
     "0,1 % blekk i tekstsonen ett forsøk, 14,8 % det neste. Med grenen som mal: 20,6 %, verre enn uten.",
     "Modellen tegner én fugl om gangen. Koden setter dem på grenen. Tekstsonen måles, og ureint forkastes."),
    ("Bare palettfarger på sida",
     "Panelet har seks farger. Alt annet må lages med prikker, og dithret tekst blir vanskelig å lese.",
     "En halvgjennomsiktig hvit pute bak teksten, for lesbarhet.",
     "En grumsete flekk. Fargen finnes ikke, så dithringen gjettet den.",
     "Alt tegnes i de seks fargene. Ren hvit pute når den trengs; den dithres ikke i det hele tatt."),
    ("Stedsfilter og blokkliste",
     "BirdNET foreslår arter som finnes i Norge, men ikke i en villahage.",
     "Posisjon og dato som filter, som BirdNET anbefaler.",
     "Myrrikse i 80 opptak fram til 19. september, opptil 0,91 i sikkerhet.",
     "En blokkliste for de klassiske feilene. De tegnes aldri, men står i fotnoten så det er synlig at de ble hørt."),
    ("Lytteplanen følger sola og batteriet",
     "En fast plan treffer morgenkoret i juni og bekmørke i desember.",
     "Fast morgenrunde fra klokka fire, som i firmwaren.",
     "Fem timers forskjell i soloppgang gjennom året. 70 % av de sikre funnene hang på ett enkelt minutt.",
     "Soloppgangen regnes ut på serveren, uten nettkall. Finvindu rundt den, tettere sampling, trappet ned når spenningen faller."),
    ("Dyr modell til det som kjører sjelden",
     "Regningen vokste uten at noen så hvor.",
     "Kameraet på Raspberry Pi med en tenkende modell i 1280 px, hvert bilde.",
     "1559 bilder på åtte dager var 80 til 90 % av forbruket. Halvparten uten fugl.",
     "Beste modell til nye arter, én gang. Billigste uten tenking i 768 px til kameraet, med tak per time og pause etter 429."),
    ("Vakta ser etter stillhet",
     "Utedelen lå femten timer i bootloader. Ingen merket det.",
     "En vakt som reagerte på nye data.",
     "Ingen nye filer, ingen reaksjon. En vakt som bare ser på nye data er blind for at dataene har sluttet å komme.",
     "Vakta ser etter det som ikke skjer, og er ellers helt stille. Én melding når noe er galt."),
    ("07:07, ikke 07:00",
     "Vær-API-et er mest overbelastet på hel time.",
     "Cron på 07:00.",
     "To dagers 503-stopp i juli 2026.",
     "Sju over sju. Og været stopper aldri sida: tre forsøk, så tegnes den uten værreferanse."),
]
FORKASTET = [
    ("Utedel v1 på Raspberry Pi 3 B",
     "Trakk 450 mA i tomgang, fikk undervoltage på solcelle og døde 28. juli 2026. Mikrofonen og designvalgene ble med videre."),
    ("Modellen komponerer hele plansjen",
     "Den tegnet sin egen gren midt på sida uansett hva referansen sa. Koden tok over komposisjonen."),
    ("Kamera på Raspberry Pi med HQ-kamera",
     "Virket, men kostet for mye i modellkall. Telefonen med telelinse tok over i september 2026."),
    ("Plansjer fra en 3D-modell i Blender",
     "For arter uten brukbar plansje. Streken virket, fjærdrakten gjorde det ikke, og hver art kostet mer modellering enn den var verdt. Lagt dødt 20. september 2026."),
]

BYGGET = {
    "kicker": "Slik bygde jeg det",
    "tittel": "Delene, strømmen og tidslinja",
    "ingress": "Alt er vanlige deler. Det som tok tid var strømmen ute og fargene inne.",
    "deleliste": "Delelista",
    "stroem": "Strømmen ute",
    "stroem_avsnitt": ("Solcella var netto positiv i august med 24 økter om dagen. Planen trappes ned av seg selv "
                       "når spenningen faller. Målet er at boksen skal overleve november."),
    "tidslinje": "Tidslinja",
    "verktoey": "Verktøyene",
    "verktoey_avsnitt": ("Mye av koden er skrevet sammen med Claude Code. Det som ble målt, valgt og forkastet "
                         "står på Valgene-sida. Repoet har en AGENTS.md med konvensjonene, så en agent jobber "
                         "etter de samme reglene som en kollega ville gjort."),
}
DELELISTE = [
    ("Innedel", ["Waveshare ESP32-S3-ePaper-13.3E6, 13,3\" Spectra 6, seks farger, 16 MB PSRAM", "IKEA RÖDALM-ramme, 30×40 cm"]),
    ("Utedel", ["Seeed XIAO ESP32-S3, 8 MB PSRAM", "INMP441 I2S-mikrofon, skumgummi mot vind",
                "Waveshare Solar Power Manager (D), MPPT-lading", "3,7 V LiPo på 10 Ah", "Solcellepanel, 6 til 24 V inn"]),
    ("Hjemmeserver", ["En gammel PC med Linux, Python 3.12, to venv-er", "systemd for tjenestene, cron for døgnet"]),
    ("Kamera", ["Android-telefon med telelinse i vinduet", "Før: Raspberry Pi 3 B med HQ-kamera, parkert"]),
]
STROEM = [("Deep sleep mellom øktene", "14 µA"),
          ("Opptak og opplasting, noen titalls sekunder", "~100 mA"),
          ("Raspberry Pi 3 B i tomgang, til sammenligning", "~450 mA")]
TIDSLINJE = [
    ("21. juli 2026", "Første bilde på skjermen, sendt fra Macen."),
    ("24. juli", "Daglig push fra cron på hjemmeserveren."),
    ("28. juli", "Utedel v1 på Raspberry Pi dør av strømmangel."),
    ("4. august", "Utedel v2 på XIAO ESP32-S3 i drift, soldrevet."),
    ("28. august", "Fuglesida tar over for det frie AI-bildet."),
    ("13. september", "Kostnadsbremsene på kameraanalysen."),
    ("September", "Telefonen som kamera. Repoet gjøres klart for å bli åpent."),
]

BUNN = {
    "laget": "Laget av Sondre Wittek, frontend-utvikler. Alt fra firmware til denne sida ligger åpent på GitHub.",
    "takk": ("Plansjene er public domain fra Wikimedia Commons; kunstneren står ved hver fugl. "
             "Artsgjenkjenning: BirdNET. Vær: MET Norge. Koden er MIT-lisensiert."),
    "github": "Koden på GitHub",
    "personvern": "Personvernerklæring",
    "sporing": "Sida bruker ingen sporing.",
    "hopp": "Til innholdet",
}
