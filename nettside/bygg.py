#!/usr/bin/env python3
"""
bygg.py -- bygger nettsida fra repoets egne data.

    python3 nettside/bygg.py            # skriver nettside/ut/
    python3 -m http.server 8765 --directory nettside/ut

Sida er statisk HTML uten JavaScript. Alt kommer fra det som alt ligger i
repoet: plates/ (plansjer, fugler, maler), tools/bird_names.py og
tools/lytteplan.py (soloppgangskurven regnes ut av den ekte koden),
nettside/dager/ (dagene sida kan vise) og nettside/innhold_<spraak>.py
(all tekst). Pillow er valgfritt: med Pillow lages nedskalerte WebP-bilder,
uten kopieres originalene.

GitHub Actions kjoerer dette ved hver push til main og legger nettside/ut/ paa
GitHub Pages, se .github/workflows/nettside.yml.
"""

from __future__ import annotations

import datetime
import html
import importlib
import json
import os
import re
import shutil
import sys

HER = os.path.dirname(os.path.abspath(__file__))
ROT = os.path.dirname(HER)
UT = os.path.join(HER, "ut")
SPRAAK = os.environ.get("NETTSIDE_SPRAAK", "nb")
# Absolutt adresse, bare til og:image og lenker som maa vaere absolutte.
URL = os.environ.get("NETTSIDE_URL", "https://sonwit.github.io/Bilderamme/").rstrip("/") + "/"

sys.path.insert(0, os.path.join(ROT, "tools"))
sys.path.insert(0, HER)
import bird_names as bn  # noqa: E402
import lytteplan  # noqa: E402
T = importlib.import_module(f"innhold_{SPRAAK}")

E = html.escape
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

# ---------------------------------------------------------------- bilder
def bilde(kilde: str, ut_rel: str, maks: int) -> str:
    """Nedskalert WebP av kilde i ut/<ut_rel>. Uten Pillow: kopi av originalen.
    Returnerer stien relativt til ut/. Hopper over hvis resultatet er nyere
    enn kilden, saa lokale bygg gaar fort."""
    if Image is None:
        ut_rel = os.path.splitext(ut_rel)[0] + os.path.splitext(kilde)[1].lower()
    maal = os.path.join(UT, ut_rel)
    os.makedirs(os.path.dirname(maal), exist_ok=True)
    if os.path.exists(maal) and os.path.getmtime(maal) >= os.path.getmtime(kilde):
        return ut_rel
    if Image is None:
        shutil.copyfile(kilde, maal)
        return ut_rel
    im = Image.open(kilde)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    im.thumbnail((maks, maks))
    if im.mode == "RGBA":
        bakgrunn = Image.new("RGB", im.size, (255, 255, 255))
        bakgrunn.paste(im, mask=im.split()[3])
        im = bakgrunn
    im.save(maal, "WEBP", quality=84, method=6)
    return ut_rel


# ---------------------------------------------------------------- data
def les_json(sti):
    with open(sti, encoding="utf-8") as f:
        return json.load(f)


def skala(cm: float) -> float:
    return max(0.55, min(1.60, (cm / 21) ** 0.6))


def kunstner(opphav: str, commons: str | None) -> str:
    k = re.sub(r"<[^>]+>", "", opphav or "")
    k = re.sub(r"\s*[<(/].*$", "", k).strip("; ").strip()
    if len(k) < 9 or k in ("John J", "Johann"):
        t = (commons or "").replace("File:", "")
        t = re.sub(r"\s*\(\d+\)\.jpg$", "", t).replace(".jpg", "")
        return "fra «" + t + "»" if t else ""
    if ";" in k:
        k = k.split(";")[0].strip()
    if "," in k and not k.startswith("J and"):
        etter, fornavn = [s.strip() for s in k.split(",", 1)]
        k = f"{fornavn} {etter}"
    return k


def hent_arter() -> list[dict]:
    arter = les_json(os.path.join(ROT, "plates", "arter.json"))
    plansjer = les_json(os.path.join(ROT, "plates", "plates.json"))
    fugler = os.path.join(ROT, "plates", "fugler")
    ut = []
    for fil in sorted(os.listdir(fugler)):
        if not fil.endswith(".png") or fil.endswith(("-flyvende.png", "-klatrende.png")):
            continue
        slug = fil[:-4]
        slekt, art = slug.split("-", 1)
        sci = f"{slekt.capitalize()} {art}"
        a = arter.get(sci.lower(), {})
        p = plansjer.get(sci, {})
        cm = a.get("lengde_cm") or bn.length_cm(sci)
        ut.append({
            "slug": slug, "sci": sci,
            "norsk": a.get("norsk") or bn.norwegian_name(sci),
            "cm": cm, "skala": skala(cm),
            "habitat": a.get("habitat") or bn.habitat(sci),
            "overvintrer": a.get("overvintrer"),
            "kunstner": kunstner(p.get("opphav", ""), p.get("commons")),
            "side": p.get("side"),
            "flyvende": os.path.exists(os.path.join(fugler, f"{slug}-flyvende.png")),
            "klatrende": os.path.exists(os.path.join(fugler, f"{slug}-klatrende.png")),
        })
    return ut


