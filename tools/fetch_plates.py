#!/usr/bin/env python3
"""
Fugleramme: skaff fugleplansjer fra Wikimedia Commons.

Commons har en kategori «<Vitenskapelig navn> (illustrations)» for nesten hver
art -- 40 av de 41 artene utedelen har hoert saa langt. Der ligger plansjene
fra de gamle fuglebøkene (Naumann 1905, Morris «A history of British birds»,
Dresser, Gould m.fl.), alle falt i det fri. Men kategoriene er rotete: der
ligger ogsaa frimerker, lydfiler, moderne foto og fargeleggingsark. Derfor er
dette et TO-STEGS verktoey -- maskinen lager en kortliste, mennesket velger.

  1) Kortliste (henter bare metadata, ingen bilder):
       python3 fetch_plates.py --shortlist --birds birds.json --out plates/velg.html
     Aapne HTML-en, se gjennom kandidatene, kopier filnavnet du vil ha.

  2) Hent den valgte plansjen:
       python3 fetch_plates.py --get "File:Turdus iliacus NAUMANN.jpg" --for "Turdus iliacus"

Plansjene lagres som plates/<slekt-art>.jpg, som er akkurat der
render_daily_panel.py leter. plates/plates.json holder kilde og lisens for
hver -- vi skal kunne svare paa hvor et bilde kommer fra.

Kun stdlib.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
# Commons ber om en identifiserende User-Agent, som api.met.no. Kontakten
# kommer fra FUGLERAMME_KONTAKT (frame_server.env), se oppsett.py.
from oppsett import user_agent  # noqa: E402
UA = os.environ.get("COMMONS_USER_AGENT", user_agent("fugleramme-plates/1.0"))

HERE = os.path.dirname(os.path.abspath(__file__))
PLATES_DIR = os.environ.get(
    "PLATES_DIR",
    os.path.join(HERE, "plates") if os.path.isdir(os.path.join(HERE, "plates"))
    else os.path.join(HERE, "..", "plates"))

# Plansjene skal fylle 1104x620 (hero) uten aa bli grøtete, saa alt under
# ~800 px bredde er ubrukelig. Mange Commons-filer er smaa utsnitt paa
# 250 px -- de skal ikke i kortlista i det hele tatt.
MIN_WIDTH = int(os.environ.get("PLATE_MIN_WIDTH", "800"))
CANDIDATES = int(os.environ.get("PLATE_CANDIDATES", "12"))

# Titler som nesten alltid er feil vare i en «(illustrations)»-kategori.
STOPP = ("stamp", "frimerke", "briefmarke", "coloring", "colouring", "ausmal",
         "logo", "coat of arms", "wappen", "banknote", "coin", "münze",
         "poster", "sign", "schild", "relief", "statue", "graffiti", "mural")

# Verk vi vet er gamle plansjeverk -- treff her sorteres oeverst i kortlista.
VERK = ("naumann", "a history of british birds", "british ornithology",
        "history of the birds of europe", "dresser", "gould", "morris",
        "natural history of birds", "atlas", "iconographia", "bhl",
        "brehm", "buffon", "meyer", "vögel", "voegel", "birds of britain")


def _api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def slug(scientific: str) -> str:
    return scientific.strip().lower().replace(" ", "-")


def candidates(scientific: str) -> list[dict]:
    """Kandidatplansjer for arten, best foerst. Henter kun metadata."""
    try:
        d = _api({
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{scientific} (illustrations)",
            "gcmtype": "file", "gcmlimit": "100",
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": "420",
        })
    except Exception as e:  # noqa: BLE001
        print(f"  ADVARSEL: oppslag feilet for {scientific}: {str(e)[:90]}",
              file=sys.stderr)
        return []

    out = []
    for pg in (d.get("query", {}).get("pages") or {}).values():
        title = pg.get("title", "")
        ii = (pg.get("imageinfo") or [{}])[0]
        low = title.lower()
        if not low.endswith((".jpg", ".jpeg", ".png")):
            continue                      # .ogg, .pdf, .svg, .tif
        if any(s in low for s in STOPP):
            continue
        if ii.get("width", 0) < MIN_WIDTH:
            continue
        lic = ii.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
        if "public domain" not in lic.lower() and not lic.lower().startswith("cc0"):
            continue                      # bare det som trygt kan henge paa veggen
        out.append({
            "title": title,
            "url": ii.get("url", "").split("?")[0],
            "thumb": ii.get("thumburl", ""),
            "w": ii.get("width"), "h": ii.get("height"),
            "kb": round(ii.get("size", 0) / 1024),
            "lisens": lic,
            "verk": next((v for v in VERK if v in low), ""),
        })

    def rank(c):
        # Kjente plansjeverk foerst, saa staaende format (plansjer er portrett),
        # saa stoerrelse.
        staaende = 0 if c["h"] >= c["w"] else 1
        return (0 if c["verk"] else 1, staaende, -(c["w"] or 0))

    return sorted(out, key=rank)[:CANDIDATES]


def shortlist(species: list[dict], out_path: str) -> None:
    blocks = []
    for s in species:
        sci = s["scientific_name"]
        navn = s.get("norsk") or s.get("common_name", "")
        cands = candidates(sci)
        print(f"  {navn:22s} {len(cands):2d} kandidater")
        cards = "".join(f"""
          <figure>
            <img src="{html.escape(c['thumb'])}" loading="lazy">
            <figcaption>
              <code>{html.escape(c['title'])}</code>
              <span>{c['w']}x{c['h']} · {c['kb']} KB · {html.escape(c['lisens'])}</span>
            </figcaption>
          </figure>""" for c in cands)
        blocks.append(f"""
        <section>
          <h2>{html.escape(navn)} <i>{html.escape(sci)}</i></h2>
          <p class="cmd">python3 fetch_plates.py --get "FILNAVN" --for "{html.escape(sci)}"</p>
          <div class="rad">{cards or '<p>ingen kandidater over ' + str(MIN_WIDTH) + ' px</p>'}</div>
        </section>""")
        time.sleep(0.2)   # vaer snill mot Commons

    doc = f"""<meta charset="utf-8"><title>Velg plansjer</title>
