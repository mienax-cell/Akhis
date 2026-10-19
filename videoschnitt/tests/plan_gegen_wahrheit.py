"""Hält den Schnittplan des Testvideos gegen die Wahrheit der Testsprache.

Für jedes gesprochene Stück ist bekannt, ob es bleiben soll. Geprüft wird auf die Millisekunde,
wie viel davon in den geplanten Segmenten liegt: Was bleiben soll, darf nicht angeschnitten sein;
was raus soll, darf nicht mehr zu hören sein.

Aufruf:  python tests\\plan_gegen_wahrheit.py [Arbeitsordner] [Wahrheit.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
FEHLT_HOECHSTENS = 0.04   # so viel darf einem Stück, das bleibt, an den Rändern fehlen (gut ein Bild)
REST_HOECHSTENS = 0.08    # so viel darf von einem Stück, das raus soll, noch drin sein


def vergleichen(plan: dict, wahrheit: dict) -> list[dict]:
    segmente = [(s["von"], s["bis"]) for s in plan["segmente"]]

    def drin(a: float, b: float) -> float:
        return sum(max(0.0, min(b, y) - max(a, x)) for x, y in segmente)

    befunde = []
    for t in wahrheit["teile"]:
        if t["art"] == "pause":
            continue
        a, b = t["start_ms"] / 1000, t["ende_ms"] / 1000
        d = drin(a, b)
        if t["entfernen"]:
            ok, text = d <= REST_HOECHSTENS, ("raus" if d <= REST_HOECHSTENS else f"NOCH {d * 1000:.0f} ms DRIN")
        else:
            fehlt = (b - a) - d
            ok, text = fehlt <= FEHLT_HOECHSTENS, ("ganz" if fehlt <= FEHLT_HOECHSTENS else f"ES FEHLEN {fehlt * 1000:.0f} ms")
        befunde.append({"text": t["text"], "art": t["art"], "soll_raus": t["entfernen"], "dauer": b - a, "drin": d,
                        "ok": ok, "befund": text})
    # Lange Pausen: zwischen zwei Stücken, die bleiben, darf höchstens pause_ab stehen bleiben.
    return befunde


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ordner = Path(sys.argv[1]) if len(sys.argv) > 1 else HIER / "daten" / "testvideo.schnitt"
    wahr = Path(sys.argv[2]) if len(sys.argv) > 2 else HIER / "daten" / "testsprache.wahrheit.json"
    befunde = vergleichen(json.loads((ordner / "schnittplan.json").read_text(encoding="utf-8")),
                          json.loads(wahr.read_text(encoding="utf-8-sig")))
    for b in befunde:
        print(f"  {'ok    ' if b['ok'] else 'FEHLER'} {b['text'][:44]:<44} {b['dauer']:5.2f} s, davon drin {b['drin']:5.2f} s  → {b['befund']}")
    schlecht = sum(not b["ok"] for b in befunde)
    print(f"{len(befunde) - schlecht} von {len(befunde)} Stücken stimmen.")
    sys.exit(1 if schlecht else 0)