def hent_dager() -> list[dict]:
    mappe = os.path.join(HER, "dager")
    dager = []
    for fil in sorted(os.listdir(mappe)):
        if fil.endswith(".json"):
            d = les_json(os.path.join(mappe, fil))
            d["_png"] = os.path.join(mappe, d.get("bilde", fil[:-5] + ".png"))
            if os.path.exists(d["_png"]):
                dager.append(d)
    return dager


def dato_tekst(iso: str) -> tuple[str, str]:
    d = datetime.date.fromisoformat(iso)
    return T.UKEDAGER[d.weekday()], f"{d.day}. {T.MAANEDER[d.month - 1]} {d.year}"


# ---------------------------------------------------------------- byggeklosser
def topp(aktiv: str | None, p: str) -> str:
    lenker = []
    for navn, sti in T.NAV:
        cur = ' aria-current="page"' if sti == aktiv else ""
        lenker.append(f'<a href="{p}{sti}"{cur}>{E(navn)}</a>')
    return (f'<a class="hopp" href="#innhold">{E(T.BUNN["hopp"])}</a>\n'
            f'<header class="topp"><a class="ordmerke" href="{p}">{E(T.TITTEL)}</a>'
            f'<nav class="nav" aria-label="Sider">{"".join(lenker)}'
            f'<a class="ekstern" href="{T.GITHUB}">GitHub</a></nav></header>')


def bunn(p: str) -> str:
    b = T.BUNN
    return (f'<footer class="bunn"><div class="venstre"><span>{E(b["laget"])}</span><span>{E(b["takk"])}</span></div>'
            f'<div class="hoeyre"><a href="{T.GITHUB}">{E(b["github"])}</a>'
            f'<a href="{T.PERSONVERN}">{E(b["personvern"])}</a><span>{E(b["sporing"])}</span></div></footer>')


def side(tittel: str, innhold: str, dybde: int, aktiv: str | None = None,
         beskrivelse: str | None = None, og_bilde: str | None = None) -> str:
    p = "../" * dybde
    tittel_full = T.TITTEL if not tittel else f"{tittel} · {T.TITTEL}"
    og = f'<meta property="og:image" content="{URL}{og_bilde}">' if og_bilde else ""
    return f"""<!doctype html>
<html lang="{SPRAAK}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(tittel_full)}</title>
<meta name="description" content="{E(beskrivelse or T.BESKRIVELSE)}">
<meta property="og:title" content="{E(tittel_full)}">
<meta property="og:description" content="{E(beskrivelse or T.BESKRIVELSE)}">
{og}
<link rel="preload" href="{p}fonter/eb-garamond.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{p}stil.css">
</head>
<body>
<div class="side">
{topp(aktiv, p)}
<main id="innhold">
{innhold}
</main>
{bunn(p)}
</div>
</body>
</html>
"""


def seksjonstopp(tittel: str, hoeyre: str = "") -> str:
    return f'<div class="seksjonstopp"><h2 class="kicker">{E(tittel)}</h2>{hoeyre}</div>'


def fuglekort(a: dict, p: str) -> str:
    return (f'<a class="fuglekort" href="{p}fuglene/{a["slug"]}/">'
            f'<div class="kort skaaret"><img src="{p}{a["_bilde"]}" alt="{E(a["norsk"])}" loading="lazy"></div>'
            f'<div class="navnlinje"><span class="navn">{E(a["norsk"])}</span><span class="cm tall">{a["cm"]:g} {T.FUGLENE["cm"]}</span></div>'
            f'<div class="latin">{E(a["sci"])}</div></a>')


def foto(fil: str, tekst: str, p: str) -> str:
    return (f'<figure class="foto"><div class="kort skaaret"><img src="{p}bilder/foto/{fil}" alt="{E(tekst)}" loading="lazy"></div>'
            f'<figcaption>{E(tekst)}</figcaption></figure>')


