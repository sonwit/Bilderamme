#!/usr/bin/env python3
"""
Fugleramme: norske fuglenavn.

BirdNET gir engelsk artsnavn + latinsk navn. Panelet skal vise norsk navn med
det latinske under, saa vi trenger en oversettelse. Vitenskapelig navn er
noekkelen -- det engelske navnet varierer mellom BirdNET-versjoner
("Eurasian Blue Tit" vs "Blue Tit"), mens Sitta europaea staar stille.

Lista dekker artene utedelen faktisk har hoert saa langt (se
data/observations.jsonl) pluss vanlige hage- og skogsfugler i omraadet. En art
som mangler faller tilbake paa det engelske navnet -- panelet skal aldri
stoppe fordi en gjest er ukjent, og en engelsk linje er et tydelig signal om
at arten boer legges inn her.

    from bird_names import norwegian_name
    norwegian_name("Pica pica", "Eurasian Magpie")  -> "Skjære"
"""

# Vitenskapelig navn (lowercase) -> norsk navn.
NORWEGIAN = {
    # --- Meiser og smaafugl i hagen ---
    "parus major": "Kjøttmeis",
    "cyanistes caeruleus": "Blåmeis",
    "periparus ater": "Svartmeis",
    "poecile palustris": "Løvmeis",
    "poecile montanus": "Granmeis",
    "lophophanes cristatus": "Toppmeis",
    "aegithalos caudatus": "Stjertmeis",
    "sitta europaea": "Spettmeis",
    "certhia familiaris": "Trekryper",
    "troglodytes troglodytes": "Gjerdesmett",
    "prunella modularis": "Jernspurv",
    "regulus regulus": "Fuglekonge",
    "erithacus rubecula": "Rødstrupe",

    # --- Finker og spurver ---
    "fringilla coelebs": "Bokfink",
    "fringilla montifringilla": "Bjørkefink",
    "chloris chloris": "Grønnfink",
    "spinus spinus": "Grønnsisik",
    "carduelis carduelis": "Stillits",
    "acanthis flammea": "Gråsisik",
    "acanthis hornemanni": "Polarsisik",
    "linaria cannabina": "Tornirisk",
    "loxia curvirostra": "Grankorsnebb",
    "loxia pytyopsittacus": "Furukorsnebb",
    "pyrrhula pyrrhula": "Dompap",
    "coccothraustes coccothraustes": "Kjernebiter",
    "carpodacus erythrinus": "Rosenfink",
    "passer domesticus": "Gråspurv",
    "passer montanus": "Pilfink",
    "emberiza citrinella": "Gulspurv",
    "emberiza schoeniclus": "Sivspurv",

    # --- Troster og fluesnappere ---
    "turdus merula": "Svarttrost",
    "turdus pilaris": "Gråtrost",
    "turdus iliacus": "Rødvingetrost",
    "turdus philomelos": "Måltrost",
    "turdus viscivorus": "Duetrost",
    "phoenicurus phoenicurus": "Rødstjert",
    "phoenicurus ochruros": "Svartrødstjert",
    "saxicola rubetra": "Buskskvett",
    "oenanthe oenanthe": "Steinskvett",
    "ficedula hypoleuca": "Svarthvit fluesnapper",
    "muscicapa striata": "Gråfluesnapper",

    # --- Sangere ---
    "sylvia atricapilla": "Munk",
    "sylvia borin": "Hagesanger",
    "curruca communis": "Tornsanger",
    "sylvia communis": "Tornsanger",
    "curruca curruca": "Møller",
    "phylloscopus trochilus": "Løvsanger",
    "phylloscopus collybita": "Gransanger",
    "phylloscopus sibilatrix": "Bøksanger",
    "acrocephalus schoenobaenus": "Sivsanger",

    # --- Kraaker ---
    "pica pica": "Skjære",
    "garrulus glandarius": "Nøtteskrike",
    "nucifraga caryocatactes": "Nøttekråke",
    "corvus corax": "Ravn",
    "corvus cornix": "Kråke",
    "corvus corone": "Svartkråke",
    "corvus monedula": "Kaie",
    "corvus frugilegus": "Kornkråke",

    # --- Spetter ---
    "dendrocopos major": "Flaggspett",
    "dryobates minor": "Dvergspett",
    "dryocopus martius": "Svartspett",
    "picus viridis": "Grønnspett",
    "jynx torquilla": "Vendehals",

    # --- Duer, svaler, seilere ---
    "columba palumbus": "Ringdue",
    "columba livia": "Bydue",
    "columba oenas": "Skogdue",
    "streptopelia decaocto": "Tyrkerdue",
    "hirundo rustica": "Låvesvale",
    "delichon urbicum": "Taksvale",
    "riparia riparia": "Sandsvale",
    "apus apus": "Tårnseiler",

    # --- Ugler og rovfugl ---
    "strix aluco": "Kattugle",
    "strix uralensis": "Slagugle",
    "bubo bubo": "Hubro",
    "asio otus": "Hornugle",
    "aegolius funereus": "Perleugle",
    "glaucidium passerinum": "Spurveugle",
    "surnia ulula": "Haukugle",
    "tyto alba": "Tårnugle",
    "accipiter nisus": "Spurvehauk",
    "accipiter gentilis": "Hønsehauk",
    "buteo buteo": "Musvåk",
    "falco tinnunculus": "Tårnfalk",
    "falco subbuteo": "Lerkefalk",
    "milvus milvus": "Glente",

    # --- Andre landfugler ---
    "sturnus vulgaris": "Stær",
    "bombycilla garrulus": "Sidensvans",
    "lanius collurio": "Tornskate",
    "motacilla alba": "Linerle",
    "motacilla flava": "Gulerle",
    "anthus pratensis": "Heipiplerke",
    "anthus trivialis": "Trepiplerke",
    "alauda arvensis": "Sanglerke",
    "cuculus canorus": "Gjøk",
    "tetrao urogallus": "Storfugl",
    "lyrurus tetrix": "Orrfugl",
    "tetrastes bonasia": "Jerpe",
    "lagopus lagopus": "Lirype",
    "phasianus colchicus": "Fasan",

    # --- Vann og vaatmark (BirdNET plukker dem opp fra Nitelva-kanten) ---
    "anas platyrhynchos": "Stokkand",
    "anas crecca": "Krikkand",
    "mareca penelope": "Brunnakke",
    "aythya fuligula": "Toppand",
    "bucephala clangula": "Kvinand",
    "mergus merganser": "Laksand",
    "cygnus olor": "Knoppsvane",
    "cygnus cygnus": "Sangsvane",
    "anser anser": "Grågås",
    "branta canadensis": "Kanadagås",
    "ardea cinerea": "Gråhegre",
    "botaurus stellaris": "Rørdrum",
    "grus grus": "Trane",
    "fulica atra": "Sothøne",
    "gallinula chloropus": "Sivhøne",
    "rallus aquaticus": "Vannrikse",
    "porzana porzana": "Myrrikse",
    "crex crex": "Åkerrikse",
    "podiceps cristatus": "Toppdykker",
    "tachybaptus ruficollis": "Dvergdykker",
    "gavia arctica": "Storlom",
    "vanellus vanellus": "Vipe",
    "charadrius dubius": "Dverglo",
    "charadrius hiaticula": "Sandlo",
    "gallinago gallinago": "Enkeltbekkasin",
    "scolopax rusticola": "Rugde",
    "numenius arquata": "Storspove",
    "tringa ochropus": "Skogsnipe",
    "tringa totanus": "Rødstilk",
    "actitis hypoleucos": "Strandsnipe",
    "larus canus": "Fiskemåke",
    "larus argentatus": "Gråmåke",
    "larus ridibundus": "Hettemåke",
    "chroicocephalus ridibundus": "Hettemåke",
    "sterna hirundo": "Makrellterne",
}


