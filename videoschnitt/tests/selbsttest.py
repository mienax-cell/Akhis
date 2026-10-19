"""Selbsttest — das ganze Modul einmal über den echten Weg, mit Zahlen. Kostet nichts.

Geprüft wird nicht, ob die Programme „Erfolg“ melden, sondern was am Ende dasteht:

1. Schnittplan gegen die Wahrheit der Testsprache (was bleiben soll, ist ganz da; was raus soll, ist weg)
2. Das fertige Video wird nachgemessen (Länge, Größe, Bild und Ton gleich lang)
3. Das fertige Video wird noch einmal transkribiert: Füllwörter und Versprecher dürfen nicht mehr
   zu hören sein, die gewollte Wiederholung muss noch da sein
4. Untertitel: dasselbe Bild mit und ohne — der Unterschied muss im Untertitel-Band liegen und Gelb
   (das gesprochene Wort) und Weiß (die anderen) enthalten
5. Lautheit des Ergebnisses
6. Ändern des Plans von Hand wirkt und lässt sich zurücksetzen

Aufruf:  python tests\\selbsttest.py          (baut das Testvideo, falls es fehlt)
Ergebnis: Tabelle im Fenster, dazu tests\\daten\\selbsttest-ergebnis.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

HIER = Path(__file__).resolve().parent
MODUL = HIER.parent
DATEN = HIER / "daten"
sys.path.insert(0, str(MODUL))
sys.path.insert(0, str(HIER))

import numpy as np  # noqa: E402

from videoschnitt import medien, schnittlogik as sl, transkript, umgebung  # noqa: E402
import plan_gegen_wahrheit  # noqa: E402
import testvideo_bauen  # noqa: E402

ZEILEN: list[dict] = []


def punkt(name: str, ok: bool, wert: str) -> None:
    ZEILEN.append({"name": name, "ok": bool(ok), "wert": wert})
    print(f"  {'ok    ' if ok else 'FEHLER'} {name}: {wert}", flush=True)


def schnitt(*args: str) -> tuple[int, str]:
    lauf = subprocess.run([sys.executable, str(MODUL / "schnitt.py"), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return lauf.returncode, lauf.stderr + lauf.stdout   # Fortschritt (stderr) zuerst, die Ergebniszeilen zuletzt


def bild(video: Path, sekunde: float) -> np.ndarray:
    """Ein Bild als Zahlenfeld (Höhe × Breite × 3) — ffmpeg schreibt rohe Farbwerte in ein Rohr."""
    info = medien.auskunft(video)
    lauf = subprocess.run([umgebung.ffmpeg(), "-v", "error", "-ss", f"{sekunde:.3f}", "-i", str(video), "-frames:v", "1",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(lauf.stdout, dtype=np.uint8).reshape(info["hoehe"], info["breite"], 3).astype(np.int16)


def lautheit(video: Path) -> float | None:
    lauf = subprocess.run([umgebung.ffmpeg(), "-hide_banner", "-v", "info", "-i", str(video), "-vn", "-af",
                           "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    treffer = re.search(r'"input_i"\s*:\s*"(-?[0-9.]+)"', lauf.stderr)
    return float(treffer.group(1)) if treffer else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.monotonic()
    video, wahr_datei = DATEN / "testvideo.mp4", DATEN / "testsprache.wahrheit.json"
    if not video.is_file() or not wahr_datei.is_file():
        print("Baue das Testvideo …")
        testvideo_bauen.bauen(DATEN)
    wahrheit = json.loads(wahr_datei.read_text(encoding="utf-8-sig"))
    ordner = DATEN / "testvideo.schnitt"
    roh_vorher = (video.stat().st_size, video.stat().st_mtime_ns)
    for alt in DATEN.glob("testvideo-*.mp4"):
        alt.unlink()

    print("1 · Umgebung und Schnittplan")
    code, aus = schnitt("pruefen")
    punkt("Umgebung bereit", code == 0, aus.strip().splitlines()[-1])
    code, aus = schnitt("vorbereiten", str(video), "--stil", "standard", "--neu")
    punkt("vorbereiten läuft durch", code == 0, "ja" if code == 0 else aus[-300:])
    if code != 0:
        return abschluss(t0)
    plan = json.loads((ordner / "schnittplan.json").read_text(encoding="utf-8"))
    befunde = plan_gegen_wahrheit.vergleichen(plan, wahrheit)
    schlecht = [b for b in befunde if not b["ok"]]
    # Ein Stück darf knapp daneben liegen: wo ein Wort ohne Pause in ein Füllwort übergeht, sitzt die
    # Grenze von Whisper auf etwa 50 ms genau — bekannt und in der README benannt.
    punkt("Plan gegen Wahrheit", len(schlecht) <= 1 and all(b["soll_raus"] is False for b in schlecht),
          f"{len(befunde) - len(schlecht)} von {len(befunde)} Stücken stimmen"
          + ("".join(f" · „{b['text'][:24]}“ {b['befund']}" for b in schlecht)))
    st = plan["statistik"]["stueck"]
    punkt("Füllwörter gefunden", st["fuellwort"] == wahrheit["zaehler"]["fuellwoerter"],
          f"{st['fuellwort']} von {wahrheit['zaehler']['fuellwoerter']}")
    offen = [k for k in plan["kandidaten"] if not k["angewandt"]]
    punkt("Gewollte Wiederholung nur als Vorschlag", any("Ich will mehr" in k["text"] for k in offen) or not any(
        "Ich will mehr" in k["text"] for k in plan["kandidaten"]), f"{len(offen)} unsichere Stelle(n), nicht geschnitten")

    print("2 · Rendern und Nachmessen")
    code, aus = schnitt("rendern", str(video))
    ergebnis = DATEN / "testvideo-geschnitten.mp4"
    punkt("rendern läuft durch", code == 0 and ergebnis.is_file(), "ja" if code == 0 else aus[-400:])
    if code != 0 or not ergebnis.is_file():
        return abschluss(t0)
    info = medien.auskunft(ergebnis)
    soll = plan["statistik"]["dauer_ergebnis"]
    punkt("Länge wie geplant", abs(info["dauer"] - soll) <= 1 / 30 + 0.001, f"{info['dauer']:.3f} s, geplant {soll:.3f} s")
    punkt("Größe", (info["breite"], info["hoehe"]) == (1080, 1920), f"{info['breite']}×{info['hoehe']}")
    lufs = lautheit(ergebnis)
    schrift_ok = "Arial-Black" in aus and "ACHTUNG" not in aus
    punkt("Schrift wirklich Arial Black (kein stiller Ersatz)", schrift_ok, aus.strip().splitlines()[-1][-70:])
    punkt("Lautheit am Ziel", lufs is not None and abs(lufs - plan["stil"]["ton"]["ziel_lufs"]) <= 2.0,
          f"{lufs} LUFS, Ziel {plan['stil']['ton']['ziel_lufs']}")

    print("3 · Das Ergebnis noch einmal anhören (transkribieren)")
    wav = DATEN / "ergebnis-ton.wav"
    medien.ton_herausziehen(ergebnis, wav)
    gehoert = transkript.transkribieren(wav, "de", "auto", "auto", plan["stil"]["transkription"].get("hinweis"))
    wav.unlink(missing_ok=True)
    tokens = [sl.norm(w["w"]) for w in gehoert["woerter"]]
    text = " ".join(tokens)
    fuell = [t for t in tokens if sl.ist_fuellwort(t, set())]
    punkt("Keine Füllwörter mehr zu hören", not fuell, "keine" if not fuell else ", ".join(fuell))
    for wendung, soll_n, name in (("wir haben", 1, "Wiederholung „wir haben“ nur einmal"),
                                  ("der wichtigste punkt", 1, "Abgebrochener Anlauf weg"),
                                  ("am ende zählt nur", 1, "Doppelter Satz nur einmal"),
                                  ("ich will mehr", 2, "Gewollte Wiederholung noch zweimal da")):
        n = text.count(wendung)
        punkt(name, n == soll_n, f"{n}× gehört, erwartet {soll_n}×")
    sauber = [sl.norm(x) for x in wahrheit["text_sauber"].split()]
    gleich = SequenceMatcher(None, tokens, sauber, autojunk=False).ratio()
    punkt("Wortlaut wie der saubere Text", gleich >= 0.93, f"{gleich:.1%} gleich ({len(tokens)} gehört, {len(sauber)} erwartet)")

    print("4 · Untertitel im Bild")
    mit, ohne = DATEN / "testvideo-mit.mp4", DATEN / "testvideo-ohne.mp4"
    c1, a1 = schnitt("rendern", str(video), "--probe", "6", "--ausgabe", str(mit))
    c2, a2 = schnitt("rendern", str(video), "--probe", "6", "--ausgabe", str(ohne), "--ohne-untertitel")
    punkt("Probe mit und ohne Untertitel", c1 == 0 and c2 == 0, "ja" if c1 == 0 and c2 == 0 else (a1 + a2)[-300:])
    if c1 == 0 and c2 == 0:
        u = plan["stil"]["untertitel"]
        hoehe = info["hoehe"]
        mitte = round(u["position"] * hoehe)
        band = slice(max(0, mitte - round(0.09 * hoehe)), min(hoehe, mitte + round(0.09 * hoehe)))
        for sekunde in (1.0, 3.5):
            a, b = bild(mit, sekunde), bild(ohne, sekunde)
            anders = np.abs(a - b).sum(axis=2) > 60
            im_band, ausserhalb = int(anders[band].sum()), int(anders.sum() - anders[band].sum())
            gelb = int(((a[..., 0] > 200) & (a[..., 1] > 180) & (a[..., 2] < 90) & anders).sum())
            weiss = int(((a.min(axis=2) > 215) & anders).sum())
            punkt(f"Untertitel bei {sekunde} s", im_band > 3000 and ausserhalb < im_band * 0.02 and gelb > 500 and weiss > 500,
                  f"{im_band} Bildpunkte im Band geändert, {ausserhalb} außerhalb, davon gelb {gelb}, weiß {weiss}")
    for datei in (mit, ohne):
        datei.unlink(missing_ok=True)

    print("5 · Plan von Hand ändern")
    vorher = plan["statistik"]["dauer_ergebnis"]
    code, aus = schnitt("aendern", str(video), "--weg", "0-5")
    nachher = json.loads((ordner / "schnittplan.json").read_text(encoding="utf-8"))["statistik"]["dauer_ergebnis"]
    punkt("Wörter 0–5 rausnehmen kürzt", code == 0 and nachher < vorher - 1.0, f"{vorher:.2f} s → {nachher:.2f} s")
    code, aus = schnitt("aendern", str(video), "--zuruecksetzen")
    zurueck = json.loads((ordner / "schnittplan.json").read_text(encoding="utf-8"))["statistik"]["dauer_ergebnis"]
    punkt("Zurücksetzen stellt den Stand wieder her", code == 0 and abs(zurueck - vorher) < 0.001, f"{zurueck:.2f} s")
    code, aus = schnitt("aendern", str(video), "--weg", "999999")
    punkt("Unsinnige Eingabe wird abgelehnt", code == 1 and "FEHLER" in aus, aus.strip().splitlines()[-1][:90])
    punkt("Rohvideo unverändert", (video.stat().st_size, video.stat().st_mtime_ns) == roh_vorher, f"{roh_vorher[0]} Bytes, Zeitstempel gleich")
    return abschluss(t0)


def abschluss(t0: float) -> int:
    schlecht = [z for z in ZEILEN if not z["ok"]]
    dauer = time.monotonic() - t0
    print(f"\n{len(ZEILEN) - len(schlecht)} von {len(ZEILEN)} Prüfungen bestanden in {dauer:.0f} s."
          + ("" if not schlecht else "  NICHT BESTANDEN: " + "; ".join(z["name"] for z in schlecht)))
    DATEN.mkdir(exist_ok=True)
    (DATEN / "selbsttest-ergebnis.json").write_text(
        json.dumps({"bestanden": not schlecht, "sekunden": round(dauer, 1), "pruefungen": ZEILEN}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