# ---------------------------------------------------------------- veggsida
def ark(d: dict, p: str) -> str:
    v = T.VEGG
    ukedag, dato = dato_tekst(d["dato"])
    merker, omriss, rader = [], [], []
    for h in d["hoert"]:
        nr = h.get("nr")
        if nr and h.get("merke"):
            x, y = h["merke"]
            merker.append(f'<div class="merke tall" data-nr="{nr}" style="left: {x / 12:.2f}cqw; top: {y / 12:.2f}cqw;">{nr}</div>')
        if nr and h.get("boks"):
            x0, y0, x1, y1 = h["boks"]
            omriss.append(f'<div class="omriss" data-nr="{nr}" style="left: {(x0 - 14) / 12:.2f}cqw; top: {(y0 - 14) / 12:.2f}cqw; '
                          f'width: {(x1 - x0 + 28) / 12:.2f}cqw; height: {(y1 - y0 + 28) / 12:.2f}cqw;"></div>')
        rader.append(f'<li class="rad" data-nr="{nr or ""}"><div class="linje"><span class="nr tall">{nr or ""}</span>'
                     f'<span class="navn">{E(h["norsk"])}</span><span class="pst tall">{h["sikkerhet"]} %</span></div>'
                     f'<div class="detalj tall"><i>{E(h["latin"])}</i> · {E(h["tid"])} · {E(h["belegg"])}</div></li>')
    ogsaa = ""
    if d.get("ogsaa"):
        ogsaa = f'<div class="ogsaa"><span>{E(v["ogsaa"])}</span> {E(", ".join(d["ogsaa"]))}</div>'
    return f'''<div class="ark skaaret">
  <img src="{p}{d["_stor"]}" alt="{E(ukedag)} {E(dato)}: {E(", ".join(h["norsk"] for h in d["hoert"] if h.get("nr")))} på grenen" fetchpriority="high">
  {"".join(omriss)}{"".join(merker)}
  <div class="spalte">
    <div class="kicker">{E(v["kicker"])}</div>
    <div class="dag">{E(ukedag)}</div>
    <div class="dato tall">{E(dato)}</div>
    <div class="periode tall">{E(d["periode"])} · {d["opptak"]} {E(v["opptak"])}</div>
    <div class="strek"></div>
    <div class="sted">{E(v["sted"])}</div>
    <div class="vaer tall">{E(d["vaer"])}</div>
    <div class="hoert">{E(v["hoert"])}</div>
    <ol>{"".join(rader)}</ol>
    {ogsaa}
    <div class="strek2"></div>
    <div class="bunn tall">{d["antall_arter"]} {E(v["arter"])} {d["opptak"]} {E(v["opptak"])} · BirdNET<br>{E(v["bunn"])}</div>
  </div>
</div>'''


def vegg(d: dict, dager: list[dict], p: str) -> str:
    v = T.VEGG
    ukedag, dato = dato_tekst(d["dato"])
    i = [x["dato"] for x in dager].index(d["dato"])
    def pil(j, tekst, tegn):
        if 0 <= j < len(dager):
            return f'<a class="pil skaaret" href="{p}dag/{dager[j]["dato"]}/" aria-label="{E(tekst)}">{tegn}</a>'
        return f'<span class="pil skaaret av" aria-hidden="true">{tegn}</span>'
    stripe = ""
    if len(dager) > 1:
        lenker = []
        for x in dager:
            u, _ = dato_tekst(x["dato"])
            cur = ' aria-current="page"' if x["dato"] == d["dato"] else ""
            lenker.append(f'<a class="skaaret" href="{p}dag/{x["dato"]}/"{cur}><img src="{p}{x["_liten"]}" alt="" loading="lazy">'
                          f'<span class="tall">{E(u[:3])} {int(x["dato"][-2:])}.</span></a>')
        stripe = (f'<nav class="dager" aria-label="{E(v["dager"])}">{pil(i - 1, v["forrige"], "&lsaquo;")}'
                  f'{"".join(lenker)}{pil(i + 1, v["neste"], "&rsaquo;")}</nav>')
    return f'''<section class="vegg">
  <div class="ramme-ytre">{ark(d, p)}</div>
  <div class="tekst"><div class="kicker tall">{E(ukedag)} {E(dato)}</div>
  <div class="tall">{d["antall_arter"]} {E(v["arter"])} {d["opptak"]} {E(v["opptak"])} · {E(v["tegnet"])} {E(d["tegnet"])}</div></div>
  {stripe}
  <p class="tekst">{E(T.FORSIDE["under_ramma"])}</p>
</section>'''


