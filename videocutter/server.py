#!/usr/bin/env python
"""Videocutter — die App zum Schnitt-Werkzeug: Skript nach Regelwerk, Aufnahme, Schnitt mit Anzeige, Motion-Video.

    python videocutter\\server.py                  startet die App auf http://127.0.0.1:8765 und öffnet den Browser
    python videocutter\\server.py --ohne-browser   nur den Server

Alles läuft auf diesem Rechner. Nur das Skript-Schreiben geht über die claude-Kommandozeile an Claude (mit dem
Zugang, der schon eingerichtet ist) — dabei geht das Thema hinaus, nie Ton oder Bild. Geschnitten wird mit
videoschnitt\\schnitt.py; das Werkzeug selbst wird nicht verändert.
"""
from __future__ import annotations

import argparse
import difflib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HIER = Path(__file__).resolve().parent
PAKET = HIER.parent
MODUL = PAKET / "videoschnitt"
SCHNITT = MODUL / "schnitt.py"
ABLICHTEN = MODUL / "grafik" / "ablichten.mjs"
WEB = HIER / "web"
REGELN = HIER / "regelwerk"
PROJEKTE = HIER / "projekte"
PORT = 8765
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UMGEBUNG = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

sys.path.insert(0, str(MODUL))
from videoschnitt import grafik as grafikmodul  # noqa: E402

TYPEN = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
         ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".wav": "audio/wav", ".m4a": "audio/mp4",
         ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}
VIDEO_ENDUNGEN = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi", ".mts", ".3gp"}
TON_ENDUNGEN = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".webm", ".aac", ".flac"}

SAEULEN = {
    "mythen": "Säule 1 · Mythen & Fehler — einen typischen Finanzfehler aufdecken, den fast jeder macht",
    "anleitung": "Säule 2 · Konkrete Anleitung — Schritt für Schritt, zum Speichern und Teilen",
    "klartext": "Säule 3 · Klartext & Meinung — Einordnung einer Finanz-News oder eines schlechten Finanz-Tipps",
    "alltag": "Praktischer Tipp für den Alltag (Freitag im Wochenplan)",
}
STILE = {"reel", "schnell", "standard", "ruhig", "magi"}
SPRECHTEMPO = 2.5          # Wörter je Sekunde, gesprochen
SPERRE = threading.RLock()


class Fehler(Exception):
    """Etwas, das der Mensch vor dem Bildschirm verstehen soll."""

    def __init__(self, text: str, code: int = 400):
        super().__init__(text)
        self.code = code


# --------------------------------------------------------------------------------------- Werkzeuge finden

def claude_pfad() -> str | None:
    """Die claude-Kommandozeile. Unter Windows lieber die echte .exe als den .cmd-Umweg (der kürzt lange Aufrufe)."""
    gefunden = shutil.which("claude")
    if not gefunden:
        return None
    exe = Path(gefunden).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(exe) if exe.is_file() else gefunden


