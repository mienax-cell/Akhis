"""Schrift — wie breit ein Text im Untertitel wird, ohne ihn zu rendern.

libass misst die Schriftgröße anders als fast alles sonst: ``Fontsize`` ist nicht die Geviert-Höhe,
sondern die Höhe von Oberkante bis Unterkante der Schrift (``usWinAscent + usWinDescent`` aus der
Schriftdatei). Arial Black ist deshalb bei ``Fontsize 100`` nur 71 Pixel „groß“. Wer das nicht
einrechnet, schätzt jede Zeile ein Drittel zu breit. Gemessen gegen libass: „HAMBURG“ in Arial Black
bei Fontsize 50 — 201 Pixel gerechnet, 201 Pixel im Bild.

Gerechnet wird Zeichen für Zeichen ohne Unterschneidung, denn so setzt libass in der Voreinstellung.

Pillow ist freiwillig. Fehlt es (oder die Schriftdatei), gilt ein vorsichtiger Schätzwert.
"""
from __future__ import annotations

import functools
import os
import struct
from pathlib import Path

# Vorschub je Zeichen als Anteil der ASS-Schriftgröße, wenn nicht gemessen werden kann. Gemessen an
# 200 deutschen Wörtern in fetten Großbuchstaben: im Mittel 0,49, einzelne Wörter bis 0,63.
SCHAETZ_FAKTOR = 0.63


def schrift_ordner() -> list[Path]:
    orte = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]
    return [o for o in orte if o.is_dir()]


@functools.cache
def _verzeichnis() -> dict[str, Path]:
    """Alle installierten Schriften: Name (klein) → Datei. Leer, wenn Pillow fehlt."""
    try:
        from PIL import ImageFont
    except ImportError:
        return {}
    namen: dict[str, Path] = {}
    for ordner in schrift_ordner():
        for datei in sorted(ordner.iterdir()):
            if datei.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            try:
                familie, schnitt = ImageFont.truetype(str(datei), 10).getname()
            except Exception:
                continue
            if not familie:
                continue
            voll = f"{familie} {schnitt or ''}".strip().lower()
            for schluessel in {voll, voll.removesuffix(" regular")}:
                namen.setdefault(schluessel, datei)
    return namen


def datei_finden(familie: str, fett: bool = False, datei: str | None = None) -> Path | None:
    """Die Datei zu einem Schriftnamen, wie er im Stil steht („Arial Black“, „Segoe UI“ + fett)."""
    if datei and Path(datei).is_file():
        return Path(datei)
    verzeichnis = _verzeichnis()
    name = familie.strip().lower()
    for kandidat in ([f"{name} bold"] if fett else []) + [name]:
        if kandidat in verzeichnis:
            return verzeichnis[kandidat]
    return None


@functools.cache
def _geviert_anteil(datei: Path) -> float | None:
    """Geviert je ASS-Schriftgröße: unitsPerEm / (usWinAscent + usWinDescent), direkt aus der Datei."""
    try:
        d = datei.read_bytes()
        start = struct.unpack(">I", d[12:16])[0] if d[:4] == b"ttcf" else 0
        anzahl = struct.unpack(">H", d[start + 4:start + 6])[0]
        tabellen = {}
        for i in range(anzahl):
            kennung, _, ort, _ = struct.unpack(">4sIII", d[start + 12 + 16 * i:start + 28 + 16 * i])
            tabellen[kennung] = ort
        geviert = struct.unpack(">H", d[tabellen[b"head"] + 18:tabellen[b"head"] + 20])[0]
        auf, ab = struct.unpack(">HH", d[tabellen[b"OS/2"] + 74:tabellen[b"OS/2"] + 78])
        return geviert / (auf + ab) if auf + ab else None
    except (KeyError, struct.error, OSError, IndexError):
        return None


@functools.cache
def _messer(datei: Path):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(str(datei), 1000)
    except Exception:
        return None


@functools.cache
def _vorschub(datei: Path, zeichen: str) -> float:
    """Vorschub eines Zeichens als Anteil der ASS-Schriftgröße."""
    return _messer(datei).getlength(zeichen) / 1000.0 * _geviert_anteil(datei)


def breite(text: str, groesse: float, familie: str, fett: bool = False, datei: str | None = None) -> tuple[float, bool]:
    """Breite des Textes in Pixeln bei ASS-Schriftgröße ``groesse``. Zweiter Wert: wirklich gemessen?"""
    ort = datei_finden(familie, fett, datei)
    if ort is not None and _geviert_anteil(ort) and _messer(ort) is not None:
        return sum(_vorschub(ort, z) for z in text) * groesse, True
    return len(text) * SCHAETZ_FAKTOR * groesse, False