<style>
 body {{ font:15px/1.4 system-ui,sans-serif; margin:24px; background:#fff; color:#111; }}
 h2 {{ font-size:20px; margin:28px 0 4px; }} h2 i {{ font-weight:400; color:#666; }}
 .cmd {{ font:12px/1.4 ui-monospace,monospace; color:#666; margin-bottom:10px; }}
 .rad {{ display:flex; gap:14px; overflow-x:auto; padding-bottom:8px; }}
 figure {{ margin:0; flex:0 0 240px; }}
 figure img {{ width:240px; height:300px; object-fit:contain; background:#f4f4f4;
               border:1px solid #ddd; }}
 figcaption {{ font-size:11px; margin-top:4px; word-break:break-all; }}
 figcaption span {{ display:block; color:#777; }}
</style>
<h1>Kandidatplansjer fra Wikimedia Commons</h1>
<p>Alt her er falt i det fri. Finn den du vil ha, kopier filnavnet og kjør
kommandoen over raden.</p>
{''.join(blocks)}"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(doc)
    print(f"OK: {out_path}")


def fetch(title: str, scientific: str) -> str:
    """Last ned én valgt fil til plates/<slekt-art>.<ext> og noter kilden."""
    d = _api({"action": "query", "titles": title, "prop": "imageinfo",
              "iiprop": "url|size|extmetadata", "iiurlwidth": "1600"})
    pg = list(d["query"]["pages"].values())[0]
    if "imageinfo" not in pg:
        raise SystemExit(f"Fant ikke {title} paa Commons")
    ii = pg["imageinfo"][0]
    em = ii.get("extmetadata", {})
    lic = em.get("LicenseShortName", {}).get("value", "")
    if "public domain" not in lic.lower() and not lic.lower().startswith("cc0"):
        raise SystemExit(f"{title} er ikke public domain ({lic}) — velg en annen.")

    # Bruk nedskalert versjon: 1600 px er mer enn nok for en 1104x620-ramme,
    # og originalene kan vaere titalls megabyte.
    src = ii.get("thumburl") or ii["url"]
    ext = ".png" if src.lower().split("?")[0].endswith(".png") else ".jpg"
    os.makedirs(PLATES_DIR, exist_ok=True)
    dest = os.path.join(PLATES_DIR, slug(scientific) + ext)

    req = urllib.request.Request(src, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())

    index_path = os.path.join(PLATES_DIR, "plates.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    index[scientific] = {
        "fil": os.path.basename(dest),
        "commons": title,
        "side": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
        "lisens": lic,
        "opphav": em.get("Artist", {}).get("value", "")[:200],
    }
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"OK: {dest} ({os.path.getsize(dest)//1024} KB, {lic})")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Hent fugleplansjer fra Wikimedia Commons.")
    ap.add_argument("--shortlist", action="store_true")
    ap.add_argument("--birds", default="birds.json")
    ap.add_argument("--out", default=os.path.join(PLATES_DIR, "velg.html"))
    ap.add_argument("--get", metavar="FILE:...")
    ap.add_argument("--for", dest="scientific", metavar="'Genus art'")
    ap.add_argument("--species", nargs="*", help="overstyr artslista (latinske navn)")
    args = ap.parse_args()

    if args.get:
        if not args.scientific:
            raise SystemExit("--get krever --for \"Genus art\"")
        fetch(args.get, args.scientific)
        return 0

    if args.shortlist:
        sys.path.insert(0, HERE)
        from bird_names import norwegian_name
        if args.species:
            species = [{"scientific_name": s, "norsk": norwegian_name(s)}
                       for s in args.species]
        else:
            data = json.load(open(args.birds))
            species = [{**s, "norsk": norwegian_name(s["scientific_name"],
                                                     s.get("common_name", ""))}
                       for s in data.get("species", [])]
        shortlist(species, args.out)
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