def browser_pfad() -> str | None:
    for p in (os.environ.get("MAGI_BROWSER"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if p and Path(p).is_file():
            return p
    return None


_zustand: dict = {}
_zustand_sperre = threading.Lock()


def zustand(neu: bool = False) -> dict:
    """Was auf dem Rechner bereitsteht. ``pruefen`` lädt Whisper — deshalb nur einmal und dann gemerkt."""
    with _zustand_sperre:
        if not _zustand or neu:
            _zustand.clear()
            _zustand.update(_zustand_messen())
        return dict(_zustand)


def _zustand_messen() -> dict:
    punkte, ok = [], False
    try:
        lauf = subprocess.run([sys.executable, str(SCHNITT), "pruefen", "--json"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=UMGEBUNG, creationflags=OHNE_FENSTER, timeout=120)
        ergebnis = json.loads(lauf.stdout)
        punkte, ok = ergebnis["punkte"], ergebnis["ok"]
    except (subprocess.SubprocessError, ValueError, KeyError) as e:
        punkte = [{"name": "schnitt.py", "ok": False, "pflicht": True, "wert": str(e)[:200], "hilfe": ""}]
    return {"schnitt": {"ok": ok, "punkte": punkte}, "claude": bool(claude_pfad()), "node": bool(shutil.which("node")),
            "browser": bool(browser_pfad())}


# --------------------------------------------------------------------------------------- Projekte

def _jetzt() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _json_schreiben(pfad: Path, daten) -> None:
    neben = pfad.with_suffix(pfad.suffix + ".neu")
    neben.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    neben.replace(pfad)


def projekt_ordner(pid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{3,90}", pid or ""):
        raise Fehler("Unbekanntes Projekt.", 404)
    ordner = PROJEKTE / pid
    if not (ordner / "projekt.json").is_file():
        raise Fehler("Das Projekt gibt es nicht (mehr).", 404)
    return ordner


def projekt_lesen(pid: str) -> dict:
    with SPERRE:
        return json.loads((projekt_ordner(pid) / "projekt.json").read_text(encoding="utf-8"))


def projekt_aendern(pid: str, aenderung) -> dict:
    """Lesen, ändern, schreiben — unter einer Sperre, weil Aufträge nebenher laufen."""
    with SPERRE:
        p = projekt_lesen(pid)
        aenderung(p)
        p["geaendert"] = _jetzt()
        _json_schreiben(projekt_ordner(pid) / "projekt.json", p)
        return p


def _kurzname(text: str, laenge: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text.lower().replace("ß", "ss"))
    text = "".join(z for z in text if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:laenge].strip("-") or "projekt"


def projekt_neu(titel: str = "") -> dict:
    titel = (titel or "").strip() or "Neues Video"
    pid = f"{datetime.now():%Y-%m-%d}-{_kurzname(titel)}-{uuid.uuid4().hex[:4]}"
    ordner = PROJEKTE / pid
    ordner.mkdir(parents=True)
    p = {"id": pid, "titel": titel, "erstellt": _jetzt(), "geaendert": _jetzt(), "skript": None, "quelle": None,
         "einstellungen": {"stil": "reel", "format": "original", "skript_betonung": True, "schlagzeile": True, "vorbild": False},
         "vorbild": None, "ergebnisse": [], "motion": None, "auftrag": None}
    _json_schreiben(ordner / "projekt.json", p)
    return p


def projekte_liste() -> list[dict]:
    liste = []
    if PROJEKTE.is_dir():
        for datei in PROJEKTE.glob("*/projekt.json"):
            try:
                p = json.loads(datei.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            liste.append({"id": p["id"], "titel": p["titel"], "geaendert": p.get("geaendert", ""), "skript": bool(p.get("skript")),
                          "quelle": bool(p.get("quelle")), "ergebnis": bool(p.get("ergebnisse")),
                          "motion": bool((p.get("motion") or {}).get("ergebnis"))})
    return sorted(liste, key=lambda x: x["geaendert"], reverse=True)


def im_projekt(pid: str, relativ: str) -> Path:
    """Eine Datei im Projektordner — nie außerhalb."""
    ordner = projekt_ordner(pid).resolve()
    pfad = (ordner / unquote(relativ)).resolve()
    if ordner not in pfad.parents and pfad != ordner:
        raise Fehler("Diese Datei liegt nicht im Projekt.", 403)
    return pfad


def _freier_name(ordner: Path, stamm: str, endung: str) -> Path:
    """aufnahme-1.webm, aufnahme-2.webm … — eine neue Aufnahme ersetzt nie eine alte."""
    n = 1
    while any(ordner.glob(f"{stamm}-{n}.*")):
        n += 1
    return ordner / f"{stamm}-{n}{endung}"


# --------------------------------------------------------------------------------------- Aufträge

AUFTRAEGE: dict[str, "Auftrag"] = {}


class Abgebrochen(Exception):
    pass


class Auftrag:
    """Eine lange Arbeit im Hintergrund. Die Oberfläche liest ihre Ereignisse als Strom mit (Server-Sent Events)."""

    def __init__(self, art: str, pid: str | None):
        self.id, self.art, self.pid = uuid.uuid4().hex[:12], art, pid
        self.ereignisse: list[dict] = []
        self.zu = False
        self.bedingung = threading.Condition()
        self.prozess: subprocess.Popen | None = None
        self.abgebrochen = False
        AUFTRAEGE[self.id] = self

    def melden(self, typ: str, **daten) -> None:
        with self.bedingung:
            self.ereignisse.append({"typ": typ, "zeit": round(time.time(), 2), **daten})
            if typ in ("fertig", "fehler"):
                self.zu = True
            self.bedingung.notify_all()

    def schritt(self, sid: str, status: str, text: str | None = None, **mehr) -> None:
        self.melden("schritt", id=sid, status=status, text=text, **mehr)

    def fortschritt(self, sid: str, anteil: float) -> None:
        self.melden("fortschritt", id=sid, anteil=round(max(0.0, min(1.0, anteil)), 3))

    def log(self, text: str) -> None:
        self.melden("log", text=text)

    def abbrechen(self) -> None:
        self.abgebrochen = True
        if self.prozess and self.prozess.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.prozess.pid)], capture_output=True, creationflags=OHNE_FENSTER)

    def starten(self, arbeit, *argumente) -> "Auftrag":
        if self.pid:
            projekt_aendern(self.pid, lambda p: p.__setitem__("auftrag", {"id": self.id, "art": self.art}))

        def lauf() -> None:
            try:
                ergebnis = arbeit(self, *argumente)
                self.melden("fertig", ergebnis=ergebnis)
            except Abgebrochen:
                self.melden("fehler", text="Abgebrochen.")
            except Fehler as e:
                self.melden("fehler", text=str(e))
            except Exception as e:  # noqa: BLE001 — jeder Fehler soll in der Oberfläche ankommen
                self.melden("fehler", text=f"Unerwarteter Fehler: {type(e).__name__}: {e}")
            finally:
                if self.pid:
                    try:
                        projekt_aendern(self.pid, lambda p: p.__setitem__("auftrag", None))
                    except Fehler:
                        pass
        threading.Thread(target=lauf, daemon=True).start()
        return self


def laufender_auftrag(pid: str) -> None:
    p = projekt_lesen(pid)
    a = AUFTRAEGE.get((p.get("auftrag") or {}).get("id", ""))
    if a and not a.zu:
        raise Fehler("In diesem Projekt läuft gerade schon etwas. Erst abwarten oder abbrechen.", 409)


_PROZENT = re.compile(r"(transkribiert|gerendert)\s+(\d+)\s*%")
_ABGELICHTET = re.compile(r"abgelichtet (\d+) von (\d+)")


def ausfuehren(a: Auftrag, sid: str, befehl: list[str], cwd: Path | None = None, eingabe: str | None = None,
               zeile_lesen=None) -> list[str]:
    """Einen Befehl laufen lassen, jede Zeile als Ereignis weiterreichen und Fortschritt herauslesen."""
    if a.abgebrochen:
        raise Abgebrochen()
    prozess = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE if eingabe is not None else subprocess.DEVNULL, text=True,
                               encoding="utf-8", errors="replace", cwd=str(cwd or PAKET), env=UMGEBUNG,
                               creationflags=OHNE_FENSTER)
    a.prozess = prozess
    zeilen: list[str] = []

    def lesen(strom) -> None:
        for roh in strom:
            zeile = roh.rstrip()
            if not zeile:
                continue
            zeilen.append(zeile)
            if zeile_lesen and zeile_lesen(zeile):
                continue
            m = _PROZENT.search(zeile)
            if m:
                a.fortschritt(sid, int(m.group(2)) / 100)
            m = _ABGELICHTET.search(zeile)
            if m:
                a.fortschritt(sid, int(m.group(1)) / max(1, int(m.group(2))))
            a.log(zeile)

    leser = [threading.Thread(target=lesen, args=(s,), daemon=True) for s in (prozess.stdout, prozess.stderr)]
    for t in leser:
        t.start()
    if eingabe is not None:
        prozess.stdin.write(eingabe)
        prozess.stdin.close()
    prozess.wait()
    for t in leser:
        t.join(timeout=5)
    a.prozess = None
    if a.abgebrochen:
        raise Abgebrochen()
    if prozess.returncode != 0:
        fehler = [z for z in zeilen if z.startswith(("FEHLER", "NICHT IN ORDNUNG"))]
        raise Fehler((" ".join(fehler) or "\n".join(zeilen[-4:]) or f"{Path(befehl[0]).name} ist gescheitert.")[:900])
    return zeilen


def schnitt(a: Auftrag, sid: str, *argumente: str) -> list[str]:
    return ausfuehren(a, sid, [sys.executable, str(SCHNITT), *argumente])


def ffmpeg(*argumente: str) -> None:
    lauf = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-v", "error", *argumente], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=OHNE_FENSTER)
    if lauf.returncode != 0:
        raise Fehler("ffmpeg ist gescheitert: " + (lauf.stderr or "").strip()[-400:])


def dauer_messen(pfad: Path) -> float:
    lauf = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(pfad)],
                          capture_output=True, text=True, creationflags=OHNE_FENSTER)
    try:
        return round(float(lauf.stdout.strip()), 2)
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------------------- Skript (Claude)

SKRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"type": "string", "description": "Arbeitstitel, höchstens 6 Wörter"},
        "abschnitte": {"type": "array", "items": {"type": "object", "properties": {
            "rolle": {"type": "string", "enum": ["hook", "mehrwert", "action"]},
            "text": {"type": "string", "description": "gesprochener Text mit *Betonung* und / für kurze Pausen"},
            "quelle": {"type": "string", "description": "Kurzform zum Einblenden, wenn der Abschnitt eine Zahl nennt"}},
            "required": ["rolle", "text"]}},
        "hook_alternativen": {"type": "array", "items": {"type": "string"}},
        "schlagzeile": {"type": "object", "properties": {"klein": {"type": "string"}, "gross": {"type": "string"},
                                                         "akzent": {"type": "string"}}, "required": ["gross"]},
        "caption": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "quellen": {"type": "array", "items": {"type": "object", "properties": {
            "aussage": {"type": "string"}, "quelle": {"type": "string"}, "stand": {"type": "string"}, "link": {"type": "string"}},
            "required": ["aussage", "quelle"]}},
        "annahmen": {"type": "array", "items": {"type": "string"}},
        "pruefung": {"type": "array", "items": {"type": "object", "properties": {
            "aussage": {"type": "string"}, "urteil": {"type": "string", "enum": ["ok", "umformuliert", "bitte_pruefen"]},
            "hinweis": {"type": "string"}}, "required": ["aussage", "urteil"]}},
    },
    "required": ["titel", "abschnitte", "schlagzeile", "caption", "keywords", "quellen", "pruefung"],
}


