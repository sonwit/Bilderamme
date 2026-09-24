# All the text on the site, in English. Same keys as innhold_nb.py; the
# Norwegian file is the original, this one follows it. The numbers here have a
# source in the repo: README, tools/ and docs/. Do not add numbers that cannot
# be defended.

SPRAAK = "en"
SPRAAK_NAVN = "English"
SPRAAK_LABEL = "Language"
ROT = "en/"                       # where this language lives, relative to the site root
TITTEL = "Fugleramme"
BESKRIVELSE = "A picture frame that shows the birds heard in the garden today."

# The page paths in this language. bygg.py uses these to link between pages
# and to find the same page in the other language.
STIER = {"fuglene": "birds/", "hvordan": "parts/", "bygget": "build-log/", "dag": "day/"}
NAV = [
    ("The birds", STIER["fuglene"]),
    ("The parts", STIER["hvordan"]),
    ("Build log", STIER["bygget"]),
]
GITHUB = "https://github.com/sonwit/Bilderamme"
PROFIL = "https://github.com/sonwit"
PERSONVERN = "https://sonwit.github.io/personvern/"

FORSIDE = {
    "kicker": "Hobby project, running since the summer of 2026",
    "tittel": "A picture frame that shows the birds heard in the garden today.",
    "ingress": ("We have a solar-powered listener in the garden. A home server identifies the "
                "species with BirdNET and draws the day's birds on a branch, in the style of the "
                "old bird books. The picture is shown on an e-paper frame on the wall. This page "
                "shows what hangs there now, and how it is made."),
    "knapp_fugler": "See the birds",
    "knapp_hvordan": "How it works",
    "under_ramma": ("This is how it hangs on the wall. The birds on the branch are the ones heard "
                    "that day. Hover over a row in the list to see which bird it is."),
    "deler": "The parts",
    "deler_lenke": "How they fit together",
    "bilder": "What it looks like",
    "bilder_lenke": "Build log: the parts and how they were put together",
    "fugler": "The birds in the library",
    "fugler_lenke": "All species, by habitat",
    "grener": "The branches",
    "grener_tekst": "The same branch all year. The leaves follow the month.",
    "mer": "More about the project",
}

# The wall page: fixed words. The place is just a word, not an address.
VEGG = {
    "kicker": "Birds today",
    "sted": "The garden",
    "hoert": "Heard today",
    "ogsaa": "Also possible:",
    "bunn": "the outdoor unit in the garden",
    "opptak": "recordings",
    "arter": "species in",
    "tegnet": "drawn",
    "forrige": "Previous day",
    "neste": "Next day",
    "dager": "Recent days",
    "idag": "Today",
}
UKEDAGER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAANEDER = ["January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December"]
DATO = "{d} {m} {y}"              # 24 September 2026
DAG_KORT = "{u} {d}"              # Thu 24, in the strip of recent days
DESIMAL = "."

# The day files are written in Norwegian by the server. These map the parts
# that are words, not numbers. Anything not listed is shown as it is.
NAVNFELT = "engelsk"              # the field in plates/arter.json
NAVN = {                          # species that have no entry there
    "gallinago gallinago": "Common snipe",
    "pica pica": "Eurasian magpie",
    "porzana porzana": "Spotted crake",
    "sitta europaea": "Eurasian nuthatch",
    "spinus spinus": "Eurasian siskin",
    "strix aluco": "Tawny owl",
    "turdus iliacus": "Redwing",
    "corvus monedula": "Eurasian jackdaw",
    "lophophanes cristatus": "Crested tit",
    "phylloscopus trochilus": "Willow warbler",
    "erithacus rubecula": "European robin",
    "botaurus stellaris": "Eurasian bittern",
    "fulica atra": "Eurasian coot",
    "cygnus cygnus": "Whooper swan",
    "columba palumbus": "Common wood pigeon",
    "anas platyrhynchos": "Mallard",
}
VAER = {"Overskyet": "Overcast", "Delvis skyet": "Partly cloudy", "Lettskyet": "Fair",
        "Klarvær": "Clear", "Skyet": "Cloudy", "Regn": "Rain", "Yr": "Drizzle",
        "Regnbyger": "Showers", "Sludd": "Sleet", "Snø": "Snow", "Tåke": "Fog"}
BELEGG = {"ggr": ("once", "{n} times"), "økter": ("{n} session", "{n} sessions")}   # «1 ggr» -> «once»
KUNSTNER_FRA = "from “{t}”"
MENY = {"aapne": "Menu", "lukk": "Close the menu"}