# ---------------------------------------------------------------- sidene
def forside(dag: dict | None, dager: list[dict], arter: list[dict], p: str = "") -> str:
    f = T.FORSIDE
    kort = "".join(fuglekort(a, p) for a in arter if a["sci"] in T.UTVALG)
    deler = "".join(
        f'<div class="del"><div class="kicker liten">{E(n)}</div><div class="under">{E(u)}</div><p>{E(t)}</p>'
        f'<div class="etiketter">{"".join(f"<span class=\"etikett\">{E(c)}</span>" for c in chips)}</div></div>'
        for n, u, t, chips in T.DELER)
    bilder = "".join(foto(fil, tekst, p) for fil, tekst in T.FOTO)
    grener = "".join(
        f'<figure class="gren"><div class="kort skaaret"><img src="{p}bilder/grener/{navn}.webp" alt="{E(t)}" loading="lazy"></div>'
        f'<figcaption><div class="navn">{E(t)}</div><div class="mnd">{E(m)}</div></figcaption></figure>'
        for navn, t, m in T.GRENER)
    doerer = "".join(
        f'<a class="doer skaaret" href="{p}{sti}"><div class="kicker liten">{E(k)}</div><div class="tittel">{E(t)}</div>'
        f'<p>{E(b)}</p><div class="les">{E(T.LES_MER)}</div></a>' for k, t, b, sti in T.DOERER)
    helt = f'''<section class="helt">
  <div><div class="kicker">{E(f["kicker"])}</div><h1 style="margin-top: 18px;">{E(f["tittel"])}</h1></div>
  <div class="hoeyre"><p class="ingress">{E(f["ingress"])}</p>
  <div class="knapper"><a class="knapp fylt" href="{p}fuglene/">{E(f["knapp_fugler"])}</a><a class="knapp" href="{p}slik-virker-det/">{E(f["knapp_hvordan"])}</a></div></div>
</section>'''
    veggen = vegg(dag, dager, p) if dag else ""
    return f'''{helt}
{veggen}
<section>{seksjonstopp(f["deler"], f'<a href="{p}slik-virker-det/">{E(f["deler_lenke"])}</a>')}<div class="rad-4">{deler}</div></section>
<section>{seksjonstopp(f["bilder"], f'<a href="{p}slik-bygde-jeg-det/">{E(f["bilder_lenke"])}</a>')}<div class="rad-3">{bilder}</div></section>
<section>{seksjonstopp(f["fugler"], f'<a href="{p}fuglene/">{E(f["fugler_lenke"])}</a>')}<div class="rad-4">{kort}</div></section>
<section>{seksjonstopp(f["grener"], f'<span>{E(f["grener_tekst"])}</span>')}<div class="rad-4">{grener}</div></section>
<section>{seksjonstopp(f["mer"])}<div class="rad-3">{doerer}</div></section>'''


def fuglene(arter: list[dict], p: str) -> str:
    f = T.FUGLENE
    farger = {"tre": "var(--groenn)", "vaatmark": "var(--blaa)", "bakke": "var(--gul)", "luft": "var(--blekk)"}
    seksjoner = []
    for key in ("tre", "vaatmark", "bakke", "luft"):
        liste = sorted([a for a in arter if a["habitat"] == key], key=lambda a: a["cm"])
        if not liste:
            continue
        figurer = "".join(
            f'<a href="{p}fuglene/{a["slug"]}/"><img src="{p}{a["_bilde"]}" alt="{E(a["norsk"])}" style="height: {round(150 * a["skala"])}px;" loading="lazy">'
            f'<span class="navn">{E(a["norsk"])}</span><span class="latin tall">{E(a["sci"])} · {a["cm"]:g} {E(f["cm"])}</span>'
            f'<span class="kunstner">{E(a["kunstner"])}</span></a>' for a in liste)
        antall = f'{len(liste)} {f["art"] if len(liste) == 1 else f["arter"]}'
        seksjoner.append(f'<section><div class="habitat"><span class="farge" style="background: {farger[key]};"></span>'
                         f'<h2 class="kicker">{E(T.HABITAT[key])} · {antall}</h2></div><div class="oppstilling">{figurer}</div></section>')
    return (f'<section><div class="kicker">{E(f["kicker"])}</div><h1 style="margin: 14px 0;">{E(f["tittel"])}</h1>'
            f'<p class="ingress">{E(f["ingress"])}</p></section>' + "".join(seksjoner))


