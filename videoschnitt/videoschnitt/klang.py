"""Kleine Klänge zu den Bildeffekten — gerechnet, nicht geladen.

Ein Bildeffekt ohne Ton wirkt wie ein Stummfilm, ein lauter Ton stiehlt der Stimme die Aufmerksamkeit.
Darum gibt es hier nur wenige, kurze, leise Klänge, und sie werden *unter* die fertig eingepegelte Stimme
gemischt. Jeder Klang entsteht aus Formeln (Sinus, Rauschen, Hüllkurve): keine Fremddateien, keine Lizenzen,
bei jedem Lauf dasselbe.

Ein Ereignis ist ``{"zeit": 12.4, "art": "wusch", "staerke": 0.8}`` — die Zeit zählt im *fertigen* Video.
"""
from __future__ import annotations

import functools
import json
import wave
from pathlib import Path

import numpy as np

from . import ModulFehler

RATE = 48000

# Spitze je Klang in dB unter Vollausschlag, bei ton.effekte = 1 und staerke = 1. Die Stimme liegt nach dem
# Einpegeln mit ihren Spitzen bei etwa −3 dB; alles hier bleibt mindestens 15 dB darunter.
SPITZE_DB = {"wusch": -19.0, "pop": -18.0, "tick": -27.0, "klick": -23.0, "glocke": -22.0, "tiefe": -15.0,
             "aufstieg": -22.0, "schnipp": -24.0}
ARTEN = tuple(SPITZE_DB)


class KlangFehler(ModulFehler):
    pass


def _zeit(sekunden: float) -> np.ndarray:
    return np.arange(int(sekunden * RATE)) / RATE


def _rauschen(n: int, saat: int) -> np.ndarray:
    return np.random.default_rng(saat).uniform(-1.0, 1.0, n)


def _bandpass(x: np.ndarray, mitte: np.ndarray, guete: float) -> np.ndarray:
    """Ein mitlaufender Bandpass (Zustandsfilter): ``mitte`` ist die Frequenz je Abtastwert."""
    f = 2.0 * np.sin(np.pi * np.minimum(mitte, RATE / 6.5) / RATE)
    q = 1.0 / guete
    aus = np.empty_like(x)
    tief = band = 0.0
    for i in range(len(x)):
        tief += f[i] * band
        hoch = x[i] - tief - q * band
        band += f[i] * hoch
        aus[i] = band
    return aus


