"""Gleichlauf-Prüfung — bleiben Bild und Ton nach vielen Schnitten zusammen?

Das Testvideo blitzt in festem Takt zwei Bilder lang weiß und piept im selben Moment. Der Takt zählt
in Bildern (alle 30 Bilder bei 30 und 29,97 Bildern/s), nicht in Sekunden — bei gebrochenen Bildraten
fiele eine volle Sekunde sonst zwischen zwei Bilder, und die Quelle selbst wäre schon ungenau.
Es wird mit dem echten Render-Weg des Moduls zerschnitten (gleiche Kodierung wie im Betrieb).
Im Ergebnis werden Blitze und Pieptöne wiedergefunden und ihr Abstand gemessen. Verlangt ist:
kein Blitz und kein Piep fehlt, jeder Abstand liegt unter einem halben Bild, nichts läuft weg.

Aufruf:  python tests\\gleichlauf_pruefen.py [--stuecke 40] [--bildrate 30000/1001] [--tonrate 16000] [--versatz 0.3]
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import numpy as np  # noqa: E402

from videoschnitt import medien, rendern, stil as stilmodul, umgebung  # noqa: E402

DAUER = 120


def takt(fps: Fraction) -> int:
    """Alle wie viele Bilder es blitzt."""
    return round(fps)


def quelle_bauen(ziel: Path, fps: Fraction, tonrate: int, versatz: float) -> None:
    """Blitz und Piep im Takt. ``versatz`` lässt die Tonspur später anfangen (wie beim Handy)."""
    rate = f"{fps.numerator}/{fps.denominator}"
    abstand = float(Fraction(takt(fps)) / fps)   # Sekunden zwischen zwei Blitzen
    bild = (f"color=c=black:s=540x960:r={rate}:d={DAUER},"
            f"drawbox=x=0:y=0:w=iw:h=ih:c=white:t=fill:enable='lt(mod(n\\,{takt(fps)})\\,2)'")
    ton = f"aevalsrc='0.6*sin(2*PI*1000*t)*lt(mod(t\\,{abstand:.9f})\\,0.06)':s=48000:d={DAUER}"
    roh = ziel.with_suffix(".roh.mkv")
    for befehl in (
        [umgebung.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", bild, "-f", "lavfi", "-i", ton,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(roh)],
        # Zweiter Schritt: Ton auf die gewünschte Rate und um den Versatz nach hinten — erst die ersten
        # ``versatz`` Sekunden Ton wegnehmen, dann die Spur so spät beginnen lassen. Der Inhalt bleibt synchron.
        [umgebung.ffmpeg(), "-y", "-v", "error", "-i", str(roh), "-ss", f"{versatz}", "-itsoffset", f"{versatz}", "-i", str(roh),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", str(tonrate), str(ziel)],
    ):
        lauf = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if lauf.returncode != 0:
            raise SystemExit("Die Testquelle ließ sich nicht bauen:\n" + lauf.stderr[-500:])
    roh.unlink(missing_ok=True)


def stuecke_waehlen(anzahl: int, fps: Fraction, saat: int = 7) -> list[dict]:
    """Zufällige Stücke in Reihenfolge; jedes enthält genau einen Blitz samt Piep."""
    zufall = random.Random(saat)
    schlaege = sorted(zufall.sample(range(1, int(DAUER * fps / takt(fps)) - 1), anzahl))
    aus = []
    for s in schlaege:
        blitz = s * takt(fps)
        k = blitz - zufall.randint(3, max(4, int(fps * 0.4)))
        m = blitz + zufall.randint(6, max(7, int(fps * 0.5)))
        if aus and k <= aus[-1]["m"]:
            k = aus[-1]["m"] + 1
        aus.append({"k": k, "m": m, "von": float(k / fps), "bis": float(m / fps)})
    return aus


def blitze_finden(video: Path, fps: Fraction) -> list[float]:
    lauf = subprocess.run([umgebung.ffmpeg(), "-v", "error", "-i", str(video), "-vf", "scale=8:8,format=gray",
                           "-f", "rawvideo", "-"], capture_output=True)
    hell = np.frombuffer(lauf.stdout, dtype=np.uint8).reshape(-1, 64).mean(axis=1) > 128
    anfang = np.flatnonzero(hell & ~np.concatenate(([False], hell[:-1])))
    return [float(n / fps) for n in anfang]


def piepser_finden(video: Path) -> list[float]:
    lauf = subprocess.run([umgebung.ffmpeg(), "-v", "error", "-i", str(video), "-map", "0:a:0", "-ac", "1", "-ar", "48000",
                           "-f", "s16le", "-"], capture_output=True)
    ton = np.abs(np.frombuffer(lauf.stdout, dtype=np.int16).astype(np.float32))
    laut = ton > 0.3 * ton.max()
    stellen = np.flatnonzero(laut)
    if stellen.size == 0:
        return []
    anfang = stellen[np.concatenate(([True], np.diff(stellen) > 4800))]   # neuer Piep nach 0,1 s Ruhe
    return [float(x / 48000) for x in anfang]


def pruefen(stuecke: int, fps: Fraction, tonrate: int, versatz: float, lautheit: bool = True) -> dict:
    ordner = HIER / "daten" / "gleichlauf"
    ordner.mkdir(parents=True, exist_ok=True)
    quelle, ziel = ordner / "quelle.mp4", ordner / "ergebnis.mp4"
    quelle_bauen(quelle, fps, tonrate, versatz)
    info = medien.auskunft(quelle)
    stil = stilmodul.laden("standard")
    stil["untertitel"]["an"] = False
    stil["ton"]["lautheit"] = lautheit
    segmente = stuecke_waehlen(stuecke, fps)
    plan = {"quelle": str(quelle), "auskunft": info, "bildrate": f"{fps.numerator}/{fps.denominator}", "stil": stil,
            "woerter": [], "segmente": segmente}
    ergebnis = rendern.rendern(plan, ordner, ziel, untertitel=False)

    blitze, piepser = blitze_finden(ziel, fps), piepser_finden(ziel)
    # Erwartet: Jeder Blitz liegt im fertigen Video dort, wo sein Bild nach dem Zusammenschieben landet.
    erwartet, pos = [], 0
    for s in segmente:
        blitzbild = next(n for n in range(s["k"], s["m"]) if n % takt(fps) == 0)
        erwartet.append(float((pos + blitzbild - s["k"]) / fps))
        pos += s["m"] - s["k"]
    ein_bild = float(1 / fps)
    abstaende = [(p - b) * 1000 for b, p in zip(blitze, piepser)]
    lage = [(b - e) * 1000 for b, e in zip(blitze, erwartet)]
    aus = {
        "stuecke": stuecke, "bildrate": str(fps), "tonrate_quelle": tonrate, "ton_versatz_quelle": versatz,
        "quelle_bild_start": info["bild_start"], "quelle_ton_start": info["ton_start"],
        "encoder": ergebnis["encoder"], "lautheit": lautheit,
        "blitze": len(blitze), "piepser": len(piepser), "erwartet": len(erwartet),
        "abstand_ms_min": round(min(abstaende), 2) if abstaende else None,
        "abstand_ms_mittel": round(float(np.median(abstaende)), 2) if abstaende else None,
        "abstand_ms_max": round(max(abstaende), 2) if abstaende else None,
        "blitz_lage_ms_max": round(max(abs(x) for x in lage), 2) if lage else None,
        "nachmessung_ok": ergebnis["ok"], "dauer_bild": ergebnis["dauer_bild"], "dauer_ton": ergebnis["dauer_ton"],
    }
    aus["ok"] = (len(blitze) == len(piepser) == len(erwartet) and ergebnis["ok"]
                 and max(abs(x) for x in abstaende) <= ein_bild * 500 and aus["blitz_lage_ms_max"] <= 1.0)
    return aus


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--stuecke", type=int, default=40)
    p.add_argument("--bildrate", default="30")
    p.add_argument("--tonrate", type=int, default=48000)
    p.add_argument("--versatz", type=float, default=0.0)
    p.add_argument("--ohne-lautheit", action="store_true")
    a = p.parse_args()
    e = pruefen(a.stuecke, Fraction(a.bildrate), a.tonrate, a.versatz, not a.ohne_lautheit)
    print(json.dumps(e, ensure_ascii=False, indent=1))
    print("GLEICHLAUF " + ("IN ORDNUNG" if e["ok"] else "NICHT IN ORDNUNG"))
    sys.exit(0 if e["ok"] else 1)