def artside(a: dict, p: str) -> str:
    t = T.ART
    plass = t["plass_liten"] if a["skala"] < 0.8 else t["plass_stor"] if a["skala"] > 1.3 else t["plass_midt"]
    varianter = t["var_klatre"] if a["klatrende"] else t["var_fly"] if a["flyvende"] else ""
    rader = [(t["lengde"], t["lengde_tekst"].format(cm=f"{a['cm']:g}")), (t["habitat"], T.HABITAT.get(a["habitat"], a["habitat"]))]
    if a["overvintrer"] is not None:
        rader.append((t["overvintrer"], t["ja"] if a["overvintrer"] else t["nei"]))
    rader.append((t["paa_grenen"], t["paa_grenen_tekst"].format(skala=f"{a['skala']:.2f}".replace(".", ","), plass=plass)))
    forelegg = E(t["forelegg_tekst"].format(kunstner=a["kunstner"]))
    if a["side"]:
        forelegg += f' <a href="{E(a["side"])}">{E(t["se_plansjen"])}</a>'
    rader.append((t["forelegg"], forelegg))
    rader.append((t["tegnet"], t["tegnet_tekst"].format(varianter=varianter)))
    tabell = "".join(f'<tr><td>{E(k)}</td><td>{v if k == t["forelegg"] else E(v)}</td></tr>' for k, v in rader)
    smaa = ""
    if a["flyvende"]:
        smaa += (f'<figure><div class="kort liten skaaret"><img src="{p}bilder/fugler/{a["slug"]}-flyvende.webp" alt="{E(a["norsk"])}, {E(t["i_lufta"]).lower()}" loading="lazy"></div>'
                 f'<figcaption class="kicker liten" style="margin-top: 8px;">{E(t["i_lufta"])}</figcaption></figure>')
    if a["klatrende"]:
        smaa += (f'<figure><div class="kort liten skaaret"><img src="{p}bilder/fugler/{a["slug"]}-klatrende.webp" alt="{E(a["norsk"])}, {E(t["klatrende"]).lower()}" loading="lazy"></div>'
                 f'<figcaption class="kicker liten" style="margin-top: 8px;">{E(t["klatrende"])}</figcaption></figure>')
    return f'''<div class="sti"><a href="{p}fuglene/">{E(T.FUGLENE["kicker"])}</a> &rsaquo; {E(T.HABITAT.get(a["habitat"], a["habitat"]))} &rsaquo; {E(a["norsk"])}</div>
<section class="art">
  <div style="display: flex; flex-direction: column; gap: 22px;">
    <div class="kort stor skaaret"><img src="{p}{a["_stor"]}" alt="{E(a["norsk"])}"></div>
    <div class="rad-2" style="gap: 22px;">{smaa}</div>
  </div>
  <div class="tekst">
    <div class="kicker">{E(T.HABITAT.get(a["habitat"], a["habitat"]))}</div>
    <h1>{E(a["norsk"])}</h1>
    <div class="latin">{E(a["sci"])}</div>
    <table class="fakta tall">{tabell}</table>
    <div class="knapper"><a class="knapp" href="{p}fuglene/">{E(t["tilbake"])}</a><a class="knapp" href="{T.GITHUB}/tree/main/plates">{E(t["repo"])}</a></div>
  </div>
</section>'''


FONT = 'font-family="EB Garamond, Georgia, serif"'


def diagram() -> str:
    h = T.HVORDAN
    d = h["diagram"]; pl = h["piler"]
    def boks(x, y, w, hh, tittel, under):
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{hh}" rx="14" fill="#fff" stroke="#000" stroke-width="2.5"/>'
                f'<text x="{x + 24}" y="{y + 44}" {FONT} font-size="27" font-weight="600">{E(tittel)}</text>'
                f'<text x="{x + 24}" y="{y + 72}" {FONT} font-size="15" letter-spacing="2">{E(under.upper())}</text>')
    def pil(pts, tekst, tx, ty, dashed=False):
        dd = ' stroke-dasharray="6 6"' if dashed else ""
        return (f'<polyline points="{pts}" fill="none" stroke="#000" stroke-width="2"{dd} marker-end="url(#spiss)"/>'
                f'<text x="{tx}" y="{ty}" {FONT} font-size="15" letter-spacing="1">{E(tekst)}</text>')
    return f'''<svg viewBox="0 0 1312 470" role="img" aria-label="{E(h["delene"])}">
<defs><marker id="spiss" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#000"/></marker></defs>
{boks(20, 40, 300, 150, *d[0])}{boks(506, 20, 360, 200, *d[1])}{boks(1000, 40, 292, 150, *d[2])}{boks(20, 300, 300, 130, *d[3])}
<rect x="546" y="330" width="130" height="60" rx="10" fill="#fff" stroke="#000" stroke-width="1.5" stroke-dasharray="5 5"/>
<text x="611" y="366" {FONT} font-size="17" text-anchor="middle">api.met.no</text>
<rect x="706" y="330" width="130" height="60" rx="10" fill="#fff" stroke="#000" stroke-width="1.5" stroke-dasharray="5 5"/>
<text x="771" y="366" {FONT} font-size="17" text-anchor="middle">Gemini</text>
{pil("320,90 502,90", pl["upload"], 330, 78)}{pil("506,150 324,150", pl["config"], 330, 176)}
{pil("866,110 996,110", pl["display"], 872, 98)}{pil("320,365 460,365 460,225", pl["bilde"], 330, 352)}
{pil("611,220 611,326", pl["vaer"], 622, 280, True)}{pil("771,220 771,326", pl["gemini"], 782, 280, True)}
<text x="1000" y="230" {FONT} font-size="15" letter-spacing="1">{E(pl["rammen"][0])}</text>
<text x="1000" y="252" {FONT} font-size="15" letter-spacing="1">{E(pl["rammen"][1])}</text>
</svg>'''