def system_prompt(faktencheck: bool) -> str:
    kollege = (REGELN / "kollege.md").read_text(encoding="utf-8")
    plan = (REGELN / "gemini-plan.md").read_text(encoding="utf-8")
    recherche = (
        "Du hast eine Websuche. Prüfe jede Zahl an der Originalquelle (DRV, Destatis, BiB, Bundesbank, BaFin, "
        "Verbraucherzentrale) und nimm die aktuellste belegbare Zahl. Nenne in „quellen“ Stand und Link. Findest du keinen "
        "Beleg, lass die Zahl weg. Halte die Recherche knapp: wenige gezielte Suchen, nur die Zahlen, die das Skript braucht."
        if faktencheck else
        "Du hast keine Websuche. Verwende nur Zahlen, die du sicher kennst, nenne den Stand, und setze bei jeder Zahl in "
        "„pruefung“ das Urteil „bitte_pruefen“, damit der Berater sie selbst nachschlägt. Lieber ohne Zahl als mit einer unsicheren.")
    return f"""Du schreibst Sprechskripte für Instagram-Reels eines jungen deutschen Vermögensberaters (DVAG). Er nimmt sie selbst auf
(Kamera oder nur Stimme für ein Motion-Video). Heute ist der {datetime.now():%d.%m.%Y}.

Zwei Regelwerke gelten. Bei einem Widerspruch gewinnt immer das Regelwerk des Kollegen: Eine Hook darf zuspitzen und neugierig
machen, aber nie etwas behaupten, das sich nicht belegen lässt, und keine Angst schüren.

<regelwerk_kollege>
{kollege}
</regelwerk_kollege>

<gemini_plan>
{plan}
</gemini_plan>

<form>
- Aufbau Hook – Mehrwert – Action als „abschnitte“, in dieser Reihenfolge: genau ein „hook“ (der erste Satz, gesprochen höchstens
  3 Sekunden, also höchstens etwa 9 Wörter; er sagt konkret, warum man dranbleiben muss), dann 2 bis 4 „mehrwert“ (je ein Gedanke,
  1 bis 3 Sätze), dann genau ein „action“ (Frage in die Kommentare; DM-Trigger und Beratungshinweis nur, wenn der Auftrag es sagt).
- Länge: etwa {SPRECHTEMPO:g} gesprochene Wörter je Sekunde. Halte die verlangte Länge auf ±10 % ein.
- Gesprochene Sprache: Du-Form, kurze Sätze, so wie man redet. Keine Klammern, keine Aufzählungszeichen, keine Emojis, keine
  Abkürzungen, die man beim Sprechen auflöst („zum Beispiel“ statt „z. B.“). Zahlen in Ziffern mit Einheit, so wie sie im
  Untertitel stehen sollen: „1.000 €“, „48 %“, „2026“.
- Betonung: Die Wörter, die beim Sprechen betont werden, stehen in *Sternchen* — pro Satz höchstens ein bis zwei, nie ein halber
  Satz: Zahlen, Gegensätze, das Kernwort der Aussage. Eine kurze Sprechpause ist „ / “ (sparsam, höchstens eine pro Satz).
- Quellen: Jede Zahl bekommt im gesprochenen Text eine kurze Herkunft („laut Deutscher Rentenversicherung“) und im Feld „quelle“
  ihres Abschnitts eine Kurzform zum Einblenden („DRV, Rentenanpassung 2026“). In „quellen“ steht die volle Angabe.
- Rechenbeispiele im Text als Beispiel kennzeichnen („Rechenbeispiel:“, „Angenommen …“); die Annahmen kommen in „annahmen“.
- Keywords aus dem Plan (Vermögensaufbau, ETFs, Finanzen, Sparen, Steuern, Rente …) dort einbauen, wo sie natürlich passen, und in
  „keywords“ auflisten.
- „schlagzeile“: Einblendung oben im Bild während der Hook. „gross“ höchstens 4 Wörter, „akzent“ ist genau ein Wort aus „gross“,
  „klein“ (freiwillig) höchstens 5 Wörter. Kein senkrechter Strich.
- „hook_alternativen“: zwei andere Hooks, die dieselben Regeln einhalten.
- „caption“: 2 bis 4 kurze Absätze mit den Keywords, den Quellen in Kurzform und dem Satz „Keine individuelle Beratung.“; sie endet
  mit der Kommentar-Frage. Höchstens 5 Hashtags ganz am Ende.
- „pruefung“: Am Ende jede Aussage mit Zahl, Fachbegriff oder Versprechen einzeln selbst kritisch prüfen: Könnte ein Fachmann oder
  Verbraucherschützer sie als falsch oder irreführend angreifen? „ok“, „umformuliert“ (dann im Skript schon umformuliert, Hinweis:
  was vorher angreifbar war) oder „bitte_pruefen“ (was der Berater selbst nachschlagen muss).
- {recherche}
</form>"""


def nutzer_prompt(e: dict, bisher: dict | None) -> str:
    sekunden = int(e.get("laenge") or 45)
    zeilen = [
        f"Thema: {e.get('thema', '').strip()}",
        f"Content-Säule: {SAEULEN.get(e.get('saeule'), SAEULEN['mythen'])}",
        f"Länge: {sekunden} Sekunden gesprochen, also etwa {round(sekunden * SPRECHTEMPO)} Wörter insgesamt",
        "DM-Trigger „STRATEGIE“ in die Action: " + ("ja" if e.get("dm") else "nein"),
        "Den Satz „Keine individuelle Beratung.“ am Ende sprechen: " + ("ja" if e.get("hinweis_sprechen") else "nein (steht nur in der Caption)"),
    ]
    if (e.get("wunsch") or "").strip():
        zeilen.append(f"Zusätzlich beachten: {e['wunsch'].strip()}")
    if bisher:
        zeilen.append("\nÜberarbeite dieses bisherige Skript nach dem Änderungswunsch, statt neu anzufangen:\n"
                      + json.dumps({k: bisher.get(k) for k in ("titel", "abschnitte", "schlagzeile", "caption", "quellen")},
                                   ensure_ascii=False))
    return "\n".join(zeilen)