def norwegian_name(scientific_name: str, common_name: str = "") -> str:
    """Norsk navn for arten, eller det engelske navnet hvis vi ikke har det.

    Slaar opp paa vitenskapelig navn (stabilt), og faller tilbake paa slekten
    alene naar BirdNET bruker et annet artsepitet enn oss (f.eks.
    Curruca/Sylvia-splitten) og slekten bare har én art i lista."""
    key = (scientific_name or "").strip().lower()
    if key in NORWEGIAN:
        return NORWEGIAN[key]
    genus = key.split(" ")[0] if key else ""
    if genus:
        hits = {v for k, v in NORWEGIAN.items() if k.startswith(genus + " ")}
        if len(hits) == 1:
            return hits.pop()
    return common_name or scientific_name or "Ukjent art"


def is_translated(scientific_name: str) -> bool:
    """True hvis arten har et norsk navn i lista. Panelet bruker dette til aa
    sette det engelske navnet i kursiv, saa hull i lista er lette aa se."""
    return (scientific_name or "").strip().lower() in NORWEGIAN


# ----------------------------------------------------------------------
# Kroppslengde i cm (nebbspiss til halespiss, typisk voksen)
# ----------------------------------------------------------------------
# Brukes av compose_branch.py til aa skalere fuglene i forhold til hverandre.
# Uten dette blir en skjaere paa 44 cm like stor som en groennsisik paa 12.
#
# NB: tallene er TOTALLENGDE, altsaa med hale. Det er riktig maal her, siden
# plansjene viser fuglen i profil med halen med.
LENGDE_CM = {
    # smaafugl
    "regulus regulus": 9, "troglodytes troglodytes": 9.5,
    "aegithalos caudatus": 14, "cyanistes caeruleus": 12,
    "periparus ater": 11, "poecile palustris": 12, "poecile montanus": 13,
    "lophophanes cristatus": 12, "parus major": 14, "sitta europaea": 14,
    "certhia familiaris": 13, "prunella modularis": 14,
    "erithacus rubecula": 14, "phoenicurus phoenicurus": 14,
    "phoenicurus ochruros": 14, "saxicola rubetra": 13,
    "oenanthe oenanthe": 15, "ficedula hypoleuca": 13,
    "muscicapa striata": 14, "phylloscopus trochilus": 11,
    "phylloscopus collybita": 11, "phylloscopus sibilatrix": 12,
    "sylvia atricapilla": 14, "sylvia borin": 14, "curruca communis": 14,
    "sylvia communis": 14, "curruca curruca": 13,
    "acrocephalus schoenobaenus": 13, "motacilla alba": 18,
    "motacilla flava": 17, "anthus pratensis": 15, "anthus trivialis": 15,
    "alauda arvensis": 18, "delichon urbicum": 13, "hirundo rustica": 19,
    "riparia riparia": 12, "apus apus": 17,
    # finker og spurver
    "fringilla coelebs": 15, "fringilla montifringilla": 15,
    "chloris chloris": 15, "spinus spinus": 12, "carduelis carduelis": 13,
    "acanthis flammea": 13, "acanthis hornemanni": 13, "linaria cannabina": 13,
    "loxia curvirostra": 16, "loxia pytyopsittacus": 18,
    "pyrrhula pyrrhula": 16, "coccothraustes coccothraustes": 18,
    "carpodacus erythrinus": 15, "passer domesticus": 15,
    "passer montanus": 14, "emberiza citrinella": 17,
    "emberiza schoeniclus": 15,
    # troster og mellomstore
    "turdus merula": 25, "turdus pilaris": 25, "turdus iliacus": 21,
    "turdus philomelos": 23, "turdus viscivorus": 27,
    "sturnus vulgaris": 21, "bombycilla garrulus": 20,
    "lanius collurio": 17, "cuculus canorus": 33,
    "dendrocopos major": 23, "dryobates minor": 15,
    "picus viridis": 32, "dryocopus martius": 46, "jynx torquilla": 17,
    # kraaker og duer
    "pica pica": 44, "garrulus glandarius": 34,
    "nucifraga caryocatactes": 33, "corvus monedula": 34,
    "corvus frugilegus": 46, "corvus cornix": 47, "corvus corone": 47,
    "corvus corax": 64, "columba palumbus": 41, "columba livia": 33,
    "columba oenas": 33, "streptopelia decaocto": 32,
    # ugler og rovfugl
    "glaucidium passerinum": 17, "aegolius funereus": 25,
    "asio otus": 36, "strix aluco": 38, "surnia ulula": 38,
    "strix uralensis": 60, "bubo bubo": 70, "tyto alba": 34,
    "accipiter nisus": 33, "accipiter gentilis": 55, "buteo buteo": 52,
    "falco tinnunculus": 34, "falco subbuteo": 33, "milvus milvus": 63,
    # skogsfugl
    "tetrastes bonasia": 36, "lagopus lagopus": 38, "lyrurus tetrix": 53,
    "tetrao urogallus": 85, "phasianus colchicus": 75,
    # vann og vaatmark
    "charadrius dubius": 16, "charadrius hiaticula": 19,
    "actitis hypoleucos": 20, "tringa ochropus": 22, "tringa totanus": 28,
    "gallinago gallinago": 26, "scolopax rusticola": 34,
    "vanellus vanellus": 30, "numenius arquata": 55,
    "porzana porzana": 22, "crex crex": 28, "rallus aquaticus": 26,
    "gallinula chloropus": 33, "fulica atra": 38,
    "tachybaptus ruficollis": 27, "podiceps cristatus": 48,
    "larus ridibundus": 38, "chroicocephalus ridibundus": 38,
    "larus canus": 43, "larus argentatus": 60, "sterna hirundo": 34,
    "anas crecca": 36, "anas platyrhynchos": 58, "mareca penelope": 48,
    "aythya fuligula": 42, "bucephala clangula": 46, "mergus merganser": 62,
    "ardea cinerea": 94, "botaurus stellaris": 75, "grus grus": 115,
    "cygnus olor": 150, "cygnus cygnus": 150, "anser anser": 82,
    "branta canadensis": 95, "gavia arctica": 70,
}

# Naar arten mangler i tabellen: en middels smaafugl. Bedre enn aa gjette
# stort og fylle halve arket med noe vi ikke vet stoerrelsen paa.
STANDARD_LENGDE = 18.0


def length_cm(scientific_name: str) -> float:
    """Typisk totallengde i cm. Faller tilbake paa slekten, saa paa 18 cm."""
    key = (scientific_name or "").strip().lower()
    if key in LENGDE_CM:
        return float(LENGDE_CM[key])
    genus = key.split(" ")[0] if key else ""
    if genus:
        treff = [v for k, v in LENGDE_CM.items() if k.startswith(genus + " ")]
        if treff:
            return float(sum(treff) / len(treff))
    return STANDARD_LENGDE


if __name__ == "__main__":
    import json
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "test/data/birds-2026-08-28.json"
    data = json.load(open(src))
    missing = 0
    for s in data.get("species", []):
        sci, com = s.get("scientific_name", ""), s.get("common_name", "")
        ok = is_translated(sci)
        missing += 0 if ok else 1
        print(f"  {'✓' if ok else '·'} {norwegian_name(sci, com):28s} {sci}")
    print(f"{len(data.get('species', []))} arter, {missing} uten norsk navn")