def doegn() -> str:
    h = T.HVORDAN
    W, x0, x1, y = 1312, 40, 1272, 88
    X = lambda t: x0 + t / 24 * (x1 - x0)
    ticks = "".join(f'<line x1="{X(t):.1f}" y1="{y - (8 if t % 3 == 0 else 4)}" x2="{X(t):.1f}" y2="{y}" stroke="#000" stroke-width="1"/>'
                    + (f'<text x="{X(t):.1f}" y="{y + 22}" {FONT} font-size="14" text-anchor="middle">{t:02d}</text>' if t % 3 == 0 else "")
                    for t in range(25))
    merker = "".join(f'<polygon points="{X(t):.1f},{y - 12} {X(t) - 7:.1f},{y - 24} {X(t) + 7:.1f},{y - 24}" fill="#000"/>'
                     f'<text x="{X(t):.1f}" y="{y - 32}" {FONT} font-size="14" letter-spacing="1" text-anchor="middle">{E(tekst.upper())}</text>'
                     for t, tekst in h["doegn_merker"])
    a, b, c = h["doegn_tekst"]
    return f'''<svg viewBox="0 0 {W} 150" role="img" aria-label="{E(h["doegn"])}">
<rect x="{X(6):.1f}" y="{y - 8}" width="{X(11) - X(6):.1f}" height="8" fill="#000" fill-opacity="0.35"/>
<rect x="{X(11):.1f}" y="{y - 8}" width="{X(21) - X(11):.1f}" height="8" fill="#000" fill-opacity="0.12"/>
<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#000" stroke-width="1.5"/>{ticks}{merker}
<text x="{X(6):.1f}" y="{y + 44}" {FONT} font-size="13" letter-spacing="1">{E(a.upper())}</text>
<text x="{X(11) + 6:.1f}" y="{y + 44}" {FONT} font-size="13" letter-spacing="1">{E(b.upper())}</text>
<text x="{x1}" y="{y + 44}" {FONT} font-size="13" letter-spacing="1" text-anchor="end">{E(c.upper())}</text>
</svg>'''


def sol_graf() -> str:
    h = T.HVORDAN
    aar = datetime.date.today().year
    pts = []
    d = datetime.date(aar, 1, 1)
    while d.year == aar:
        t = lytteplan.soloppgang(d)
        pts.append((d.timetuple().tm_yday, t.hour * 60 + t.minute))
        d += datetime.timedelta(days=1)
    W, H, x0, x1, y0, y1 = 1312, 360, 60, 1292, 30, 300
    X = lambda dd: x0 + (dd - 1) / 364 * (x1 - x0)
    Y = lambda m: y0 + (m - 180) / (840 - 180) * (y1 - y0)
    linje = " ".join(f"{X(dd):.1f},{Y(m):.1f}" for dd, m in pts)
    oever = " ".join(f"{X(dd):.1f},{Y(m - lytteplan.FOER_SOL_MIN):.1f}" for dd, m in pts)
    under = " ".join(f"{X(dd):.1f},{Y(m + lytteplan.VINDU_TIMER * 60):.1f}" for dd, m in reversed(pts))
    mnd = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    ticks = "".join(f'<line x1="{X(dd):.1f}" y1="{y1}" x2="{X(dd):.1f}" y2="{y1 + 6}" stroke="#000" stroke-width="1"/>'
                    f'<text x="{X(dd) + 4:.1f}" y="{y1 + 22}" {FONT} font-size="14">{T.MAANEDER[i][:3]}</text>' for i, dd in enumerate(mnd))
    timer = "".join(f'<line x1="{x0}" y1="{Y(t * 60):.1f}" x2="{x1}" y2="{Y(t * 60):.1f}" stroke="#000" stroke-width="0.6" stroke-dasharray="2 5"/>'
                    f'<text x="{x0 - 10}" y="{Y(t * 60) + 5:.1f}" {FONT} font-size="14" text-anchor="end">{t:02d}</text>' for t in (4, 6, 8, 10, 12, 14))
    idag = datetime.date.today().timetuple().tm_yday
    tidligst = min(pts, key=lambda q: q[1]); senest = max(pts, key=lambda q: q[1])
    tid = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    sol, vindu, i_dag = h["sol_tekst"]
    return f'''<svg viewBox="0 0 {W} {H}" role="img" aria-label="{E(h["plan"])}">
{timer}<polygon points="{oever} {under}" fill="#000" fill-opacity="0.07"/>
<polyline points="{linje}" fill="none" stroke="#000" stroke-width="2.5"/>
<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="#000" stroke-width="1.5"/>{ticks}
<line x1="{X(idag):.1f}" y1="{y0}" x2="{X(idag):.1f}" y2="{y1}" stroke="#b3111f" stroke-width="1.5" stroke-dasharray="4 4"/>
<text x="{X(idag) + 8:.1f}" y="{y0 + 16}" {FONT} font-size="15" letter-spacing="1" fill="#b3111f">{E(i_dag.upper())}</text>
<text x="{X(tidligst[0]) - 20:.1f}" y="{Y(tidligst[1]) - 14:.1f}" {FONT} font-size="16" text-anchor="middle">{E(sol)} {tid(tidligst[1])}</text>
<text x="{X(senest[0]):.1f}" y="{Y(senest[1]) + 34:.1f}" {FONT} font-size="16" text-anchor="end">{tid(senest[1])}</text>
<text x="{X(20):.1f}" y="{Y(330):.1f}" {FONT} font-size="15" letter-spacing="1">{E(vindu.upper())}</text>
</svg>'''