def _rand(x: np.ndarray, ms: float = 4.0) -> np.ndarray:
    """Anfang und Ende weich, damit nichts knackt."""
    n = min(len(x) // 2, int(ms / 1000 * RATE))
    if n > 0:
        x[:n] *= np.linspace(0.0, 1.0, n)
        x[-n:] *= np.linspace(1.0, 0.0, n)
    return x


@functools.lru_cache(maxsize=None)
def klang(art: str) -> np.ndarray:
    """Ein Klang als Zahlenreihe, Spitze 1."""
    if art == "wusch":            # Luftzug: Rauschen, dessen Tonhöhe steigt — für alles, was ins Bild fliegt
        t = _zeit(0.40)
        x = t / t[-1]
        y = _bandpass(_rauschen(len(t), 1), 280.0 * 11.0 ** x, 1.3) * x ** 1.4 * (1.0 - x) ** 0.7
    elif art == "aufstieg":       # Anlauf vor einem großen Wechsel, bricht am Ziel ab
        t = _zeit(0.62)
        x = t / t[-1]
        y = _bandpass(_rauschen(len(t), 2), 420.0 * 10.0 ** x, 2.2) * x ** 2.2
        y += 0.25 * np.sin(2 * np.pi * np.cumsum(180.0 * 4.0 ** x) / RATE) * x ** 3
    elif art == "pop":            # weicher Tropfen: ein Wort oder eine Zahl springt auf
        t = _zeit(0.12)
        f = 190.0 + 430.0 * np.exp(-t / 0.018)
        y = np.sin(2 * np.pi * np.cumsum(f) / RATE) * (1.0 - np.exp(-t / 0.002)) * np.exp(-t / 0.032)
    elif art == "tick":           # ein Zählschritt
        t = _zeit(0.03)
        y = np.sin(2 * np.pi * 2200.0 * t) * np.exp(-t / 0.004) + 0.3 * _rauschen(len(t), 3) * np.exp(-t / 0.0012)
    elif art == "klick":          # Schalter: zwei Zählschritte dicht hintereinander
        t = _zeit(0.06)
        y = np.sin(2 * np.pi * 3000.0 * t) * np.exp(-t / 0.003)
        s = np.clip(t - 0.024, 0.0, None)
        y += 0.6 * np.sin(2 * np.pi * 1800.0 * s) * np.exp(-s / 0.004) * (t >= 0.024)
    elif art == "schnipp":        # Schere: kurzes helles Rauschen
        t = _zeit(0.07)
        y = _bandpass(_rauschen(len(t), 4), np.full(len(t), 5200.0), 0.9) * np.exp(-t / 0.012)
    elif art == "glocke":         # heller Schlusston
        t = _zeit(1.1)
        y = sum(a * np.sin(2 * np.pi * 784.0 * k * t) * np.exp(-t / (0.30 / k ** 0.6))
                for k, a in ((1.0, 1.0), (2.0, 0.35), (3.01, 0.18), (4.2, 0.07)))
        y *= 1.0 - np.exp(-t / 0.004)
    elif art == "tiefe":          # dumpfer Schlag: eine ganze Szene landet
        t = _zeit(0.5)
        f = 52.0 + 70.0 * np.exp(-t / 0.045)
        phase = 2 * np.pi * np.cumsum(f) / RATE
        y = (np.sin(phase) + 0.22 * np.sin(2 * phase)) * (1.0 - np.exp(-t / 0.003)) * np.exp(-t / 0.13)
    else:
        raise KlangFehler(f"Den Klang „{art}“ gibt es nicht. Es gibt: {', '.join(ARTEN)}")
    y = _rand(np.asarray(y, dtype=np.float64))
    return (y / max(1e-9, float(np.abs(y).max()))).astype(np.float32)


def lesen(datei: Path) -> list[dict]:
    """Eine Ereignisliste aus einer JSON-Datei, geprüft."""
    try:
        roh = json.loads(Path(datei).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise KlangFehler(f"Die Klang-Liste lässt sich nicht lesen: {datei} ({e})") from None
    if isinstance(roh, dict):
        roh = roh.get("klaenge", [])
    liste = []
    for nr, e in enumerate(roh if isinstance(roh, list) else []):
        if not isinstance(e, dict) or e.get("art") not in ARTEN or not isinstance(e.get("zeit"), (int, float)):
            raise KlangFehler(f"Eintrag {nr + 1} der Klang-Liste braucht „zeit“ (Sekunden im fertigen Video) und "
                              f"„art“ ({', '.join(ARTEN)}).")
        liste.append({"zeit": float(e["zeit"]), "art": e["art"], "staerke": float(e.get("staerke", 1.0))})
    return liste


def spur(ereignisse: list[dict], dauer: float, staerke: float = 1.0) -> np.ndarray:
    """Alle Ereignisse auf einer Tonspur von ``dauer`` Sekunden. Was über das Ende ragt, wird abgeschnitten."""
    aus = np.zeros(int(dauer * RATE) + 1, dtype=np.float32)
    for e in ereignisse:
        y = klang(e["art"]) * (10 ** (SPITZE_DB[e["art"]] / 20) * max(0.0, float(e.get("staerke", 1.0))) * staerke)
        a = int(round(e["zeit"] * RATE))
        if a >= len(aus) or a + len(y) <= 0:
            continue
        y = y[max(0, -a):]
        a = max(0, a)
        aus[a:a + len(y)] += y[:len(aus) - a]
    return np.clip(aus, -1.0, 1.0)


def schreiben(pfad: Path, ton: np.ndarray) -> None:
    with wave.open(str(pfad), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes((ton * 32767).astype(np.int16).tobytes())
