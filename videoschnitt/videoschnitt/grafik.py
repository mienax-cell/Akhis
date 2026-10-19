"""Bewegungsgrafik über ein gefilmtes Video legen.

Die Szenen sind eine Webseite (HTML mit ein paar data-Angaben, siehe ``grafik\\motor.js``). Der Browser, der
schon auf dem Rechner ist, lichtet sie Bild für Bild mit durchsichtigem Grund ab; heraus kommt ``grafik.mov``
im Arbeitsordner, genau so lang wie das fertige Video. ``rendern`` legt die Datei dann über das Bild — unter
die Untertitel.

Die Seite bekommt die Wörter des Schnittplans mit ihren Zeiten im *fertigen* Video. Ändert sich danach der
Schnitt, passt die Grafik nicht mehr; ``rendern`` merkt das und verlangt ein neues Ablichten.

Gebraucht wird Node ab Version 22 und Edge oder Chrome. Geladen oder installiert wird nichts.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from . import ModulFehler, schnittlogik as sl

ABLICHTEN = Path(__file__).resolve().parent.parent / "grafik" / "ablichten.mjs"
MOTOR = ABLICHTEN.with_name("motor.js")
FILM = "grafik.mov"
DATEN = "grafik-daten.json"
AUSKUNFT = "grafik-auskunft.json"


class GrafikFehler(ModulFehler):
    pass


def _stuecke(plan: dict) -> list[list[int]]:
    return [[s["k"], s["m"]] for s in plan["segmente"]]


def daten(plan: dict, breite: int, hoehe: int) -> dict:
    """Was die Seite wissen muss: Länge, Bildgröße und jedes Wort, das bleibt, mit seiner Zeit im fertigen Video."""
    achse = sl.Zeitachse(plan["segmente"])
    woerter = []
    for w in plan["woerter"]:
        ort = None if w.get("weg") else achse.wort(w["von"], w["bis"])
        if ort is not None:
            woerter.append({"i": w["i"], "w": w["w"], "t": round(ort[0], 3), "e": round(ort[1], 3)})
    return {"dauer": round(achse.dauer, 4), "fps": float(Fraction(plan["bildrate"])), "breite": breite, "hoehe": hoehe,
            "akzent": plan["stil"]["untertitel"].get("farbe_betont"), "woerter": woerter, "stuecke": _stuecke(plan)}


def ablichten(plan: dict, ordner: Path, szenen: Path, breite: int, hoehe: int, bild: float | None = None) -> dict:
    """Die Seite ablichten: ganz (``grafik.mov``) oder nur ein Standbild der Sekunde ``bild`` (PNG, durchsichtig)."""
    node = shutil.which("node")
    if not node:
        raise GrafikFehler("Für die Bewegungsgrafik fehlt Node (ab Version 22). Mit Chefs Ja: winget install --id OpenJS.NodeJS.LTS -e")
    if not szenen.is_file():
        raise GrafikFehler(f"Die Szenen-Seite gibt es nicht: {szenen}")
    d = daten(plan, breite, hoehe)
    if not d["woerter"]:
        raise GrafikFehler("Im Schnittplan bleibt kein Wort übrig — ohne Wörter hat die Grafik keinen Takt.")
    (ordner / DATEN).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8", newline="\n")
    befehl = [node, str(ABLICHTEN), str(szenen), "--daten", str(ordner / DATEN), "--motor", str(MOTOR), "--durchsichtig",
              "--breite", str(breite), "--hoehe", str(hoehe), "--fps", str(plan["bildrate"])]
    if bild is not None:
        ziel = ordner / f"grafik-{bild:06.2f}.png"
        befehl += ["--bild", f"{bild}", "--aus", str(ziel)]
    else:
        ziel = ordner / FILM
        befehl += ["--aus", str(ziel), "--dauer", f"{d['dauer']:.4f}", "--auskunft", str(ordner / AUSKUNFT)]
    lauf = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if lauf.returncode != 0 or not ziel.is_file():
        raise GrafikFehler("Das Ablichten ist gescheitert:\n" + (lauf.stderr or lauf.stdout).strip()[-700:])
    klaenge = []
    if bild is None and (ordner / AUSKUNFT).is_file():
        klaenge = (json.loads((ordner / AUSKUNFT).read_text(encoding="utf-8")) or {}).get("klaenge", [])
    return {"ziel": ziel, "dauer": d["dauer"], "woerter": len(d["woerter"]), "klaenge": len(klaenge), "meldung": lauf.stdout.strip()}


def vorhanden(plan: dict, ordner: Path) -> tuple[Path, list[dict]] | None:
    """Die abgelichtete Grafik und ihre Klänge, wenn es sie gibt. Passt sie nicht mehr zum Schnitt, ist das ein Fehler."""
    film = ordner / FILM
    if not film.is_file():
        return None
    try:
        d = json.loads((ordner / DATEN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if d.get("stuecke") != _stuecke(plan):
        raise GrafikFehler("Die Grafik im Arbeitsordner passt nicht mehr zum Schnittplan (der Schnitt hat sich geändert). "
                           "Neu ablichten mit „schnitt.py grafik …“ — oder ohne sie rendern: --ohne-grafik.")
    try:
        klaenge = (json.loads((ordner / AUSKUNFT).read_text(encoding="utf-8")) or {}).get("klaenge", [])
    except (OSError, ValueError):
        klaenge = []
    return film, klaenge