def skript_auftrag(a: Auftrag, pid: str, eingabe: dict) -> dict:
    claude = claude_pfad()
    if not claude:
        raise Fehler("Die claude-Kommandozeile wurde nicht gefunden — ohne sie kann die App keine Skripte schreiben.")
    faktencheck = bool(eingabe.get("faktencheck", True))
    bisher = projekt_lesen(pid).get("skript") if eingabe.get("ueberarbeiten") else None
    a.schritt("regeln", "fertig", "Regelwerk des Kollegen und Gemini-Plan geladen")
    with tempfile.TemporaryDirectory(prefix="videocutter-") as tmp:
        sysdatei = Path(tmp) / "system.txt"
        sysdatei.write_text(system_prompt(faktencheck), encoding="utf-8")
        befehl = [claude, "-p", "--system-prompt-file", str(sysdatei), "--output-format", "stream-json", "--verbose",
                  "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "", "--permission-mode", "dontAsk",
                  "--json-schema", json.dumps(SKRIPT_SCHEMA, ensure_ascii=False)]
        befehl += ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch WebFetch"] if faktencheck else ["--tools", ""]
        a.schritt("recherche" if faktencheck else "schreiben", "laeuft",
                  "Claude prüft Zahlen an Originalquellen …" if faktencheck else "Claude schreibt …")
        ergebnis: dict = {}
        suchen = {"n": 0}

        def zeile_lesen(zeile: str) -> bool:
            try:
                d = json.loads(zeile)
            except ValueError:
                return False
            if d.get("type") == "assistant":
                for teil in d.get("message", {}).get("content", []):
                    if teil.get("type") != "tool_use":
                        continue
                    name, inp = teil.get("name"), teil.get("input") or {}
                    if name == "WebSearch":
                        suchen["n"] += 1
                        a.schritt("recherche", "laeuft", f"Sucht: {inp.get('query', '')}", anzahl=suchen["n"])
                    elif name == "WebFetch":
                        a.schritt("recherche", "laeuft", f"Liest: {inp.get('url', '')}")
                    elif name == "StructuredOutput":
                        if faktencheck:
                            a.schritt("recherche", "fertig", f"{suchen['n']} Suche(n) an Originalquellen")
                        a.schritt("schreiben", "laeuft", "Skript steht, Selbstprüfung läuft …")
            elif d.get("type") == "result":
                ergebnis.update(d)
            return True

        ausfuehren(a, "schreiben", befehl, cwd=Path(tmp), eingabe=nutzer_prompt(eingabe, bisher), zeile_lesen=zeile_lesen)
    skript = ergebnis.get("structured_output")
    if not isinstance(skript, dict) or not skript.get("abschnitte"):
        raise Fehler("Claude hat kein Skript geliefert: " + str(ergebnis.get("result") or ergebnis.get("subtype") or "keine Antwort")[:400])
    if faktencheck:
        a.schritt("recherche", "fertig", f"{suchen['n']} Suche(n) an Originalquellen")
    skript["eingabe"] = {k: eingabe.get(k) for k in ("thema", "saeule", "laenge", "dm", "hinweis_sprechen", "faktencheck", "wunsch")}
    skript["erstellt"] = _jetzt()
    skript["woerter"] = len(skript_klartext(skript).split())

    def speichern(p: dict) -> None:
        p["skript"] = skript
        if p["titel"] == "Neues Video":
            p["titel"] = skript.get("titel") or eingabe.get("thema", "")[:60] or p["titel"]
    projekt_aendern(pid, speichern)
    a.schritt("schreiben", "fertig", f"{skript['woerter']} Wörter, etwa {round(skript['woerter'] / SPRECHTEMPO)} Sekunden")
    return {"skript": skript}


# --------------------------------------------------------------------------------------- Skript ↔ Schnittplan

def skript_klartext(skript: dict) -> str:
    """Der reine Sprechtext — ohne Betonungs-Sternchen und Pausenstriche."""
    teile = [re.sub(r"\s+/\s+", " ", (ab.get("text") or "").replace("*", "")) for ab in skript.get("abschnitte", [])]
    return re.sub(r"\s+", " ", " ".join(teile)).strip()


def _norm(wort: str) -> str:
    w = unicodedata.normalize("NFC", wort.lower())
    w = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", w)
    return re.sub(r"[^\w]", "", w).replace("_", "")


def skript_marken(skript: dict) -> list[dict]:
    """Jedes Wort des Skripts mit Abschnitt und Betonung."""
    marken = []
    for nr, ab in enumerate(skript.get("abschnitte", [])):
        text = re.sub(r"\s+/\s+", " ", ab.get("text") or "")
        for m in re.finditer(r"\*[^*]+\*|[^\s*]+", text):
            stueck = m.group(0)
            betont = stueck.startswith("*")
            for wort in stueck.strip("*").split():
                n = _norm(wort)
                if n:
                    marken.append({"n": n, "w": wort, "betont": betont, "abschnitt": nr})
    return marken


