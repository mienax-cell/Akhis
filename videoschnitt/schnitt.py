#!/usr/bin/env python
"""MAGI Videoschnitt — Rohvideo rein, fertiges Video raus.

Üblicher Ablauf:   vorbereiten  →  (zeigen, aendern)  →  rendern

    pruefen                       ist alles da?
    stile                         welche Stile gibt es, und welches Format machen sie?
    vorbereiten VIDEO --stil X    transkribieren und Schnittplan nach Regeln bauen
    zeigen VIDEO                  den Plan noch einmal lesen (ändert nichts)
    aendern VIDEO --weg 12-18     den Plan ändern: Wörter, Kandidaten, Zeitbereiche, Schreibweise, Betonung, Schlagzeilen
    rendern VIDEO                 das fertige Video bauen
    alles VIDEO --stil X          vorbereiten + rendern in einem Zug, nur nach Regeln
    referenz VIDEO                Standbilder und Takt eines Vorbild-Videos (für einen neuen Stil)
    modell-holen NAME --ja        ein Whisper-Modell laden (nur mit Chefs Ja)

VIDEO ist das Rohvideo oder sein Arbeitsordner (<name>.schnitt neben dem Video). Das Rohvideo wird nie
verändert. Das Ergebnis heißt <name>-geschnitten.mp4 und liegt daneben; gibt es das schon, -geschnitten-2,
-3 … Der genaue Pfad steht in der Zeile FERTIG. Zeiten im Plan sind Zeiten des Rohvideos; die Spalte
daneben zeigt, wo die Stelle im fertigen Video liegt.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

from videoschnitt import VERSION, ModulFehler, medien, plan as planmodul, stil as stilmodul, transkript, umgebung  # noqa: E402

VIDEO_ENDUNGEN = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi", ".mts", ".mpg", ".mpeg", ".wmv", ".3gp"}
AUFRUF = f'python "{HIER / "schnitt.py"}"'
LANG_AB = 450        # ab so vielen Wörtern steht der Wortlaut nur noch in der Datei, nicht mehr in der Ausgabe
# Was zuletzt benutzt wurde, merkt sich MAGI in seinem Datenordner (nicht in AppData: den sieht die
# Claude-App umgeleitet, und MAGI fände ihn von außen nicht).
MERKZETTEL = HIER.parent.parent / "daten" / "videoschnitt-zuletzt.json"


class Abbruch(ModulFehler):
    """Ein Fehler aus der Bedienung (falscher Pfad, nichts angegeben)."""


def sagen(*teile: str) -> None:
    print(*teile, flush=True)


def _videos_in(ordner: Path) -> list[str]:
    try:
        return sorted(p.name for p in ordner.iterdir() if p.suffix.lower() in VIDEO_ENDUNGEN)
    except OSError:
        return []


def orte(angabe: str, ordner: str | None = None) -> tuple[Path | None, Path]:
    """Aus dem, was übergeben wurde, Rohvideo und Arbeitsordner machen."""
    roh = angabe.strip().strip('"')
    if roh.lower().startswith(("http://", "https://")):
        raise Abbruch("Das ist eine Internet-Adresse. Das Modul lädt nichts herunter — die Datei muss schon auf dem Rechner liegen.")
    pfad = Path(roh).expanduser()
    if pfad.is_dir():
        plan = pfad / "schnittplan.json"
        if plan.is_file():
            return Path(json.loads(plan.read_text(encoding="utf-8"))["quelle"]), pfad.resolve()
        videos = _videos_in(pfad)
        raise Abbruch(f"{pfad} ist ein Ordner, kein Video und kein Arbeitsordner."
                      + (f" Videos darin: {', '.join(videos[:8])}" if videos else ""))
    if not pfad.is_file():
        if not pfad.parent.is_dir():
            raise Abbruch(f"Den Ordner gibt es nicht: {pfad.parent}")
        videos = _videos_in(pfad.parent)
        nah = difflib.get_close_matches(pfad.name, videos, n=3, cutoff=0.5)
        raise Abbruch(f"Die Datei gibt es nicht: {pfad}."
                      + (f" Gemeint vielleicht: {', '.join(nah)}" if nah else
                         f" In dem Ordner liegen: {', '.join(videos[:8])}" if videos else " In dem Ordner liegt kein Video."))
    if pfad.suffix.lower() not in VIDEO_ENDUNGEN:
        raise Abbruch(f"{pfad.name} sieht nicht nach einem Video aus (Endung {pfad.suffix}).")
    pfad = pfad.resolve()
    return pfad, (Path(ordner).resolve() if ordner else pfad.with_name(pfad.stem + ".schnitt"))


def fortschritt(wort: str):
    """Fortschritt in Viertelschritten, auf den Fehlerkanal — so bleibt die eigentliche Ausgabe kurz."""
    stand = {"viertel": 0}

    def melden(anteil: float) -> None:
        viertel = int(anteil * 4)
        if stand["viertel"] < viertel < 4:
            stand["viertel"] = viertel
            print(f"  {wort} {viertel * 25} %", file=sys.stderr, flush=True)
    return melden


def zuletzt_lesen() -> str | None:
    try:
        return json.loads(MERKZETTEL.read_text(encoding="utf-8")).get("stil")
    except (OSError, ValueError):
        return None


def zuletzt_merken(stil: str) -> None:
    if MERKZETTEL.parent.is_dir():
        try:
            MERKZETTEL.write_text(json.dumps({"stil": stil, "wann": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False),
                                  encoding="utf-8", newline="\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------------

def cmd_pruefen(a) -> int:
    ergebnis = umgebung.pruefen()
    if a.json:
        sagen(json.dumps(ergebnis, ensure_ascii=False, indent=1))
        return 0 if ergebnis["ok"] else 1
    sagen(f"MAGI Videoschnitt {VERSION}")
    for p in ergebnis["punkte"]:
        zeichen = "ok   " if p["ok"] else ("FEHLT" if p["pflicht"] else "fehlt")
        sagen(f"  {zeichen}  {p['name']}: {p['wert']}")
        if p["hilfe"]:
            sagen(f"         → {p['hilfe']}")
    sagen("BEREIT — ein Video läuft durch." if ergebnis["ok"] else "NICHT BEREIT — die Zeilen mit FEHLT zuerst beheben.")
    return 0 if ergebnis["ok"] else 1


def cmd_stile(a) -> int:
    for name, beschreibung in stilmodul.liste():
        try:
            bild = stilmodul.laden(name)["bild"]
            form = "Format wie gefilmt" if bild["format"] == "original" else f"macht {bild['format']}"
        except stilmodul.StilFehler:
            form = "defekt"
        sagen(f"  {name:<10} {form:<19} {beschreibung}")
    letzter = zuletzt_lesen()
    if letzter:
        sagen(f"Zuletzt benutzt: {letzter}")
    sagen(f"Ein eigener Stil ist eine JSON-Datei mit \"erbt\": \"<stil>\" und nur den Abweichungen — in {stilmodul.STILE_ORDNER} "
          "oder irgendwo, dann --stil <Pfad>.")
    return 0


def _transkript_holen(video: Path, ordner: Path, stil: dict, a) -> dict:
    """Transkribieren — oder das vorhandene Transkript nehmen, wenn Video und Einstellung dieselben sind."""
    datei = ordner / "transkript.json"
    st = video.stat()
    sprache = a.sprache or stil["sprache"]
    modell = transkript.modell_waehlen(a.modell or stil["transkription"]["modell"])
    schluessel = {"bytes": st.st_size, "geaendert": int(st.st_mtime), "modell": modell, "sprache": sprache,
                  "hinweis": stil["transkription"].get("hinweis") or "", "namen": a.namen or "", "fassung": 2}
    if datei.is_file() and not a.neu:
        alt = json.loads(datei.read_text(encoding="utf-8"))
        if alt.get("schluessel") == schluessel:
            return alt
    wav = ordner / "ton.wav"
    medien.ton_herausziehen(video, wav)
    print(f"  Transkribiere mit Modell {modell} …", file=sys.stderr, flush=True)
    ergebnis = transkript.transkribieren(wav, sprache, modell, "auto", stil["transkription"].get("hinweis"),
                                        fortschritt("transkribiert"), a.namen)
    if not ergebnis["woerter"]:
        raise Abbruch("Im Ton wurde kein einziges Wort erkannt. Ist das die richtige Datei, ist die Sprache richtig "
                      f"(angenommen: {sprache})? Für ein Video ohne Sprache gibt es hier nichts zu schneiden.")
    ergebnis["schluessel"] = schluessel
    planmodul.schreiben(datei, ergebnis)
    return ergebnis


def _huelle(ordner: Path, video: Path | None) -> medien.Huelle | None:
    wav = ordner / "ton.wav"
    if not wav.is_file() and video and video.is_file():
        medien.ton_herausziehen(video, wav)
    return medien.Huelle.aus_wav(wav) if wav.is_file() else None


def _ablegen(plan: dict, ordner: Path) -> None:
    planmodul.schreiben(ordner / "schnittplan.json", plan)
    (ordner / "schnittplan.txt").write_text(planmodul.uebersicht(plan, not plan.get("vertraulich")),
                                            encoding="utf-8", newline="\n")
    (ordner / "schnitt.edl").write_text(planmodul.edl_cmx3600(plan), encoding="utf-8", newline="\r\n")


def _ausgeben(plan: dict, ordner: Path) -> None:
    """Den Plan zeigen — bei langen Videos nur Zahlen und offene Stellen, der Wortlaut steht in der Datei."""
    if plan.get("vertraulich") or len(plan["woerter"]) <= LANG_AB:
        sagen(planmodul.uebersicht(plan, not plan.get("vertraulich")).rstrip())
        return
    for zeile in planmodul.kurzfassung(plan) + planmodul.kandidaten_zeilen(plan):
        sagen(zeile)
    sagen(f"\nTEXT      {len(plan['woerter'])} Wörter — zu lang für hier. Der Wortlaut mit Nummern steht in "
          f"{ordner / 'schnittplan.txt'} (in Stücken lesen) oder:  {AUFRUF} zeigen \"{ordner}\" --von 0 --bis 300")


def vorbereiten(a) -> tuple[dict, Path]:
    video, ordner = orte(a.video, getattr(a, "ordner", None))
    if video is None or not video.is_file():
        raise Abbruch("Zum Vorbereiten braucht es das Rohvideo — es liegt nicht mehr dort, wo der Arbeitsordner es kennt.")
    letzter = zuletzt_lesen()
    if a.stil == "letzter":
        if not letzter:
            raise Abbruch("Es ist noch kein Stil benutzt worden. Welche es gibt:  " + AUFRUF + " stile")
        a.stil = letzter
    stil = stilmodul.laden(a.stil or stilmodul.GRUNDSTIL)
    if not a.stil:
        sagen(f"  Kein Stil genannt — nehme {stilmodul.GRUNDSTIL}." + (f" Zuletzt benutzt: {letzter} (--stil letzter)." if letzter else ""))
    for warnung in stil.get("_warnungen", []):
        sagen(f"  Hinweis zum Stil: {warnung}")
    ordner.mkdir(parents=True, exist_ok=True)
    info = medien.auskunft(video)
    alt = None
    if (ordner / "schnittplan.json").is_file():
        try:
            alt = planmodul.lesen(ordner / "schnittplan.json")
        except (planmodul.PlanFehler, KeyError, ValueError):
            alt = None
    ts = _transkript_holen(video, ordner, stil, a)
    huelle = _huelle(ordner, video)
    transkript.verankern(ts["woerter"], huelle)
    plan, uebernommen = planmodul.neu(video, info, stil, ts, alt)
    plan["vertraulich"] = bool(a.vertraulich)
    plan["arbeitsordner"] = str(ordner)
    planmodul.rechnen(plan, huelle)
    if not plan["segmente"]:
        raise Abbruch("Nach den Regeln bliebe vom Video nichts übrig. Stil prüfen (zu streng?) oder --stil ruhig.")
    _ablegen(plan, ordner)
    zuletzt_merken(a.stil or stilmodul.GRUNDSTIL)
    if uebernommen:
        sagen(f"  {uebernommen} Entscheidung(en) aus dem bisherigen Plan übernommen (zurück auf die Regeln: aendern --zuruecksetzen).")
    elif alt is not None:
        sagen("  Der bisherige Plan passte nicht mehr zum Transkript — neu nach den Regeln gebaut.")
    return plan, ordner


def _weiter(plan: dict, ordner: Path) -> str:
    """Was als Nächstes aufzurufen ist — mit dem Arbeitsordner, wenn er nicht neben dem Video liegt."""
    video = Path(plan["quelle"])
    ziel = ordner if ordner != video.with_name(video.stem + ".schnitt") else video
    return f'{AUFRUF} rendern "{ziel}" --bilder 3'


def cmd_vorbereiten(a) -> int:
    plan, ordner = vorbereiten(a)
    _ausgeben(plan, ordner)
    sagen(f"\nARBEITSORDNER  {ordner}")
    sagen(f"WEITER         {_weiter(plan, ordner)}   (vorher bei Bedarf: aendern)")
    return 0


def _plan(a) -> tuple[dict, Path, Path | None]:
    video, ordner = orte(a.video)
    return planmodul.lesen(ordner / "schnittplan.json"), ordner, video


def cmd_zeigen(a) -> int:
    plan, ordner, _ = _plan(a)
    if a.von is not None or a.bis is not None:
        if plan.get("vertraulich"):
            raise Abbruch("Dieser Plan ist vertraulich — der Wortlaut wird nicht gezeigt.")
        for zeile in planmodul.textzeilen(plan, max(0, a.von or 0), a.bis):
            sagen(zeile)
        return 0
    _ausgeben(plan, ordner)
    sagen(f"\nARBEITSORDNER  {ordner}")
    return 0


def cmd_aendern(a) -> int:
    plan, ordner, video = _plan(a)
    drehbuch = None
    if a.drehbuch:
        datei = Path(a.drehbuch)
        if not datei.is_file():
            raise Abbruch(f"Die Drehbuch-Datei gibt es nicht: {datei}")
        drehbuch = datei.read_text(encoding="utf-8-sig")
    getan = planmodul.aendern(plan, a.weg, a.doch, a.annehmen, a.ablehnen, a.schnitt, a.halten, a.zuruecksetzen,
                              a.schreibweise, drehbuch, a.betonen, a.unbetonen, a.schlagzeile, a.schlagzeilen_weg)
    if not getan:
        raise Abbruch("Nichts zu ändern angegeben. Möglich: --annehmen k2  --ablehnen k1  --weg 12-18  --doch 40  "
                      "--schnitt 10.5-14.2  --halten 30-33  --schreibweise 12=Raphael  --drehbuch text.txt  "
                      "--betonen 7,21-22  --schlagzeile \"0-6=kleine Zeile|GROSSE ZEILE|Akzentwort\"  --zuruecksetzen")
    planmodul.rechnen(plan, _huelle(ordner, video))
    if not plan["segmente"]:
        raise Abbruch("So bliebe vom Video nichts übrig — der Plan wurde nicht gespeichert.")
    _ablegen(plan, ordner)
    for zeile in getan:
        sagen("  " + (zeile if not plan.get("vertraulich") else zeile.split("„")[0].rstrip(": —")))
    for zeile in planmodul.kurzfassung(plan)[2:]:
        sagen(zeile)
    return 0


def rendern(a, plan: dict | None = None, ordner: Path | None = None) -> int:
    from videoschnitt import rendern as rendermodul

    if plan is None:
        plan, ordner, _ = _plan(a)
    video = Path(plan["quelle"])
    if not video.is_file():
        raise Abbruch(f"Das Rohvideo liegt nicht mehr dort: {video}")
    if video.stat().st_size != plan["quelle_bytes"]:
        raise Abbruch("Das Rohvideo hat sich seit dem Vorbereiten geändert. Erst neu vorbereiten.")
    probe = getattr(a, "probe", None)
    if probe is not None and probe <= 0:
        raise Abbruch("--probe braucht eine Länge über 0 Sekunden, zum Beispiel --probe 10.")
    ziel = rendermodul.ziel_waehlen(video, getattr(a, "ausgabe", None), probe is not None, getattr(a, "ueberschreiben", False))
    dauer = min(probe, plan["statistik"]["dauer_ergebnis"]) if probe else plan["statistik"]["dauer_ergebnis"]
    print(f"  Rendere {planmodul.uhr(dauer)} aus {len(plan['segmente'])} Stücken …", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    bilder = 0 if plan.get("vertraulich") else int(getattr(a, "bilder", 0) or 0)
    klaenge = None
    if getattr(a, "klaenge", None):
        from videoschnitt import klang as klangmodul
        klaenge = klangmodul.lesen(Path(a.klaenge))
    grafik = None
    if not getattr(a, "ohne_grafik", False) and not getattr(a, "ohne_untertitel", False):
        from videoschnitt import grafik as grafikmodul
        da = grafikmodul.vorhanden(plan, ordner)
        if da:
            grafik, klaenge = da[0], (klaenge or []) + da[1]
    ergebnis = rendermodul.rendern(plan, ordner, ziel, untertitel=not getattr(a, "ohne_untertitel", False),
                                   probe=probe, melden=fortschritt("gerendert"), bilder=bilder, klaenge=klaenge, grafik=grafik)
    ergebnis["sekunden"] = round(time.monotonic() - t0, 1)
    rendermodul.bericht_schreiben(plan, ergebnis, ordner)
    for zeile in rendermodul.meldung(plan, ergebnis):
        sagen(zeile)
    return 0 if ergebnis["ok"] else 1


def cmd_rendern(a) -> int:
    return rendern(a)


def cmd_grafik(a) -> int:
    from videoschnitt import grafik as grafikmodul
    from videoschnitt import rendern as rendermodul

    plan, ordner, _ = _plan(a)
    w, h = rendermodul.bildgroesse(plan["auskunft"], plan["stil"]["bild"])
    szenen = Path(a.szenen).expanduser().resolve()
    for sekunde in a.bild or []:
        e = grafikmodul.ablichten(plan, ordner, szenen, w, h, bild=sekunde)
        sagen(f"BILD      {e['ziel']}")
    if a.bild:
        return 0
    print(f"  Lichte {planmodul.uhr(plan['statistik']['dauer_ergebnis'])} Grafik ab (etwa 8 Bilder je Sekunde) …", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    e = grafikmodul.ablichten(plan, ordner, szenen, w, h)
    sagen(f"GRAFIK    {e['ziel']} · {planmodul.uhr(e['dauer'])} · {w}×{h} · {e['klaenge']} Klänge · in {time.monotonic() - t0:.0f} s")
    sagen(f'WEITER    {AUFRUF} rendern "{ordner}"   (die Grafik liegt dann über dem Bild)')
    return 0


def cmd_alles(a) -> int:
    plan, ordner = vorbereiten(a)
    for zeile in planmodul.kurzfassung(plan):
        sagen(zeile)
    offen = sum(1 for k in plan["kandidaten"] if not k["angewandt"] and not k.get("entschieden"))
    if offen:
        sagen(f"  {offen} unsichere Stelle(n) wurden nicht geschnitten"
              + ("." if plan.get("vertraulich") else f" — siehe {ordner / 'schnittplan.txt'}"))
    return rendern(a, plan, ordner)


def cmd_referenz(a) -> int:
    from videoschnitt import referenz

    video, _ = orte(a.video)
    if video is None:
        raise Abbruch("Für die Referenz braucht es ein Video.")
    ergebnis = referenz.auswerten(video, a.bilder, Path(a.ordner) if a.ordner else None)
    for zeile in referenz.meldung(ergebnis):
        sagen(zeile)
    return 0


def cmd_modell_holen(a) -> int:
    mb = umgebung.MODELL_GROESSE_MB.get(a.name)
    if umgebung.modell_ort(a.name):
        sagen(f"Das Modell {a.name} liegt schon auf dem Rechner.")
        return 0
    if not a.ja:
        sagen(f"Das lädt das Whisper-Modell „{a.name}“ von Hugging Face" + (f", ca. {mb} MB" if mb else "") +
              f", nach {umgebung.MODELL_ORDNER}.")
        sagen(f"Nur mit Chefs Ja. Dann:  {AUFRUF} modell-holen {a.name} --ja")
        return 1
    sagen(f"Lade {a.name} …" + (f" (ca. {mb} MB)" if mb else ""))
    sagen(f"Fertig: {transkript.modell_holen(a.name)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for strom in (sys.stdout, sys.stderr):
        # Windows gibt in Rohre sonst cp1252 aus — dann werden Umlaute im Chat zu Fragezeichen.
        try:
            strom.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    def parser(*args, **kw) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(*args, formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False, **kw)
        p._positionals.title, p._optionals.title = "Angaben", "Schalter"
        p.add_argument("-h", "--help", action="help", help="diese Hilfe zeigen")
        return p

    video_hilfe = "Rohvideo oder Arbeitsordner (<name>.schnitt)"
    p = parser(prog="schnitt.py", description=__doc__)
    sub = p.add_subparsers(dest="befehl", required=True, metavar="BEFEHL", parser_class=lambda **kw: parser(**kw))

    s = sub.add_parser("pruefen", help="ist alles da, was das Modul braucht?")
    s.add_argument("--json", action="store_true", help="Ergebnis als JSON")
    s.set_defaults(lauf=cmd_pruefen)

    sub.add_parser("stile", help="alle Stile mit Format und Beschreibung").set_defaults(lauf=cmd_stile)

    def gemeinsam(s) -> None:
        s.add_argument("video", help="das Rohvideo")
        s.add_argument("--stil", help="Name eines Stils, Pfad zu einer Stil-Datei oder „letzter“ (Vorgabe: standard)")
        s.add_argument("--sprache", help="Sprache des Videos, z. B. de oder en (Vorgabe: aus dem Stil)")
        s.add_argument("--modell", help="Whisper-Modell (Vorgabe: das beste, das auf dem Rechner liegt)")
        s.add_argument("--neu", action="store_true", help="neu transkribieren, auch wenn ein Transkript da ist")
        s.add_argument("--namen", help="Eigennamen und Fachwörter aus dem Video, mit Komma getrennt — werden dann eher richtig erkannt")
        s.add_argument("--ordner", help="Arbeitsordner woanders als neben dem Video (dann bei zeigen/aendern/rendern diesen Ordner angeben)")
        s.add_argument("--vertraulich", action="store_true",
                       help="kein Wort aus dem Video in Ausgabe und Übersicht (für Aufnahmen, die das Modell nicht lesen soll)")

    s = sub.add_parser("vorbereiten", help="transkribieren und Schnittplan nach Regeln bauen",
                       description="Transkribiert (einmal, danach aus dem Arbeitsordner) und baut den Plan nach den Regeln des Stils. "
                                   "Ein zweiter Aufruf mit anderem Stil behält die Entscheidungen aus aendern.")
    gemeinsam(s)
    s.set_defaults(lauf=cmd_vorbereiten)

    s = sub.add_parser("zeigen", help="den Schnittplan lesen (ändert nichts)",
                       description="Zeigt Zahlen, offene Stellen und den Wortlaut. Jede Textzeile: Nummer des ersten Wortes | Zeit im "
                                   "Rohvideo | Zeit im fertigen Video | Wörter. [-so-] fliegt raus, ‖1,8 ist eine Pause in Sekunden, "
                                   "die gekürzt wird, *so* ist im Untertitel betont.")
    s.add_argument("video", help=video_hilfe)
    s.add_argument("--von", type=int, metavar="WORT", help="nur den Wortlaut ab dieser Wortnummer")
    s.add_argument("--bis", type=int, metavar="WORT", help="… bis zu dieser Wortnummer")
    s.set_defaults(lauf=cmd_zeigen)

    s = sub.add_parser("aendern", help="den Schnittplan ändern",
                       description="Ändert den Plan und sagt wörtlich, was geändert wurde. Wortnummern stehen in der Übersicht. "
                                   "Zeitbereiche sind Sekunden des ROHVIDEOS; die spätere Anweisung gewinnt (ein --halten hebt einen "
                                   "--schnitt an derselben Stelle auf und umgekehrt).")
    s.add_argument("video", help=video_hilfe)
    s.add_argument("--annehmen", default="", metavar="K", help="Kandidaten annehmen (fliegen raus): k2,k5")
    s.add_argument("--ablehnen", default="", metavar="K", help="Kandidaten ablehnen (bleiben drin, gelten als entschieden): k1")
    s.add_argument("--weg", default="", metavar="WÖRTER", help="Wörter rausnehmen: 12-18,40")
    s.add_argument("--doch", default="", metavar="WÖRTER", help="Wörter doch behalten: 12-18,40")
    s.add_argument("--schnitt", default="", metavar="SEK", help="Zeitbereich des Rohvideos rausnehmen: 10.5-14.2")
    s.add_argument("--halten", default="", metavar="SEK", help="Zeitbereich des Rohvideos in jedem Fall behalten: 30-33")
    s.add_argument("--schreibweise", action="append", metavar="NR=WORT",
                   help="ein falsch erkanntes Wort richtig schreiben: 12=Raphael (mehrfach möglich)")
    s.add_argument("--drehbuch", metavar="DATEI",
                   help="Textdatei mit dem gesprochenen Text: ihre Schreibweise ersetzt die erkannte, wo beides zusammenpasst")
    s.add_argument("--betonen", default="", metavar="WÖRTER", help="Wörter im Untertitel hervorheben: 7,21-22")
    s.add_argument("--unbetonen", default="", metavar="WÖRTER", help="Hervorhebung wieder wegnehmen")
    s.add_argument("--schlagzeile", action="append", metavar="VON-BIS=TEXT",
                   help="große Zeile oben im Bild, solange diese Wörter gesprochen werden: \"0-6=kleine Zeile|GROSSE ZEILE|Akzentwort\" "
                        "(kleine Zeile und Akzentwort dürfen fehlen; mehrfach möglich)")
    s.add_argument("--schlagzeilen-weg", action="store_true", help="alle Schlagzeilen entfernen")
    s.add_argument("--zuruecksetzen", action="store_true",
                   help="zurück auf den Stand nach den Regeln — auch Schreibweisen, Betonungen, Zeitbereiche und Schlagzeilen")
    s.set_defaults(lauf=cmd_aendern)

    def ausgabe(s) -> None:
        s.add_argument("--ausgabe", help="Zieldatei (Vorgabe: <name>-geschnitten.mp4 neben dem Rohvideo, bei vorhandener Datei -2, -3 …)")
        s.add_argument("--ueberschreiben", action="store_true", help="eine vorhandene --ausgabe ersetzen")
        s.add_argument("--ohne-untertitel", action="store_true", help="nichts einbrennen (auch keine Schlagzeilen, kein Balken)")
        s.add_argument("--ohne-grafik", action="store_true", help="eine abgelichtete Bewegungsgrafik (grafik.mov im Arbeitsordner) weglassen")
        s.add_argument("--klaenge", metavar="DATEI",
                       help="eigene Effekt-Klänge als JSON-Liste: zeit (Sekunde im fertigen Video), art (wusch, pop, tick, klick, glocke, tiefe, aufstieg, schnipp), staerke (0 bis 1)")
        s.add_argument("--probe", type=float, metavar="SEK",
                       help="nur die ersten SEK Sekunden rendern, nach <name>-probe.mp4 (wird jedes Mal ersetzt)")
        s.add_argument("--bilder", type=int, default=0, metavar="N",
                       help="N Standbilder des Ergebnisses als blick-1.png … in den Arbeitsordner legen (Anfang, breiteste Zeile, Ende)")

    s = sub.add_parser("rendern", help="das fertige Video bauen")
    s.add_argument("video", help=video_hilfe)
    ausgabe(s)
    s.set_defaults(lauf=cmd_rendern)

    s = sub.add_parser("grafik", help="Bewegungsgrafik für das Video ablichten (liegt beim Rendern dann über dem Bild)",
                       description="Lichtet eine Szenen-Seite (HTML, Aufbau siehe grafik\\motor.js) durchsichtig ab, im Takt der Wörter "
                                   "des Schnittplans. Das Ergebnis grafik.mov liegt im Arbeitsordner; „rendern“ legt es über das Bild "
                                   "und unter die Untertitel. Nach jeder Änderung am Schnitt neu ablichten.")
    s.add_argument("video", help=video_hilfe)
    s.add_argument("--szenen", required=True, metavar="SEITE", help="die Szenen-Seite (.html)")
    s.add_argument("--bild", type=float, action="append", metavar="SEK",
                   help="nur ein Standbild dieser Sekunde des fertigen Videos (PNG, durchsichtig) — zum Ansehen, mehrfach möglich")
    s.set_defaults(lauf=cmd_grafik)

    s = sub.add_parser("alles", help="vorbereiten und rendern in einem Zug, nur nach Regeln")
    gemeinsam(s)
    ausgabe(s)
    s.set_defaults(lauf=cmd_alles)

    s = sub.add_parser("referenz", help="Standbilder und Takt eines Vorbild-Videos herausziehen")
    s.add_argument("video", help="das Vorbild-Video (eine Datei auf dem Rechner)")
    s.add_argument("--bilder", type=int, default=8, help="wie viele Standbilder (Vorgabe 8)")
    s.add_argument("--ordner", help="wohin Bilder und Messwerte kommen (Vorgabe: <name>.referenz neben dem Vorbild)")
    s.set_defaults(lauf=cmd_referenz)

    s = sub.add_parser("modell-holen", help="ein Whisper-Modell aus dem Netz laden (nur mit Chefs Ja)")
    s.add_argument("name", choices=list(umgebung.MODELL_VORLIEBE))
    s.add_argument("--ja", action="store_true", help="Chef hat zugestimmt")
    s.set_defaults(lauf=cmd_modell_holen)

    a = p.parse_args(argv)
    try:
        return a.lauf(a)
    except ModulFehler as e:
        print(f"FEHLER: {e}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("ABGEBROCHEN", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