def hvordan(p: str) -> str:
    h = T.HVORDAN
    komp = "".join(
        f'<div class="komponent"><div><div class="navn">{E(n)}</div><div class="sti-kode">{E(sti)}</div></div>'
        f'<div><div class="kicker liten">{E(h["hva"])}</div><p class="felt">{E(hva)}</p></div>'
        f'<div><div class="kicker liten">{E(h["hvorfor"])}</div><p class="felt">{E(hvorfor)}</p></div>'
        f'<div><div class="kicker liten">{E(h["kode"])}</div><a href="{T.GITHUB}/blob/main/{lenke}">{E(lenke)}</a></div></div>'
        for n, sti, hva, hvorfor, lenke in T.KOMPONENTER)
    trapper = "".join(
        f'<tr><td>{E(h["over"]) if v > 0 else E(h["under"])}{f" {v:.2f} V".replace(".", ",") if v > 0 else ""}</td><td>{fin} min</td><td>{dag} min</td></tr>'
        for v, fin, dag in lytteplan.TRAPPER)
    farger = "".join(f'<div class="farge-brikke"><div style="background: {hex_};"></div><span>{E(n)}</span></div>' for n, hex_ in T.FARGER)
    return f'''<section><div class="kicker">{E(h["kicker"])}</div><h1 style="margin: 14px 0;">{E(h["tittel"])}</h1><p class="ingress">{E(h["ingress"])}</p></section>
<section class="diagram">{diagram()}</section>
<section>{seksjonstopp(h["delene"])}{komp}</section>
<section class="graf">{seksjonstopp(h["doegn"])}{doegn()}</section>
<section class="graf">{seksjonstopp(h["plan"], f'<span>{E(h["plan_tekst"])}</span>')}
  <div class="plan">{sol_graf()}<table class="trapper tall"><tr><td colspan="3" class="kicker liten" style="border: 0; padding-left: 0;">{E(h["trapper"])}</td></tr>{trapper}
  <tr><td colspan="3" style="border: 0; padding-top: 10px; font-size: 15px;">{E(h["trapper_tekst"])}</td></tr></table></div></section>
<section>{seksjonstopp(h["farger"], f'<span>{E(h["farger_tekst"])}</span>')}
  <div class="farger"><div class="rekke">{farger}</div><p style="max-width: 52ch;">{E(h["farger_avsnitt"])}</p></div></section>'''


def valgene(p: str) -> str:
    v = T.VALGENE
    def blokk(tittel, pr, prv, m, va):
        trinn = "".join(f'<div class="trinn"><div>{E(k)}</div><div>{E(tekst)}</div></div>'
                        for k, tekst in ((v["problemet"], pr), (v["proevd"], prv), (v["maalt"], m), (v["valgt"], va)))
        return f'<div class="valg"><h2 class="tittel">{E(tittel)}</h2>{trinn}</div>'
    valg = "".join(blokk(*x) for x in T.VALG)
    forkastet = "".join(f'<div class="forkastet"><h3 class="tittel">{E(t)}</h3><p>{E(b)}</p></div>' for t, b in T.FORKASTET)
    return f'''<section><div class="kicker">{E(v["kicker"])}</div><h1 style="margin: 14px 0;">{E(v["tittel"])}</h1><p class="ingress">{E(v["ingress"])}</p></section>
<section><div class="rad-2" style="gap: 44px 56px;">{valg}</div></section>
<section>{seksjonstopp(v["forkastet"])}<div class="rad-4">{forkastet}</div></section>'''


