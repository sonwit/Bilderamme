#!/usr/bin/env python3
"""
eksporter_dag.py -- dagen paa veggen til nettsida, og push.

    venv/bin/python3 repo/tools/eksporter_dag.py              # fra /opt/fugleramme, via cron
    venv/bin/python3 repo/tools/eksporter_dag.py --ikke-push  # bare skriv filene

Kjoeres paa serveren etter hver tegning. Leser det kjeden alt har laget:
plates/dagens-bakgrunn.json og .png (illustrasjonen og hvor fuglene staar),
birds.json eller www/birds-valgt.json (dagens liste) og www/panel.html
(vaerlinja slik den ble tegnet). Skriver nettside/dager/<dato>.json og .png i
repo-klonen, regner artsstatistikken, committer og pusher. Hver push bygger
nettsida paa GitHub Pages.

Lista settes sammen med de samme funksjonene som veggen bruker
(render_daily_panel: split_species, nummerering, «N oekter»/«N ggr»), saa
JSON-en sier det samme som arket. Ingen posisjon: kildelinja med
koordinatene er ikke med, og fila sjekkes foer den skrives.

Repo-klonen ligger i /opt/fugleramme/repo med en deploy key som bare kan
pushe til dette repoet. Standardbibliotek, som resten av serversidene.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import importlib
import json
import os
import re
import shutil
import subprocess
import sys

HER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HER)                       # repo-klonen scriptet ligger i
BASE = os.environ.get("FUGLERAMME_BASE", os.path.dirname(REPO))   # /opt/fugleramme


def last(base: str):
    """render_daily_panel og bird_names fra det som faktisk tegnet veggen.
    Finnes de ikke der (lokal test), fra repoet."""
    for sti in (base, os.path.join(REPO, "tools")):
        if os.path.exists(os.path.join(sti, "render_daily_panel.py")):
            sys.path.insert(0, sti)
            return importlib.import_module("render_daily_panel"), importlib.import_module("bird_names")
    raise SystemExit("Fant ikke render_daily_panel.py")


def les_json(sti: str):
    with open(sti, encoding="utf-8") as f:
        return json.load(f)


def vaer_fra_panel(sti: str) -> str:
    """Vaerlinja slik den ble tegnet. Vaeret hentes live naar sida tegnes og
    lagres ikke, saa panel.html er det eneste stedet det staar."""
    try:
        with open(sti, encoding="utf-8") as f:
            t = f.read()
    except OSError:
        return ""
    m = re.search(r'<div class="vaerlinje">\s*<span class="sted">[^<]*</span>(?:<br>)?\s*([^<]*?)\s*</div>', t)
    if not m:
        m = re.search(r'<div class="vaer">\s*<div class="sted">[^<]*</div>\s*<div>([^<]*)</div>', t)
    return html.unescape(m.group(1)).strip() if m else ""


def dagens(base: str, rdp, bn) -> tuple[dict, str] | None:
    """JSON-en for dagen som sist ble tegnet, og stien til illustrasjonen."""
    bg_json = os.path.join(base, "plates", "dagens-bakgrunn.json")
    bg_png = os.path.join(base, "plates", "dagens-bakgrunn.png")
    if not (os.path.exists(bg_json) and os.path.exists(bg_png)):
        print("Ingen dagens-bakgrunn.json/.png -- ingenting aa eksportere.")
        return None
    bg = les_json(bg_json)
    dato = bg.get("date", "")
    # Kjeden tegner i gaar naar i dag ikke har noe ennaa; da ligger lista i
    # birds-valgt.json. birds.json er alltid dagens.
    birds = None
    for kandidat in (os.path.join(base, "birds.json"), os.path.join(base, "www", "birds-valgt.json")):
        if os.path.exists(kandidat):
            b = les_json(kandidat)
            if b.get("date") == dato:
                birds = b
                break
    if birds is None:
        print(f"Fant ingen liste for {dato} -- hopper over.")
        return None

    # Samme utvalg og rekkefoelge som veggen (render_daily_panel.build_html).
    alle = birds.get("species", [])
    alle_sure, unsure = rdp.split_species(alle, len(alle))
    tegnet = {sp["scientific_name"]: sp for sp in bg.get("species", []) if sp.get("merke")}
    med = [s for s in alle_sure if s.get("scientific_name") in tegnet]
    resten = [s for s in alle_sure if s not in med]
    plass = max(rdp.OVERLAY_ROWS - len(med), 0)
    valgt = med + resten[:plass]
    sure = [s for s in alle_sure if s in valgt]
    unsure = unsure + resten[plass:]

    hoert = []
    nr = 0
    for s in sure:
        sci = s.get("scientific_name", "")
        sess = s.get("sessions", 1)
        rad = {
            "norsk": bn.norwegian_name(sci, s.get("common_name", "")),
            "latin": sci,
            "sikkerhet": round(s.get("confidence", 0.0) * 100),
            "tid": rdp._heard(s),
            "belegg": f"{sess} økter" if sess > 1 else f"{s.get('detections', 0)} ggr",
        }
        if sci in tegnet:
            nr += 1
            rad = {"nr": nr, **rad, "boks": tegnet[sci].get("boks"), "merke": tegnet[sci]["merke"]}
            if rad["boks"] is None:
                del rad["boks"]
        hoert.append(rad)
    ogsaa = [bn.norwegian_name(s.get("scientific_name", ""), s.get("common_name", "")) for s in unsure[:6]]

    panel = os.path.join(base, "www", "panel.html")
    try:
        tegnet_kl = datetime.datetime.fromtimestamp(os.path.getmtime(panel)).strftime("%H:%M")
    except OSError:
        tegnet_kl = datetime.datetime.now().strftime("%H:%M")
    d = {
        "dato": dato,
        "tegnet": tegnet_kl,
        "periode": birds.get("periode", ""),
        "opptak": birds.get("sessions_today", 0),
        "vaer": vaer_fra_panel(panel),
        "antall_arter": len(sure) + len(unsure),
        "hoert": hoert,
        "ogsaa": ogsaa,
        "bilde": f"{dato}.png",
    }
    return d, bg_png


def sjekk_personvern(d: dict, rdp) -> None:
    """Nettsida viser aldri posisjon. Stopp heller enn aa skrive noe galt."""
    tekst = json.dumps(d, ensure_ascii=False)
    if re.search(r"\d\.\d+\s*[°º]", tekst):
        raise SystemExit("STOPP: noe som ligner en koordinat i eksporten.")
    stedsnavn = getattr(rdp, "STEDSNAVN", "")
    if stedsnavn and stedsnavn != "Hagen" and stedsnavn in tekst:
        raise SystemExit("STOPP: stedsnavnet er med i eksporten.")


def skriv_hvis_endret(sti: str, data: bytes) -> bool:
    if os.path.exists(sti):
        with open(sti, "rb") as f:
            if hashlib.sha256(f.read()).digest() == hashlib.sha256(data).digest():
                return False
    os.makedirs(os.path.dirname(sti), exist_ok=True)
    with open(sti, "wb") as f:
        f.write(data)
    return True


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dagen paa veggen til nettsida.")
    ap.add_argument("--base", default=BASE, help="der kjeden kjoerer (/opt/fugleramme)")
    ap.add_argument("--ikke-push", action="store_true", help="skriv filene, men ikke commit eller push")
    args = ap.parse_args()
    naa = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if not args.ikke_push:
        # Rydd etter en eventuell avbrutt kjoering (alt under regenereres), og
        # hent, saa klonen og dette scriptet er ajour og pushen gaar rett inn.
        # Committede, upushede dager overlever: rebase legger dem oppaa.
        git("reset", "--hard", "--quiet", "HEAD")
        git("clean", "-fdq", "nettside/dager")
        r = git("pull", "--rebase", "--quiet")
        if r.returncode != 0:
            print(f"{naa} git pull feilet: {r.stderr.strip()[:200]}")
            git("rebase", "--abort")
            return 1

    rdp, bn = last(args.base)
    ut = dagens(args.base, rdp, bn)
    if ut is None:
        return 0
    d, bg_png = ut
    sjekk_personvern(d, rdp)

    dager = os.path.join(REPO, "nettside", "dager")
    endret = skriv_hvis_endret(os.path.join(dager, f"{d['dato']}.json"),
                               (json.dumps(d, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    with open(bg_png, "rb") as f:
        endret = skriv_hvis_endret(os.path.join(dager, f"{d['dato']}.png"), f.read()) or endret

    # Statistikken: dager hoert per art, fra observasjonsloggen.
    logg = os.path.join(args.base, "data", "observations.jsonl")
    if os.path.exists(logg):
        sys.path.insert(0, os.path.join(REPO, "tools"))
        stat = importlib.import_module("artsstatistikk").regn(logg)
        endret = skriv_hvis_endret(os.path.join(REPO, "nettside", "statistikk.json"),
                                   (json.dumps(stat, ensure_ascii=False, indent=1) + "\n").encode("utf-8")) or endret

    print(f"{naa} {d['dato']}: {d['antall_arter']} arter paa {d['opptak']} opptak, tegnet {d['tegnet']}"
          + ("" if endret else " (uendret)"))
    if args.ikke_push or not endret:
        return 0

    git("add", "nettside/dager", "nettside/statistikk.json")
    melding = (f"Dagen {d['dato']}: {d['antall_arter']} arter paa {d['opptak']} opptak, tegnet {d['tegnet']}\n\n"
               "Eksportert av serveren etter tegningen (tools/eksporter_dag.py).")
    r = git("commit", "--quiet", "-m", melding)
    if r.returncode != 0:
        print(f"{naa} ingenting aa committe: {r.stderr.strip()[:120]}")
        return 0
    r = git("push", "--quiet")
    if r.returncode != 0:
        print(f"{naa} git push feilet: {r.stderr.strip()[:200]}")
        return 1
    print(f"{naa} pushet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