DELER = [
    ("Outdoor unit", "Listens in the garden",
     "A small board with a microphone, powered by a solar panel. It wakes after sunrise, records one minute and sends the audio to the server.",
     ["XIAO ESP32-S3", "C++", "I2S", "deep sleep", "solar panel"]),
    ("Home server", "Identifies and draws",
     "Runs BirdNET on the recordings and puts the day's species on a branch, at the right size and with their feet on the wood.",
     ["Python", "BirdNET", "systemd", "cron", "Gemini"]),
    ("Indoor unit", "Shows it on the wall",
     "Receives the image over HTTP and draws it on the e-paper. The image stays until the next one arrives, even without power.",
     ["ESP32-S3", "e-paper 13.3\"", "HTTP", "watchdog"]),
    ("Camera", "Watches the feeder",
     "A phone in the window takes a picture when something moves at the feeder. The server says which bird it is.",
     ["Kotlin", "CameraX", "Android"]),
]

FOTO = [
    ("ramme.jpg", "The frame on the wall, 24 September 2026."),
    ("boks-ute.jpg", "The box outside, on the fence post."),
    ("boks-inni.jpg", "Inside: the battery, the charging module and the XIAO board."),
]
FOTO_BYGGET = [
    ("ramme-naer.jpg", "The frame on the wall, 24 September 2026."),
    ("boks-ute.jpg", "The box outside, on the fence post."),
    ("boks-inni.jpg", "Inside: the battery, the charging module and the XIAO board."),
]

DOERER = [
    ("How", "The parts",
     "The parts, the data flow and the listening plan. Each part with what it does, why, and where the code is.", STIER["hvordan"]),
    ("The hardware", "Build log",
     "The parts list, the power outside and the timeline from July to September.", STIER["bygget"]),
    ("Why", "The choices",
     "What was chosen along the way, what was tried, and what was dropped. A section of the build log.", STIER["bygget"] + "#valgene"),
]
LES_MER = "Read more"

# The selection on the front page, scientific names.
UTVALG = ["Parus major", "Cyanistes caeruleus", "Pica pica", "Chloris chloris",
          "Pyrrhula pyrrhula", "Dendrocopos major", "Ardea cinerea", "Strix aluco"]

GRENER = [
    ("gren-vaar", "Branch with buds", "April and May"),
    ("gren-sommer", "Birch in summer", "June to August"),
    ("gren-host", "Birch in autumn", "September and October"),
    ("gren-vinter", "Snow-covered spruce twig", "November to March"),
]

HABITAT = {"tre": "Trees", "vaatmark": "Wetland", "bakke": "Ground", "luft": "Air"}

FUGLENE = {
    "kicker": "The library",
    "tittel": "All the birds heard in the garden",
    "ingress": ("Every species heard in the garden has a drawing made after an old plate. Here they stand "
                "at the same relative size as on the wall, scaled by body length. The scale is compressed, "
                "otherwise the grey heron would take the whole page. Click a bird to see the original plate."),
    "art": "species", "arter": "species",
    "cm": "cm",
}

ART = {
    "lengde": "Length", "lengde_tekst": "{cm} cm, bill to tail tip",
    "habitat": "Habitat",
    "overvintrer": "Winters here", "ja": "Yes", "nei": "No, migrates",
    "paa_grenen": "On the branch",
    "paa_grenen_tekst": "Scale {skala} of the redwing. {plass}",
    "plass_liten": "Gets the thin twig at the top.",
    "plass_stor": "Gets the thick branch at the bottom.",
    "plass_midt": "Gets one of the branches in the middle.",
    "forelegg": "Source plate",
    "forelegg_tekst": "{kunstner}. Public domain, via Wikimedia Commons.",
    "se_plansjen": "See the plate",
    "tegnet": "Drawn",
    "tegnet_tekst": "Once, after the plate{varianter}. The foot point is measured so the feet land on the wood.",
    "var_fly": ", perched and in flight",
    "var_klatre": ", perched, in flight and climbing",
    "i_lufta": "In flight",
    "klatrende": "Climbing",
    "tilbake": "All the birds",
    "repo": "The library in the repo",
}