def bygget(p: str) -> str:
    b = T.BYGGET
    bilder = "".join(foto(fil, tekst, p) for fil, tekst in T.FOTO_BYGGET)
    deler = "".join(f'<div class="deler-liste"><div class="navn">{E(n)}</div><ul>{"".join(f"<li>{E(x)}</li>" for x in liste)}</ul></div>'
                    for n, liste in T.DELELISTE)
    stroem = "".join(f'<tr><td>{E(k)}</td><td class="tall">{E(v)}</td></tr>' for k, v in T.STROEM)
    tid = "".join(f'<div class="tidslinje"><div class="naar tall">{E(n)}</div><div>{E(t)}</div></div>' for n, t in T.TIDSLINJE)
    return f'''<section><div class="kicker">{E(b["kicker"])}</div><h1 style="margin: 14px 0;">{E(b["tittel"])}</h1><p class="ingress">{E(b["ingress"])}</p></section>
<section><div class="rad-3">{bilder}</div></section>
<section>{seksjonstopp(b["deleliste"])}<div class="rad-4">{deler}</div></section>
<section><div class="rad-2" style="gap: 40px 56px;">
  <div>{seksjonstopp(b["stroem"])}<table class="stroem">{stroem}</table><p style="margin-top: 20px;">{E(b["stroem_avsnitt"])}</p></div>
  <div>{seksjonstopp(b["tidslinje"])}{tid}</div></div></section>
<section>{seksjonstopp(b["verktoey"])}<p class="ingress">{E(b["verktoey_avsnitt"])}</p></section>'''


# ---------------------------------------------------------------- bygg
def skriv(rel: str, tekst: str) -> None:
    sti = os.path.join(UT, rel)
    os.makedirs(os.path.dirname(sti), exist_ok=True)
    with open(sti, "w", encoding="utf-8") as f:
        f.write(tekst)


def main() -> int:
    os.makedirs(UT, exist_ok=True)
    shutil.copyfile(os.path.join(HER, "stil.css"), os.path.join(UT, "stil.css"))
    os.makedirs(os.path.join(UT, "fonter"), exist_ok=True)
    for fil in os.listdir(os.path.join(HER, "fonter")):
        shutil.copyfile(os.path.join(HER, "fonter", fil), os.path.join(UT, "fonter", fil))

    arter = hent_arter()
    fugler = os.path.join(ROT, "plates", "fugler")
    for a in arter:
        a["_bilde"] = bilde(os.path.join(fugler, a["slug"] + ".png"), f"bilder/fugler/{a['slug']}.webp", 600)
        a["_stor"] = bilde(os.path.join(fugler, a["slug"] + ".png"), f"bilder/fugler/{a['slug']}-stor.webp", 1000)
        for variant in ("flyvende", "klatrende"):
            if a[variant]:
                bilde(os.path.join(fugler, f"{a['slug']}-{variant}.png"), f"bilder/fugler/{a['slug']}-{variant}.webp", 700)
    for navn, _, _ in T.GRENER:
        bilde(os.path.join(ROT, "plates", "maler", navn + ".png"), f"bilder/grener/{navn}.webp", 900)
    for fil, _ in T.FOTO + T.FOTO_BYGGET:
        bilde(os.path.join(HER, "bilder", fil), f"bilder/foto/{fil}", 1400)

    dager = hent_dager()
    for d in dager:
        d["_stor"] = bilde(d["_png"], f"bilder/dager/{d['dato']}.webp", 1200)
        d["_liten"] = bilde(d["_png"], f"bilder/dager/{d['dato']}-liten.webp", 240)
    nyeste = dager[-1] if dager else None

    skriv("index.html", side("", forside(nyeste, dager, arter), 0, None, None, nyeste["_stor"] if nyeste else None))
    for d in dager:
        u, dato = dato_tekst(d["dato"])
        skriv(f"dag/{d['dato']}/index.html", side(f"{u} {dato}", vegg(d, dager, "../../"), 2, None, None, d["_stor"]))
    skriv("fuglene/index.html", side(T.FUGLENE["tittel"], fuglene(arter, "../"), 1, "fuglene/"))
    for a in arter:
        skriv(f"fuglene/{a['slug']}/index.html",
              side(a["norsk"], artside(a, "../../"), 2, "fuglene/", f'{a["norsk"]}, {a["sci"]}. {T.BESKRIVELSE}', a["_stor"]))
    skriv("slik-virker-det/index.html", side(T.HVORDAN["tittel"], hvordan("../"), 1, "slik-virker-det/"))
    skriv("valgene/index.html", side(T.VALGENE["tittel"], valgene("../"), 1, "valgene/"))
    skriv("slik-bygde-jeg-det/index.html", side(T.BYGGET["tittel"], bygget("../"), 1, "slik-bygde-jeg-det/"))
    with open(os.path.join(UT, ".nojekyll"), "w") as f:
        f.write("")
    print(f"OK: {len(arter)} arter, {len(dager)} dager -> {UT}" + ("" if Image else "  (uten Pillow: originalbildene kopiert)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
