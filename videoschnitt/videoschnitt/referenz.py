"""Referenz — aus einem Vorbild-Video herauslesen, was sich messen lässt, um daraus einen Stil zu bauen.

Gemessen wird: wie dicht geschnitten ist (Bildwechsel je Minute), wie lang die Sprechpausen sind
(daraus folgen ``pause_ab`` und ``pause_ziel``), wie laut der Ton ist. Dazu kommen Standbilder —
Schrift, Farbe, Lage und Wortzahl der Untertitel liest das Gehirn von den Bildern ab.

Was hier nicht geht: Das Modell sieht Standbilder, keinen Film. Bewegung, Übergänge und Musik bleiben
ungeprüft.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path

from . import medien, plan as planmodul, transkript, umgebung

HOECHSTENS = 180  # Sekunden, die ausgewertet werden — genug für den Takt, schnell genug zum Warten


def auswerten(video: Path, bilder: int = 8, ordner: Path | None = None) -> dict:
    info = medien.auskunft(video)
    ordner = ordner or video.with_name(video.stem + ".referenz")
    ordner.mkdir(parents=True, exist_ok=True)
    laenge = min(info["dauer"], HOECHSTENS)

    dateien = []
    for i in range(max(1, bilder)):
        t = laenge * (i + 0.5) / max(1, bilder)
        ziel = ordner / f"bild-{i + 1:02d}.jpg"
        lauf = subprocess.run([umgebung.ffmpeg(), "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                               "-vf", "scale=-2:'min(960,ih)'", "-q:v", "3", str(ziel)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if lauf.returncode == 0 and ziel.is_file():
            dateien.append({"datei": str(ziel), "sekunde": round(t, 1)})

    # Bildwechsel: Bilder, die sich stark vom vorigen unterscheiden. Sprung-Schnitte im selben Bild
    # (Jump-Cuts) fallen hier kaum auf — die zeigen sich an den Sprechpausen weiter unten.
    lauf = subprocess.run([umgebung.ffmpeg(), "-hide_banner", "-v", "info", "-t", str(laenge), "-i", str(video), "-an",
                           "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    wechsel = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", lauf.stderr)]

    lauf = subprocess.run([umgebung.ffmpeg(), "-hide_banner", "-v", "info", "-t", str(laenge), "-i", str(video), "-vn",
                           "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    treffer = re.search(r'"input_i"\s*:\s*"(-?[0-9.]+)"', lauf.stderr)
    lautheit = float(treffer.group(1)) if treffer else None

    sprache: dict = {}
    try:
        wav = ordner / "ton.wav"
        subprocess.run([umgebung.ffmpeg(), "-y", "-v", "error", "-t", str(laenge), "-i", str(video), "-map", "0:a:0", "-vn",
                        "-ac", "1", "-ar", "16000", "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", str(wav)],
                       check=True, capture_output=True)
        ts = transkript.transkribieren(wav, None, "auto")
        transkript.verankern(ts["woerter"], medien.Huelle.aus_wav(wav))
        w = ts["woerter"]
        luecken = sorted(b["von"] - a["bis"] for a, b in zip(w, w[1:]) if b["von"] > a["bis"])
        if len(luecken) >= 10:
            p90 = luecken[int(len(luecken) * 0.9)]
            sprache = {
                "sprache": ts["sprache"],
                "woerter_je_minute": round(len(w) / laenge * 60),
                "luecke_mittel": round(statistics.median(luecken), 2),
                "luecke_p90": round(p90, 2),
                "luecke_laengste": round(luecken[-1], 2),
                # Im fertigen Vorbild ist die längste Pause das, was dort stehen bleiben durfte.
                "vorschlag": {"pause_ab": round(max(0.25, min(1.5, luecken[-1] + 0.1)), 2),
                              "pause_ziel": round(max(0.08, min(0.8, p90)), 2)},
            }
        wav.unlink(missing_ok=True)
    except Exception as e:  # ohne Modell oder ohne Sprache bleibt dieser Teil einfach leer
        sprache = {"fehlt": str(e)[:200]}

    ergebnis = {
        "video": str(video), "ausgewertet_sekunden": round(laenge, 1), "breite": info["breite"], "hoehe": info["hoehe"],
        "bildrate": info["bildrate"], "bilder": dateien, "bildwechsel": len(wechsel),
        "bildwechsel_je_minute": round(len(wechsel) / laenge * 60, 1) if laenge else 0,
        "lautheit_lufs": lautheit, "sprache": sprache, "ordner": str(ordner),
    }
    planmodul.schreiben(ordner / "referenz.json", ergebnis)
    return ergebnis


def meldung(e: dict) -> list[str]:
    def k(x) -> str:
        return str(x).replace(".", ",")

    zeilen = [
        f"REFERENZ  {Path(e['video']).name} · {e['breite']}×{e['hoehe']} · ausgewertet: die ersten {e['ausgewertet_sekunden']:.0f} s",
        f"BILD      {e['bildwechsel']} harte Bildwechsel ({k(e['bildwechsel_je_minute'])} je Minute) — Sprungschnitte im selben Bild "
        "und Zooms erkennt diese Messung nicht, die zeigen sich an den Sprechpausen",
        f"TON       {k(e['lautheit_lufs'])} LUFS" if e["lautheit_lufs"] is not None else "TON       Lautheit nicht messbar",
    ]
    s = e["sprache"]
    if "vorschlag" in s:
        zeilen.append(f"SPRACHE   {s['woerter_je_minute']} Wörter/Minute · Lücke zwischen Wörtern: mittel {k(s['luecke_mittel'])} s, "
                      f"90 % unter {k(s['luecke_p90'])} s, längste {k(s['luecke_laengste'])} s")
        zeilen.append(f"VORSCHLAG schnitt.pause_ab = {s['vorschlag']['pause_ab']} · schnitt.pause_ziel = {s['vorschlag']['pause_ziel']}")
    else:
        zeilen.append("SPRACHE   nicht auswertbar (" + s.get("fehlt", "zu wenig Sprache") + ")")
    zeilen.append(f"BILDER    {len(e['bilder'])} Stück in {e['ordner']}: "
                  + ", ".join(f"{Path(b['datei']).name} ({k(b['sekunde'])} s)" for b in e["bilder"]))
    zeilen.append("WEITER    Die Bilder ansehen (Schrift, Farben, Lage, Wörter je Zeile der Untertitel). Dann eine Stil-Datei anlegen: "
                  "{\"erbt\": \"reel\", …nur die Abweichungen…}, mit vorbereiten --stil <Name oder Pfad> und rendern --probe 10 ausprobieren. "
                  "Du siehst Standbilder, keinen Film: Bewegung, Übergänge und Musik bleiben ungeprüft.")
    return zeilen