HVORDAN = {
    "kicker": "The parts",
    "tittel": "How they fit together",
    "ingress": ("The outdoor unit sends audio, the server does the work, and the frame draws what it gets. "
                "Below is each part with what it does, why it is the way it is, and where the code is."),
    "delene": "The parts",
    "hva": "What", "hvorfor": "Why", "kode": "Where in the code",
    "doegn": "A day on the server",
    "plan": "The listening plan",
    "plan_tekst": "Calculated by the same code that runs the outdoor unit",
    "trapper": "Steps down with the battery",
    "trapper_tekst": "In the fine window, and the rest of the day. The outdoor unit has to survive November.",
    "over": "above", "under": "below",
    "farger": "The colours of the panel",
    "farger_tekst": "The panel has six colours. Everything on the wall is drawn in them.",
    "farger_avsnitt": ("A colour that is not in the palette has to be made with dithering, and dithered text "
                       "is hard to read. So text, lines and pads are pure palette colours. Only the plates are dithered."),
    "diagram": [
        ("Outdoor unit", "XIAO ESP32-S3 · INMP441 · solar panel"),
        ("Home server", "Python · BirdNET · systemd · cron"),
        ("Indoor unit", "ESP32-S3 · e-paper 1200×1600"),
        ("Camera", "Android · Kotlin · CameraX"),
    ],
    "piler": {
        "upload": ["POST /upload", "60 s WAV + health JSON"],
        "config": ["GET /config", "the listening plan back"],
        "display": ["POST /display", "960,000 bytes"],
        "bilde": ["POST /bilde", "JPEG + metadata"],
        "vaer": "weather",
        "gemini": "birds and images",
        "rammen": ["The frame never fetches anything itself.", "Without power it shows what it last got."],
    },
    "doegn_merker": [(7.12, "07:07 page drawn"), (9.62, "09:37 again"), (16.0, "16:00 the day so far"), (22.0, "22:00 statistics")],
    "doegn_tekst": ["Listening every 10 min in the fine window", "Every 20 min until 21:00", "The watch every quarter hour, all day"],
    "sol_tekst": ["Sunrise", "Fine window: 1 h before to 4 h after, one session every 10 minutes", "Today"],
}

KOMPONENTER = [
    ("Outdoor unit", "firmware/outdoor_sensor/",
     "Records one minute straight into PSRAM with the radio off, connects, syncs the clock, uploads and sleeps. Deep sleep is 14 µA.",
     "The first version on a Raspberry Pi drew 450 mA idle and died on solar power. We needed a board that can sleep between sessions.",
     "firmware/README.md"),
    ("Home server", "tools/",
     "Receives audio and images, runs BirdNET, calculates the listening plan, composes the page, dithers and pushes. The web pages are pure standard library.",
     "Everything heavy happens where power is cheap and the logs are easy to read. The outdoor unit does not have to keep the radio on while the analysis runs.",
     "tools/README.md"),
    ("Indoor unit", "firmware/indoor_frame/",
     "An HTTP server that receives 960,000 bytes and pushes them to the panel. Watchdog and WiFi recovery, nothing else.",
     "The frame should not need a clock, a plan or the internet. It shows what it last got, even without power.",
     "firmware/README.md"),
    ("Camera", "kamera-app/",
     "Watches the garden at 1x, takes a telephoto picture at the feeder when something moves, crops it and sends it. The server asks the model what is there.",
     "The microphone does not hear everything. Two thrushes on the lawn were never heard, and that was the start of the camera.",
     "kamera-app/README.md"),
]

FARGER = [("Black", "#000000"), ("White", "#ffffff"), ("Red", "#c8102e"),
          ("Yellow", "#f2c300"), ("Blue", "#1d4e9f"), ("Green", "#2e8b3d")]

VALGENE = {
    "kicker": "The choices",
    "tittel": "The choices along the way",
    "ingress": ("Most of this was not decided in advance. We tried something, measured, and replaced what did "
                "not hold up. Each choice is listed with the problem, what was tried, what was measured and what was chosen."),
    "problemet": "The problem", "proevd": "Tried", "maalt": "Measured", "valgt": "Chosen",
    "forkastet": "Tried and dropped",
}
VALG = [
    ("A fixed layout, not a free image",
     "A free AI image every day was pretty, unpredictable, and said little about what was actually heard.",
     "A free image of the bird of the day, July to August 2026.",
     "The wall showed a bird. Not which ones, not when, not how certain.",
     "The same layout every day: the species with names, times and confidence. The free image lives on as a fallback."),
    ("The code puts the birds on the branch",
     "The text needs an empty area on the left. The model decided for itself where it drew.",
     "Asking for an empty area in plain words, three times. Giving it a finished branch as reference.",
     "0.1 % ink in the text zone on one attempt, 14.8 % on the next. With the branch as a template: 20.6 %, worse than without.",
     "The model draws one bird at a time. The code puts them on the branch. The text zone is measured, and anything unclean is rejected."),
    ("Only palette colours on the page",
     "The panel has six colours. Everything else has to be made with dots, and dithered text is hard to read.",
     "A semi-transparent white pad behind the text, for readability.",
     "A muddy blotch. The colour does not exist, so the dithering guessed it.",
     "Everything is drawn in the six colours. A pure white pad when needed; it is not dithered at all."),
    ("Location filter and block list",
     "BirdNET suggests species that exist in Norway, but not in a suburban garden.",
     "Location and date as a filter, as BirdNET recommends.",
     "Spotted crake in 80 recordings up to 19 September, with confidence up to 0.91.",
     "A block list for the classic mistakes. They are never drawn, but they appear in the footnote so it is visible that they were heard."),
    ("The listening plan follows the sun and the battery",
     "A fixed plan hits the dawn chorus in June and pitch darkness in December.",
     "A fixed morning round from four o'clock, as in the firmware.",
     "Five hours' difference in sunrise through the year. 70 % of the confident detections hung on a single minute.",
     "Sunrise is calculated on the server, without network calls. A fine window around it, denser sampling, stepped down when the voltage drops."),
    ("An expensive model for what runs rarely",
     "The bill grew without anyone seeing where.",
     "The camera on a Raspberry Pi with a thinking model at 1280 px, every picture.",
     "1,559 pictures in eight days were 80 to 90 % of the spend. Half of them without a bird.",
     "The best model for new species, once. The cheapest without thinking at 768 px for the camera, with a cap per hour and a pause after 429."),
    ("The watch looks for silence",
     "The outdoor unit sat in the bootloader for fifteen hours. Nobody noticed.",
     "A watch that reacted to new data.",
     "No new files, no reaction. A watch that only looks at new data is blind to the data having stopped.",
     "The watch looks for what does not happen, and is otherwise completely quiet. One message when something is wrong."),
    ("07:07, not 07:00",
     "The weather API is most overloaded on the hour.",
     "Cron at 07:00.",
     "Two days of 503 outages in July 2026.",
     "Seven past seven. And the weather never stops the page: three attempts, then it is drawn without a weather reference."),
]
FORKASTET = [
    ("Outdoor unit v1 on a Raspberry Pi 3 B",
     "Drew 450 mA idle, got undervoltage on solar power and died on 28 July 2026. The microphone and the design choices carried on."),
    ("The model composes the whole plate",
     "It drew its own branch in the middle of the page no matter what the reference said. The code took over the composition."),
    ("Camera on a Raspberry Pi with the HQ camera",
     "Worked, but cost too much in model calls. The phone with a telephoto lens took over in September 2026."),
    ("Plates from a 3D model in Blender",
     "For species without a usable plate. The line work worked, the plumage did not, and each species cost more modelling than it was worth. Dropped on 20 September 2026."),
]