def ausrichten(marken: list[dict], woerter: list[dict]) -> dict[int, int]:
    """Skriptwort-Nummer → Wortnummer im Schnittplan (nur Wörter, die bleiben)."""
    bleibt = [w for w in woerter if not w.get("weg")]
    sm = difflib.SequenceMatcher(None, [m["n"] for m in marken], [_norm(w["w"]) for w in bleibt], autojunk=False)
    zuordnung: dict[int, int] = {}
    for art, i1, i2, j1, j2 in sm.get_opcodes():
        if art == "equal" or (art == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                zuordnung[i1 + k] = bleibt[j1 + k]["i"]
    return zuordnung


def _bereiche(nummern: list[int]) -> str:
    """[3,4,5,9] → "3-5,9" """
    teile, nummern = [], sorted(set(nummern))
    for n in nummern:
        if teile and n == teile[-1][1] + 1:
            teile[-1][1] = n
        else:
            teile.append([n, n])
    return ",".join(f"{a}-{b}" if a != b else f"{a}" for a, b in teile)


def _plan_lesen(arbeitsordner: Path) -> dict:
    return json.loads((arbeitsordner / "schnittplan.json").read_text(encoding="utf-8"))


def plan_fuer_anzeige(arbeitsordner: Path) -> dict:
    plan = _plan_lesen(arbeitsordner)
    st = plan["statistik"]
    return {
        "woerter": [{"i": w["i"], "w": w["w"], "von": round(w["von"], 3), "bis": round(w["bis"], 3), "weg": w.get("weg"),
                     "betont": bool(w.get("betont")), "hand": w.get("hand")} for w in plan["woerter"]],
        "segmente": [{"von": round(s["von"], 3), "bis": round(s["bis"], 3)} for s in plan["segmente"]],
        "kandidaten": [{"id": k["id"], "art": k["art"], "von": k["von"], "bis": k["bis"], "angewandt": k.get("angewandt"),
                        "entschieden": k.get("entschieden")} for k in plan["kandidaten"]],
        "schlagzeilen": plan.get("schlagzeilen", []), "statistik": st, "dauer_roh": st["dauer_roh"],
        "dauer_ergebnis": st["dauer_ergebnis"], "vertraulich": bool(plan.get("vertraulich")),
    }


def skript_anwenden(a: Auftrag, sid: str, video: Path, arbeitsordner: Path, skript: dict, einst: dict) -> str:
    """Schreibweise aus dem Skript, dann Betonung und Schlagzeile an die richtigen Wortnummern."""
    drehbuch = arbeitsordner / "skript.txt"
    drehbuch.write_text(skript_klartext(skript) + "\n", encoding="utf-8", newline="\n")
    getan = []
    try:
        schnitt(a, sid, "aendern", str(video), "--drehbuch", str(drehbuch))
        getan.append("Schreibweise aus dem Skript")
    except Fehler as e:
        a.log(f"Schreibweise nicht übernommen: {e}")
    plan = _plan_lesen(arbeitsordner)
    marken = skript_marken(skript)
    zuordnung = ausrichten(marken, plan["woerter"])
    argumente = []
    if einst.get("skript_betonung", True):
        betont = [zuordnung[k] for k, m in enumerate(marken) if m["betont"] and k in zuordnung]
        if betont:
            argumente += ["--betonen", _bereiche(betont)]
            getan.append(f"{len(betont)} betonte Wörter")
    sz = skript.get("schlagzeile") or {}
    if einst.get("schlagzeile", True) and sz.get("gross"):
        hook = [zuordnung[k] for k, m in enumerate(marken) if m["abschnitt"] == 0 and k in zuordnung]
        if hook:
            sauber = {k: re.sub(r"[|=]", " ", sz.get(k) or "").strip() for k in ("klein", "gross", "akzent")}
            if sauber["akzent"] and sauber["akzent"] not in sauber["gross"]:
                sauber["akzent"] = ""
            # „klein|GROSS|Akzent“ — kleine Zeile und Akzent dürfen fehlen, ein Akzent ohne kleine Zeile braucht „|GROSS|Akzent“
            if sauber["akzent"]:
                text = f"{sauber['klein']}|{sauber['gross']}|{sauber['akzent']}"
            elif sauber["klein"]:
                text = f"{sauber['klein']}|{sauber['gross']}"
            else:
                text = sauber["gross"]
            argumente += ["--schlagzeilen-weg", "--schlagzeile", f"{min(hook)}-{max(hook)}={text}"]
            getan.append("Hook als Schlagzeile")
    if argumente:
        schnitt(a, sid, "aendern", str(video), *argumente)
    treffer = len(zuordnung) / max(1, len(marken))
    return f"{' · '.join(getan) or 'nichts übernommen'} (Skript zu {treffer:.0%} im Ton wiedergefunden)"


# --------------------------------------------------------------------------------------- Schnitt

def stil_schreiben(ordner: Path, p: dict, einst: dict) -> Path:
    """Der Stil des Projekts: ein vorhandener Stil plus die Abweichungen aus den Einstellungen und dem Vorbild."""
    basis = einst.get("stil") if einst.get("stil") in STILE else "reel"
    stil: dict = {"erbt": basis, "beschreibung": f"Videocutter: {basis}"}
    if einst.get("format") in ("9:16", "4:5", "1:1"):
        stil["bild"] = {"format": einst["format"], "anpassen": "zuschneiden"}
    if einst.get("position"):
        stil["untertitel"] = {"position": float(einst["position"])}
    vorschlag = ((p.get("vorbild") or {}).get("vorschlag") or {}) if einst.get("vorbild") else {}
    for bereich, werte in vorschlag.items():
        stil.setdefault(bereich, {}).update(werte)
    datei = ordner / "stil.json"
    _json_schreiben(datei, stil)
    return datei


def umwandeln(a: Auftrag, quelle: Path) -> Path:
    """Aufnahmen aus dem Browser (WebM, schwankende Bildrate) in ein festes MP4 mit 30 Bildern/s bringen."""
    ziel = quelle.with_suffix(".mp4")
    if ziel.is_file() and ziel.stat().st_mtime >= quelle.stat().st_mtime:
        return ziel
    a.schritt("umwandeln", "laeuft", "Aufnahme in ein schnittfestes MP4 umwandeln …")
    ffmpeg("-i", str(quelle), "-r", "30", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(ziel))
    a.schritt("umwandeln", "fertig", f"MP4 mit 30 Bildern/s · {dauer_messen(ziel):.1f} s".replace(".", ","))
    return ziel


def _fertig_lesen(zeilen: list[str]) -> tuple[Path | None, list[str]]:
    datei, warnungen = None, []
    for z in zeilen:
        if z.startswith("FERTIG"):
            datei = Path(z[6:].strip().split("   (")[0].strip())
        elif z.startswith(("ACHTUNG", "NICHT IN ORDNUNG", "HINWEIS")):
            warnungen.append(z)
    return datei, warnungen


def _rendern(a: Auftrag, pid: str, video: Path, arbeitsordner: Path) -> dict:
    a.schritt("rendern", "laeuft", "Video bauen: schneiden, Untertitel einbrennen, Ton einpegeln …")
    zeilen = schnitt(a, "rendern", "rendern", str(video), "--bilder", "3")
    datei, warnungen = _fertig_lesen(zeilen)
    if not datei or not datei.is_file():
        raise Fehler("Das Rendern hat keine Datei gemeldet.")
    ordner = projekt_ordner(pid)
    plan = _plan_lesen(arbeitsordner)
    eintrag = {"datei": datei.relative_to(ordner).as_posix(), "wann": _jetzt(), "dauer": plan["statistik"]["dauer_ergebnis"],
               "vorher": plan["statistik"]["dauer_roh"], "mb": round(datei.stat().st_size / 1_048_576, 1),
               "bilder": sorted(b.relative_to(ordner).as_posix() for b in arbeitsordner.glob("blick-*.png")),
               "warnungen": warnungen}
    projekt_aendern(pid, lambda p: p["ergebnisse"].append(eintrag))
    a.schritt("rendern", "fertig", f"{eintrag['mb']:.1f} MB · {eintrag['dauer']:.1f} s".replace(".", ","))
    return eintrag


def schnitt_auftrag(a: Auftrag, pid: str, einst: dict) -> dict:
    ordner = projekt_ordner(pid)
    p = projekt_aendern(pid, lambda p: p["einstellungen"].update(einst))
    if not p.get("quelle"):
        raise Fehler("Es gibt noch kein Video: erst aufnehmen oder eine Datei hineinziehen.")
    if p["quelle"].get("nur_ton"):
        raise Fehler("Die Aufnahme ist nur Ton — daraus wird ein Motion-Video (Schritt 4), kein geschnittenes Kamera-Video.")
    video = ordner / p["quelle"]["datei"]
    if video.suffix.lower() == ".webm":
        video = umwandeln(a, video)
    arbeitsordner = video.with_name(video.stem + ".schnitt")
    stil = stil_schreiben(ordner, p, p["einstellungen"])
    namen = ", ".join(dict.fromkeys(["ETF", "ETFs", "DVAG", "DRV", "Destatis", *((p.get("skript") or {}).get("keywords") or [])]))

    a.schritt("plan", "laeuft", "Ton erkennen (Whisper) und Schnittplan nach den Regeln bauen …")
    schnitt(a, "plan", "vorbereiten", str(video), "--stil", str(stil), "--namen", namen[:400])
    anzeige = plan_fuer_anzeige(arbeitsordner)
    st = anzeige["statistik"]
    a.melden("plan", plan=anzeige)
    a.schritt("plan", "fertig", f"{len(anzeige['woerter'])} Wörter erkannt · {st['dauer_roh']:.1f} s → {st['dauer_ergebnis']:.1f} s".replace(".", ","))

    if p.get("skript"):
        a.schritt("skript", "laeuft", "Skript mit dem Gesprochenen abgleichen (Schreibweise, Betonung, Schlagzeile) …")
        text = skript_anwenden(a, "skript", video, arbeitsordner, p["skript"], p["einstellungen"])
        a.melden("plan", plan=plan_fuer_anzeige(arbeitsordner))
        a.schritt("skript", "fertig", text)
    else:
        a.schritt("skript", "uebersprungen", "Kein Skript im Projekt — Betonung nur nach den Regeln (Zahlen)")

    projekt_aendern(pid, lambda p: p.__setitem__("arbeitsordner", arbeitsordner.relative_to(ordner).as_posix()))
    return {"ergebnis": _rendern(a, pid, video, arbeitsordner)}


def aendern_auftrag(a: Auftrag, pid: str, wunsch: dict) -> dict:
    ordner = projekt_ordner(pid)
    p = projekt_lesen(pid)
    if not p.get("arbeitsordner"):
        raise Fehler("Erst einmal schneiden, dann lässt sich der Plan ändern.")
    arbeitsordner = ordner / p["arbeitsordner"]
    video = Path(_plan_lesen(arbeitsordner)["quelle"])
    argumente = []
    for schluessel in ("weg", "doch", "betonen", "unbetonen"):
        nummern = [int(n) for n in wunsch.get(schluessel) or [] if str(n).lstrip("-").isdigit()]
        if nummern:
            argumente += [f"--{schluessel}", _bereiche(nummern)]
    for schluessel in ("annehmen", "ablehnen"):
        ids = [k for k in wunsch.get(schluessel) or [] if re.fullmatch(r"k\d+", str(k))]
        if ids:
            argumente += [f"--{schluessel}", ",".join(ids)]
    if wunsch.get("zuruecksetzen"):
        argumente.append("--zuruecksetzen")
    if not argumente:
        raise Fehler("Keine Änderung ausgewählt.")
    a.schritt("plan", "laeuft", "Schnittplan ändern …")
    schnitt(a, "plan", "aendern", str(video), *argumente)
    anzeige = plan_fuer_anzeige(arbeitsordner)
    a.melden("plan", plan=anzeige)
    a.schritt("plan", "fertig", f"Neu: {anzeige['dauer_ergebnis']:.1f} s".replace(".", ","))
    return {"ergebnis": _rendern(a, pid, video, arbeitsordner)}


# --------------------------------------------------------------------------------------- Vorbild

def vorbild_auftrag(a: Auftrag, pid: str) -> dict:
    ordner = projekt_ordner(pid)
    p = projekt_lesen(pid)
    if not p.get("vorbild"):
        raise Fehler("Erst ein Vorbild-Video hineinziehen.")
    video = ordner / p["vorbild"]["datei"]
    messordner = ordner / "vorbild" / "messung"
    a.schritt("messen", "laeuft", "Vorbild ansehen: Standbilder, Schnitt-Takt, Sprechpausen, Lautheit …")
    schnitt(a, "messen", "referenz", str(video), "--bilder", "6", "--ordner", str(messordner))
    m = json.loads((messordner / "referenz.json").read_text(encoding="utf-8"))
    vorschlag: dict = {}
    sprache = m.get("sprache") or {}
    if "vorschlag" in sprache:
        vorschlag["schnitt"] = dict(sprache["vorschlag"])
    if m["hoehe"] > m["breite"]:
        verhaeltnis = m["breite"] / m["hoehe"]
        vorschlag["bild"] = {"format": "9:16" if verhaeltnis < 0.7 else "4:5", "anpassen": "zuschneiden"}
    if m.get("bildwechsel_je_minute", 0) >= 20:
        vorschlag.setdefault("bild", {}).update({"zoom_bei_schnitt": 1.12, "zoom_takt": 3})
    bilder = [Path(b["datei"]).relative_to(ordner).as_posix() for b in m.get("bilder", [])]

    def speichern(p: dict) -> None:
        p["vorbild"].update({"messung": {k: m.get(k) for k in ("breite", "hoehe", "bildrate", "bildwechsel_je_minute", "lautheit_lufs",
                                                              "ausgewertet_sekunden")} | {"sprache": sprache},
                             "vorschlag": vorschlag, "bilder": bilder})
        p["einstellungen"]["vorbild"] = True
    p = projekt_aendern(pid, speichern)
    a.schritt("messen", "fertig", f"{m.get('bildwechsel_je_minute', 0):g} Bildwechsel je Minute".replace(".", ",")
              + (f" · {sprache['woerter_je_minute']} Wörter/Minute" if "woerter_je_minute" in sprache else ""))
    return {"vorbild": p["vorbild"]}


# --------------------------------------------------------------------------------------- Motion

THEMEN = {"nacht": "Nachtblau & Gold", "papier": "Papier & Grün", "kontrast": "Schwarz & Orange"}


def motion_daten(plan: dict, skript: dict | None, einst: dict) -> dict:
    """Was die Szenen-Seite braucht: jedes Wort mit Zeit im fertigen Video, Abschnitt und Betonung."""
    d = grafikmodul.daten(plan, 1080, 1920)
    nach_i = {w["i"]: w for w in plan["woerter"]}
    abschnitte = [{"rolle": "mehrwert", "quelle": ""}]
    zu_marke: dict[int, dict] = {}
    if skript and skript.get("abschnitte"):
        abschnitte = [{"rolle": ab.get("rolle", "mehrwert"), "quelle": (ab.get("quelle") or "").strip()} for ab in skript["abschnitte"]]
        marken = skript_marken(skript)
        zu_marke = {i: marken[k] for k, i in ausrichten(marken, plan["woerter"]).items()}
    letzter = 0
    for w in d["woerter"]:
        marke = zu_marke.get(w["i"])
        if marke:
            letzter = max(letzter, marke["abschnitt"])
        w["abschnitt"] = letzter
        w["betont"] = bool(nach_i[w["i"]].get("betont") or (marke and marke["betont"]))
    for nr, ab in enumerate(abschnitte):
        drin = [w for w in d["woerter"] if w["abschnitt"] == nr]
        ab["von"], ab["bis"] = (drin[0]["t"], drin[-1]["e"]) if drin else (None, None)
    dm = bool((skript or {}).get("eingabe", {}).get("dm"))
    d.update({"abschnitte": abschnitte, "thema": einst.get("thema") if einst.get("thema") in THEMEN else "nacht",
              "handle": (einst.get("handle") or "").strip()[:40], "titel": (skript or {}).get("titel", ""),
              "cta": "Schreib mir „STRATEGIE“ per DM" if dm else "Schreib's in die Kommentare",
              "hinweis": "Keine individuelle Beratung." + (" Rechenbeispiele vereinfacht." if (skript or {}).get("annahmen") else ""),
              "quellen": [q.get("quelle", "") for q in (skript or {}).get("quellen", [])][:4]})
    return d


def motion_auftrag(a: Auftrag, pid: str, einst: dict) -> dict:
    if not shutil.which("node") or not browser_pfad():
        raise Fehler("Für Motion-Videos braucht es Node (ab Version 22) und Edge oder Chrome.")
    ordner = projekt_ordner(pid)
    p = projekt_aendern(pid, lambda p: p.__setitem__("motion", {**(p.get("motion") or {}), "einstellungen": einst}))
    m = p["motion"]
    if einst.get("ton_aus_aufnahme") or not m.get("ton_roh"):
        if not p.get("quelle"):
            raise Fehler("Es gibt noch keinen Ton: erst die Stimme aufnehmen oder eine Tondatei hineinziehen.")
        quelle = ordner / p["quelle"]["datei"]
    else:
        quelle = ordner / m["ton_roh"]
    arbeit = ordner / "motion"
    arbeit.mkdir(exist_ok=True)

    a.schritt("ton", "laeuft", "Stimme vorbereiten …")
    sprache = arbeit / "sprache.wav"
    # 3 s Stille hinten dran: davon bleiben über ende_luft gut 2,5 s für die Schlusskarte
    ffmpeg("-i", str(quelle), "-vn", "-ac", "1", "-ar", "48000", "-af", "apad=pad_dur=3", "-c:a", "pcm_s16le", str(sprache))
    roh_dauer = dauer_messen(sprache)
    vorlauf = arbeit / "vorlauf.mp4"
    ffmpeg("-f", "lavfi", "-i", f"color=c=0x0B1020:s=1080x1920:r=30:d={roh_dauer:.3f}", "-i", str(sprache), "-c:v", "libx264",
           "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k", "-shortest", str(vorlauf))
    a.schritt("ton", "fertig", f"{roh_dauer:.1f} s Stimme".replace(".", ","))

    a.schritt("plan", "laeuft", "Stimme erkennen und Pausen, Füllwörter, Versprecher herausnehmen …")
    stil = arbeit / "stil.json"
    _json_schreiben(stil, {"erbt": "magi", "beschreibung": "Videocutter: Stimme für ein Motion-Video", "untertitel": {"an": False},
                           "schnitt": {"ende_luft": 2.6}})
    namen = ", ".join(dict.fromkeys(["ETF", "ETFs", "DVAG", "DRV", *((p.get("skript") or {}).get("keywords") or [])]))
    schnitt(a, "plan", "vorbereiten", str(vorlauf), "--stil", str(stil), "--namen", namen[:400], "--neu")
    arbeitsordner = vorlauf.with_name("vorlauf.schnitt")
    if p.get("skript"):
        drehbuch = arbeitsordner / "skript.txt"
        drehbuch.write_text(skript_klartext(p["skript"]) + "\n", encoding="utf-8", newline="\n")
        try:
            schnitt(a, "plan", "aendern", str(vorlauf), "--drehbuch", str(drehbuch))
        except Fehler as e:
            a.log(f"Schreibweise nicht übernommen: {e}")
    anzeige = plan_fuer_anzeige(arbeitsordner)
    a.melden("plan", plan=anzeige)
    a.schritt("plan", "fertig", f"{anzeige['dauer_roh']:.1f} s → {anzeige['dauer_ergebnis']:.1f} s".replace(".", ","))

    a.schritt("schnitt", "laeuft", "Ton schneiden und einpegeln …")
    ton_film = arbeit / "ton-geschnitten.mp4"
    schnitt(a, "schnitt", "rendern", str(vorlauf), "--ohne-untertitel", "--ausgabe", str(ton_film), "--ueberschreiben")
    ton = arbeit / "ton-geschnitten.wav"
    ffmpeg("-i", str(ton_film), "-vn", "-c:a", "pcm_s16le", str(ton))
    a.schritt("schnitt", "fertig", f"{dauer_messen(ton):.1f} s".replace(".", ","))

    daten = motion_daten(_plan_lesen(arbeitsordner), p.get("skript"), einst)
    _json_schreiben(arbeit / "motion-daten.json", daten)
    a.melden("vorschau", daten=f"motion/motion-daten.json", ton="motion/ton-geschnitten.wav")

    a.schritt("ablichten", "laeuft", "Szenen Bild für Bild im Browser ablichten …")
    ziel = _freier_name(arbeit, "motion", ".mp4")
    ausfuehren(a, "ablichten", ["node", str(ABLICHTEN), str(WEB / "motion.html"), "--aus", str(ziel), "--dauer", f"{daten['dauer']:.4f}",
                                "--fps", "30", "--daten", str(arbeit / "motion-daten.json"), "--ton", str(ton)])
    if not ziel.is_file():
        raise Fehler("Das Ablichten hat keine Datei hinterlassen.")
    eintrag = {"datei": ziel.relative_to(ordner).as_posix(), "wann": _jetzt(), "dauer": round(daten["dauer"], 2),
               "mb": round(ziel.stat().st_size / 1_048_576, 1)}
    projekt_aendern(pid, lambda p: p["motion"].update({"ergebnis": eintrag, "daten": "motion/motion-daten.json",
                                                        "ton": "motion/ton-geschnitten.wav"}))
    a.schritt("ablichten", "fertig", f"{eintrag['mb']:.1f} MB · {eintrag['dauer']:.1f} s".replace(".", ","))
    return {"motion": eintrag}


# --------------------------------------------------------------------------------------- HTTP

class Anfrage(BaseHTTPRequestHandler):
    server_version = "Videocutter/1.0"

    def log_message(self, format, *args):  # noqa: A002 — Name kommt von BaseHTTPRequestHandler
        if "/ereignisse" not in self.path and not self.path.startswith(("/api/projekte/", "/web")):
            sys.stderr.write("  " + format % args + "\n")

    # --- Antworten
    def _json(self, daten, code: int = 200) -> None:
        roh = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(roh)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(roh)

    def _koerper(self) -> dict:
        laenge = int(self.headers.get("Content-Length") or 0)
        if not laenge:
            return {}
        try:
            return json.loads(self.rfile.read(laenge).decode("utf-8"))
        except ValueError as e:
            raise Fehler(f"Die Anfrage war kein JSON: {e}")

    def _datei(self, pfad: Path) -> None:
        if not pfad.is_file():
            raise Fehler("Datei nicht gefunden.", 404)
        groesse = pfad.stat().st_size
        typ = TYPEN.get(pfad.suffix.lower()) or mimetypes.guess_type(pfad.name)[0] or "application/octet-stream"
        start, ende = 0, groesse - 1
        bereich = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if bereich and groesse:
            if bereich.group(1):
                start = int(bereich.group(1))
                ende = min(int(bereich.group(2)), groesse - 1) if bereich.group(2) else groesse - 1
            else:
                start = max(0, groesse - int(bereich.group(2) or 0))
            if start > ende:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{groesse}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{ende}/{groesse}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(ende - start + 1 if groesse else 0))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        with pfad.open("rb") as f:
            f.seek(start)
            rest = ende - start + 1
            try:
                while rest > 0:
                    stueck = f.read(min(1 << 20, rest))
                    if not stueck:
                        break
                    self.wfile.write(stueck)
                    rest -= len(stueck)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass

    def _ereignisse(self, auftrag_id: str) -> None:
        a = AUFTRAEGE.get(auftrag_id)
        if not a:
            raise Fehler("Diesen Auftrag gibt es nicht (mehr).", 404)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        gesendet = 0
        try:
            while True:
                with a.bedingung:
                    if gesendet >= len(a.ereignisse) and not a.zu:
                        a.bedingung.wait(timeout=15)
                    neu = a.ereignisse[gesendet:]
                    zu = a.zu
                if neu:
                    for e in neu:
                        self.wfile.write(f"data: {json.dumps(e, ensure_ascii=False)}\n\n".encode("utf-8"))
                    gesendet += len(neu)
                else:
                    self.wfile.write(b": still\n\n")
                self.wfile.flush()
                if zu and gesendet >= len(a.ereignisse):
                    return
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return

    def _hochladen(self, pid: str, abfrage: dict) -> None:
        laufender_auftrag(pid)
        zweck = (abfrage.get("zweck") or ["aufnahme"])[0]
        name = Path((abfrage.get("name") or ["datei"])[0]).name
        endung = Path(name).suffix.lower() or ".webm"
        nur_ton = (abfrage.get("nur_ton") or ["0"])[0] == "1"
        erlaubt = TON_ENDUNGEN | VIDEO_ENDUNGEN if zweck in ("ton", "aufnahme") else VIDEO_ENDUNGEN
        if endung not in erlaubt:
            raise Fehler(f"Mit der Endung {endung} kann der Videocutter nichts anfangen.")
        ordner = projekt_ordner(pid)
        if zweck == "vorbild":
            (ordner / "vorbild").mkdir(exist_ok=True)
            ziel = _freier_name(ordner / "vorbild", "vorbild", endung)
        elif zweck == "ton":
            (ordner / "motion").mkdir(exist_ok=True)
            ziel = _freier_name(ordner / "motion", "stimme", endung)
        elif zweck == "import":
            ziel = _freier_name(ordner, _kurzname(Path(name).stem, 30), endung)
        else:
            ziel = _freier_name(ordner, "aufnahme" if not nur_ton else "stimme", endung)
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge <= 0:
            raise Fehler("Die Datei ist leer.")
        neben = ziel.with_suffix(ziel.suffix + ".teil")
        with neben.open("wb") as f:
            rest = laenge
            while rest > 0:
                stueck = self.rfile.read(min(1 << 20, rest))
                if not stueck:
                    break
                f.write(stueck)
                rest -= len(stueck)
        if rest > 0:
            neben.unlink(missing_ok=True)
            raise Fehler("Das Hochladen wurde unterbrochen.")
        neben.replace(ziel)
        relativ = ziel.relative_to(ordner).as_posix()
        if endung in TON_ENDUNGEN - VIDEO_ENDUNGEN:
            nur_ton = True

        def speichern(p: dict) -> None:
            if zweck == "vorbild":
                p["vorbild"] = {"datei": relativ, "name": name}
            elif zweck == "ton":
                p["motion"] = {**(p.get("motion") or {}), "ton_roh": relativ}
            else:
                p["quelle"] = {"datei": relativ, "art": zweck, "name": name, "nur_ton": nur_ton, "dauer": dauer_messen(ziel)}
                if nur_ton:
                    p["motion"] = {**(p.get("motion") or {}), "ton_roh": relativ}
        self._json({"projekt": projekt_aendern(pid, speichern), "datei": relativ})

    # --- Wege
    def _weg(self, methode: str) -> None:
        url = urlparse(self.path)
        teile = [unquote(t) for t in url.path.strip("/").split("/") if t]
        abfrage = parse_qs(url.query)
        if not teile or teile[0] != "api":
            if methode not in ("GET", "HEAD"):
                raise Fehler("Unbekannter Weg.", 404)
            relativ = "/".join(teile) or "index.html"
            pfad = (WEB / relativ).resolve()
            if WEB.resolve() not in pfad.parents:
                raise Fehler("Nicht gefunden.", 404)
            return self._datei(pfad)
        weg = teile[1:]
        if weg == ["zustand"] and methode == "GET":
            return self._json(zustand(bool(abfrage.get("neu"))))
        if weg == ["regelwerk"]:
            if methode == "PUT":
                k = self._koerper()
                for schluessel, datei in (("kollege", "kollege.md"), ("gemini", "gemini-plan.md")):
                    if isinstance(k.get(schluessel), str) and k[schluessel].strip():
                        (REGELN / datei).write_text(k[schluessel].replace("\r\n", "\n"), encoding="utf-8", newline="\n")
            return self._json({"kollege": (REGELN / "kollege.md").read_text(encoding="utf-8"),
                               "gemini": (REGELN / "gemini-plan.md").read_text(encoding="utf-8")})
        if weg == ["projekte"]:
            if methode == "POST":
                return self._json(projekt_neu(self._koerper().get("titel", "")))
            return self._json(projekte_liste())
        if len(weg) >= 2 and weg[0] == "auftraege":
            if len(weg) == 3 and weg[2] == "ereignisse":
                return self._ereignisse(weg[1])
            if len(weg) == 3 and weg[2] == "abbrechen" and methode == "POST":
                a = AUFTRAEGE.get(weg[1])
                if a:
                    a.abbrechen()
                return self._json({"ok": True})
        if len(weg) >= 2 and weg[0] == "projekte":
            pid = weg[1]
            rest = weg[2:]
            if not rest:
                if methode == "PATCH":
                    k = self._koerper()
                    return self._json(projekt_aendern(pid, lambda p: p.__setitem__("titel", str(k.get("titel") or p["titel"])[:80])))
                return self._json(projekt_lesen(pid))
            if rest[0] == "datei" and len(rest) > 1:
                return self._datei(im_projekt(pid, "/".join(rest[1:])))
            if rest == ["plan"]:
                p = projekt_lesen(pid)
                if not p.get("arbeitsordner"):
                    return self._json(None)
                return self._json(plan_fuer_anzeige(projekt_ordner(pid) / p["arbeitsordner"]))
            if rest == ["motion-plan"]:
                arbeitsordner = projekt_ordner(pid) / "motion" / "vorlauf.schnitt"
                return self._json(plan_fuer_anzeige(arbeitsordner) if (arbeitsordner / "schnittplan.json").is_file() else None)
            if rest == ["hochladen"] and methode in ("PUT", "POST"):
                return self._hochladen(pid, abfrage)
            if rest == ["skript"] and methode == "PUT":
                k = self._koerper()
                skript = k.get("skript")
                if not isinstance(skript, dict) or not isinstance(skript.get("abschnitte"), list):
                    raise Fehler("Das Skript braucht Abschnitte.")
                skript["woerter"] = len(skript_klartext(skript).split())
                return self._json(projekt_aendern(pid, lambda p: p.__setitem__("skript", skript)))
            if rest == ["einstellungen"] and methode == "PUT":
                k = self._koerper()
                return self._json(projekt_aendern(pid, lambda p: p["einstellungen"].update(k)))
            if rest == ["zeigen"] and methode == "POST":
                ziel = im_projekt(pid, (abfrage.get("datei") or [""])[0])
                subprocess.Popen(["explorer", f"/select,{ziel}"] if ziel.is_file() else ["explorer", str(ziel)])
                return self._json({"ok": True})
            arbeiten = {"skript-schreiben": ("skript", skript_auftrag), "schneiden": ("schnitt", schnitt_auftrag),
                        "aendern": ("aendern", aendern_auftrag), "vorbild": ("vorbild", vorbild_auftrag),
                        "motion": ("motion", motion_auftrag)}
            if len(rest) == 1 and rest[0] in arbeiten and methode == "POST":
                laufender_auftrag(pid)
                art, arbeit = arbeiten[rest[0]]
                k = self._koerper()
                if art == "skript" and not (k.get("thema") or "").strip():
                    raise Fehler("Erst ein Thema eingeben.")
                a = Auftrag(art, pid)
                a.starten(arbeit, pid, *([] if art == "vorbild" else [k]))
                return self._json({"auftrag": a.id})
        raise Fehler("Unbekannter Weg.", 404)

    def _sicher(self, methode: str) -> None:
        try:
            self._weg(methode)
        except Fehler as e:
            try:
                self._json({"fehler": str(e)}, e.code)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_GET(self):  # noqa: N802
        self._sicher("GET")

    def do_HEAD(self):  # noqa: N802
        self._sicher("HEAD")

    def do_POST(self):  # noqa: N802
        self._sicher("POST")

    def do_PUT(self):  # noqa: N802
        self._sicher("PUT")

    def do_PATCH(self):  # noqa: N802
        self._sicher("PATCH")


def main() -> int:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Videocutter starten")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--ohne-browser", action="store_true")
    a = ap.parse_args()
    PROJEKTE.mkdir(exist_ok=True)
    adresse = f"http://127.0.0.1:{a.port}/"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", a.port), Anfrage)
    except OSError:
        print(f"Der Videocutter läuft schon (oder Port {a.port} ist belegt). Öffne {adresse}")
        if not a.ohne_browser:
            webbrowser.open(adresse)
        return 0
    server.daemon_threads = True
    # Hängengebliebene Auftrags-Marken vom letzten Lauf lösen
    for eintrag in projekte_liste():
        try:
            projekt_aendern(eintrag["id"], lambda p: p.__setitem__("auftrag", None))
        except Fehler:
            pass
    threading.Thread(target=zustand, daemon=True).start()
    print(f"Videocutter läuft: {adresse}   (Fenster schließen oder Strg+C beendet ihn)")
    if not a.ohne_browser:
        webbrowser.open(adresse)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
