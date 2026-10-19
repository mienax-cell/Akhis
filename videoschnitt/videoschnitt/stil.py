"""Stile — ein Stil ist eine JSON-Datei in ``stile\\``. Ein neuer Stil ist eine neue Datei, sonst nichts.

``standard.json`` ist vollständig und maßgeblich; es gibt keine zweite Kopie der Vorgaben im Code.
Jeder andere Stil erbt davon (oder über ``"erbt"`` von einem anderen) und nennt nur seine Abweichungen.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import ModulFehler

STILE_ORDNER = Path(__file__).resolve().parent.parent / "stile"
GRUNDSTIL = "standard"

FORMATE = {"original": None, "9:16": (9, 16), "4:5": (4, 5), "1:1": (1, 1), "16:9": (16, 9)}


class StilFehler(ModulFehler):
    pass


def _lesen(pfad: Path) -> dict:
    try:
        # utf-8-sig: schluckt ein BOM, falls ein Editor eines davorgesetzt hat
        daten = json.loads(pfad.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise StilFehler(f"Stil {pfad.name} ist kein gültiges JSON: {e}") from e
    if not isinstance(daten, dict):
        raise StilFehler(f"Stil {pfad.name}: oberste Ebene muss ein Objekt sein")
    return daten


def _mischen(basis: dict, ueber: dict) -> dict:
    """Tief mischen: Objekte werden zusammengeführt, alles andere (auch Listen) ersetzt."""
    aus = dict(basis)
    for k, v in ueber.items():
        if isinstance(v, dict) and isinstance(aus.get(k), dict):
            aus[k] = _mischen(aus[k], v)
        else:
            aus[k] = v
    return aus


def _ohne_hilfe(d: dict) -> dict:
    """Schlüssel mit ``_`` vorn sind Notizen für den Menschen und zählen nicht."""
    return {k: (_ohne_hilfe(v) if isinstance(v, dict) else v) for k, v in d.items() if not k.startswith("_")}


def finden(name_oder_pfad: str) -> Path:
    """Stil über seinen Namen (Groß/klein egal) oder einen Pfad zu einer JSON-Datei finden."""
    kandidat = Path(name_oder_pfad)
    if kandidat.suffix.lower() == ".json" and kandidat.is_file():
        return kandidat.resolve()
    gesucht = name_oder_pfad.strip().lower()
    for pfad in sorted(STILE_ORDNER.glob("*.json")):
        if pfad.stem.lower() == gesucht:
            return pfad
    vorhanden = ", ".join(p.stem for p in sorted(STILE_ORDNER.glob("*.json"))) or "keiner"
    if kandidat.suffix.lower() == ".json" or "/" in name_oder_pfad or "\\" in name_oder_pfad:
        raise StilFehler(f"Die Stil-Datei gibt es nicht: {kandidat}")
    raise StilFehler(f"Stil „{name_oder_pfad}“ gibt es nicht. Vorhanden: {vorhanden}. "
                     "(„Reel“, „Short“, „TikTok“ sind Wünsche, keine Stile — dazu passt reel oder schnell.)")


def laden(name_oder_pfad: str = GRUNDSTIL) -> dict:
    """Stil mit allem Geerbten laden. Ergebnis ist vollständig und geprüft; ``name`` steht dabei."""
    pfad = finden(name_oder_pfad)
    kette, gesehen = [], set()
    while True:
        if pfad in gesehen:
            raise StilFehler(f"Stil {pfad.stem} erbt im Kreis")
        gesehen.add(pfad)
        roh = _lesen(pfad)
        kette.append(roh)
        if pfad.stem.lower() == GRUNDSTIL and pfad.parent == STILE_ORDNER:
            break
        pfad = finden(roh.get("erbt") or GRUNDSTIL)

    stil: dict = {}
    for roh in reversed(kette):
        stil = _mischen(stil, _ohne_hilfe(roh))
    stil.pop("erbt", None)
    stil["name"] = finden(name_oder_pfad).stem

    probleme = pruefen(stil)
    fehler = [p for p in probleme if p.startswith("FEHLER")]
    if fehler:
        raise StilFehler(f"Stil {stil['name']}: " + "; ".join(fehler))
    stil["_warnungen"] = [p for p in probleme if not p.startswith("FEHLER")]
    return stil


def _schluessel(d: dict, vor: str = "") -> set[str]:
    aus = set()
    for k, v in d.items():
        if isinstance(v, dict):
            aus |= _schluessel(v, f"{vor}{k}.")
        else:
            aus.add(f"{vor}{k}")
    return aus


def pruefen(stil: dict) -> list[str]:
    """Tippfehler und unsinnige Werte finden. Liefert Zeilen, Fehler beginnen mit ``FEHLER``."""
    probleme: list[str] = []
    grund = _ohne_hilfe(_lesen(STILE_ORDNER / f"{GRUNDSTIL}.json"))
    bekannt = _schluessel(grund) | {"name", "erbt"}
    for s in sorted(_schluessel({k: v for k, v in stil.items() if not k.startswith("_")}) - bekannt):
        probleme.append(f"unbekannter Schlüssel „{s}“ (Tippfehler? wird ignoriert)")

    s, u, b, t, a, bd = (stil.get(k, {}) for k in ("schnitt", "untertitel", "bild", "ton", "ausgabe", "bindung"))

    def zahl(d: dict, k: str, lo: float, hi: float, wo: str) -> None:
        v = d.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            probleme.append(f"FEHLER {wo}.{k} = {v!r}, erwartet eine Zahl von {lo} bis {hi}")

    for k, lo, hi in (("pause_ab", 0.1, 30), ("pause_ziel", 0.0, 10), ("vorlauf", 0, 1), ("nachlauf", 0, 1),
                      ("anfang_luft", 0, 10), ("ende_luft", 0, 10)):
        zahl(s, k, lo, hi, "schnitt")
    if isinstance(s.get("pause_ab"), (int, float)) and isinstance(s.get("pause_ziel"), (int, float)) \
            and s["pause_ziel"] >= s["pause_ab"]:
        probleme.append("FEHLER schnitt.pause_ziel muss kleiner sein als schnitt.pause_ab")
    for k in ("fuellwoerter", "fuellwoerter_streng"):
        if not isinstance(s.get(k), list) or not all(isinstance(x, str) for x in s.get(k, [])):
            probleme.append(f"FEHLER schnitt.{k} muss eine Liste von Wörtern sein")

    for k, lo, hi in (("groesse", 0.02, 0.25), ("umriss", 0, 0.3), ("schatten", 0, 0.3), ("position", 0.05, 0.95),
                      ("position_quer", 0.05, 0.95),
                      ("breite_max", 0.3, 1.0), ("woerter_max", 1, 12), ("zeichen_max", 4, 80),
                      ("aktiv_groesse", 1.0, 1.5)):
        zahl(u, k, lo, hi, "untertitel")
    if u.get("art") not in ("farbe", "aufbau"):
        probleme.append(f"FEHLER untertitel.art = {u.get('art')!r}, erlaubt: farbe, aufbau")
    if u.get("kontrast") not in ("aus", "auto"):
        probleme.append(f"FEHLER untertitel.kontrast = {u.get('kontrast')!r}, erlaubt: aus, auto")
    zahl(u, "kommend", 0, 1, "untertitel")
    zahl(u, "umriss_weich", 0, 0.3, "untertitel")
    if u.get("betonen") not in ("aus", "zahlen"):
        probleme.append(f"FEHLER untertitel.betonen = {u.get('betonen')!r}, erlaubt: aus, zahlen")
    zahl(bd, "fortschritt_hoehe", 0.001, 0.05, "bindung")
    zahl(b, "zoom_takt", 0, 60, "bild")
    zahl(b, "zoom_mitte_y", 0, 1, "bild")
    zahl(t, "raumklang", 0, 1, "ton")
    zahl(t, "effekte", 0, 2, "ton")
    for k in ("farbe", "farbe_aktiv", "farbe_dunkel", "farbe_betont", "farbe_betont_2", "umriss_farbe"):
        v = u.get(k)
        if not (isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:])):
            probleme.append(f"FEHLER untertitel.{k} = {v!r}, erwartet #RRGGBB")

    if b.get("format") not in FORMATE:
        probleme.append(f"FEHLER bild.format = {b.get('format')!r}, erlaubt: {', '.join(FORMATE)}")
    if b.get("anpassen") not in ("zuschneiden", "einpassen"):
        probleme.append(f"FEHLER bild.anpassen = {b.get('anpassen')!r}, erlaubt: zuschneiden, einpassen")
    if b.get("fps") != "original" and not (isinstance(b.get("fps"), (int, float)) and 10 <= b["fps"] <= 60):
        probleme.append(f"FEHLER bild.fps = {b.get('fps')!r}, erlaubt: \"original\" oder 10 bis 60")
    zahl(b, "kante_max", 240, 7680, "bild")
    z = b.get("zoom_bei_schnitt")
    if not (z == 0 or (isinstance(z, (int, float)) and 1.0 <= z <= 1.5)):
        probleme.append(f"FEHLER bild.zoom_bei_schnitt = {z!r}, erlaubt: 0 (aus) oder 1.0 bis 1.5")

    v = bd.get("fortschritt_farbe")
    if not (isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:])):
        probleme.append(f"FEHLER bindung.fortschritt_farbe = {v!r}, erwartet #RRGGBB")
    zahl(t, "ziel_lufs", -30, -5, "ton")
    zahl(t, "blende_ms", 0, 100, "ton")
    if a.get("encoder") not in ("auto", "nvenc", "x264"):
        probleme.append(f"FEHLER ausgabe.encoder = {a.get('encoder')!r}, erlaubt: auto, nvenc, x264")
    zahl(a, "qualitaet", 10, 35, "ausgabe")
    zahl(a, "ton_kbit", 64, 320, "ausgabe")
    return probleme


def liste() -> list[tuple[str, str]]:
    """Alle Stile mit ihrer Beschreibung — abgelesen aus dem Ordner, nicht gepflegt."""
    aus = []
    for pfad in sorted(STILE_ORDNER.glob("*.json")):
        try:
            aus.append((pfad.stem, str(_lesen(pfad).get("beschreibung", ""))))
        except StilFehler as e:
            aus.append((pfad.stem, f"DEFEKT: {e}"))
    return aus