BYGGET = {
    "kicker": "Build log",
    "tittel": "The parts list, the power, the timeline and the choices along the way",
    "ingress": "All ordinary parts. What took time was the power outside and the colours inside.",
    "deleliste": "The parts list",
    "stroem": "Power outside",
    "stroem_avsnitt": ("The solar panel was net positive in August with 24 sessions a day. The plan steps down by "
                       "itself when the voltage drops. The goal is for the box to survive November."),
    "tidslinje": "The timeline",
    "verktoey": "The tools",
    "verktoey_avsnitt": ("Much of the code was written together with Claude Code. What was measured, chosen and "
                         "dropped is under the choices above. The repo has an AGENTS.md with the conventions, so an "
                         "agent works by the same rules a colleague would."),
}
DELELISTE = [
    ("Indoor unit", ["Waveshare ESP32-S3-ePaper-13.3E6, 13.3\" Spectra 6, six colours, 16 MB PSRAM", "IKEA RÖDALM frame, 30×40 cm"]),
    ("Outdoor unit", ["Seeed XIAO ESP32-S3, 8 MB PSRAM", "INMP441 I2S microphone, foam against wind",
                      "Waveshare Solar Power Manager (D), MPPT charging", "3.7 V LiPo, 10 Ah", "Solar panel, 6 to 24 V in"]),
    ("Home server", ["An old PC running Linux, Python 3.12, two venvs", "systemd for the services, cron for the day"]),
    ("Camera", ["Android phone with a telephoto lens in the window", "Before: Raspberry Pi 3 B with the HQ camera, parked"]),
]
STROEM = [("Deep sleep between sessions", "14 µA"),
          ("Recording and upload, a few tens of seconds", "~100 mA"),
          ("Raspberry Pi 3 B idle, for comparison", "~450 mA")]
TIDSLINJE = [
    ("21 July 2026", "First image on the screen, sent from the Mac."),
    ("24 July", "Daily push from cron on the home server."),
    ("28 July", "Outdoor unit v1 on a Raspberry Pi dies from lack of power."),
    ("4 August", "Outdoor unit v2 on a XIAO ESP32-S3 in service, solar powered."),
    ("28 August", "The bird page takes over from the free AI image."),
    ("13 September", "Cost brakes on the camera analysis."),
    ("September", "The phone as camera. The repo is prepared for going public."),
]

BUNN = {
    "laget_foer": "Made by ",
    "bruker": "sonwit",
    "laget_etter": ". Everything from the firmware to this page is open on GitHub.",
    "takk": ("The plates are public domain from Wikimedia Commons; the artist is named with each bird. "
             "Species identification: BirdNET. Weather: MET Norway. The code is MIT licensed."),
    "github": "The code on GitHub",
    "personvern": "Privacy statement (in Norwegian)",
    "sporing": "This page uses no tracking.",
    "hopp": "Skip to content",
}
