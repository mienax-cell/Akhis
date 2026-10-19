"""Schnittplan — die eine Datei, die sagt, was aus dem Rohvideo wird (``schnittplan.json``).

Der Plan wird nie von Hand bearbeitet. Geändert wird er über ``aendern`` (Wortnummern, Kandidaten,
Zeitbereiche, Schreibweisen, Betonungen, Schlagzeilen); danach sind Segmente und Zahlen neu gerechnet
und die Übersicht neu geschrieben.

Was im Plan zusätzlich zu den Wörtern steht:
- ``kandidaten`` — mögliche Versprecher, mit ``entschieden`` (angenommen/abgelehnt), sobald jemand entschied
- ``zeit_schnitte`` / ``zeit_halten`` — Zeitbereiche des Rohvideos, die raus müssen oder in jedem Fall bleiben
- ``schlagzeilen`` — große Zeilen oben im Bild, an Wortnummern gebunden
- an jedem Wort: ``hand`` (von wem die Entscheidung stammt), ``betont`` (im Untertitel hervorgehoben),
  ``w_erkannt`` (was Whisper schrieb, falls die Schreibweise geändert wurde)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path

from . import ModulFehler
from . import schnittlogik as sl
from .medien import Huelle, bildrate_waehlen

PLAN_VERSION = 2
GRUND_TEXT = {"fuellwort": "Füllwort", "wiederholung": "Wiederholung", "neuansatz": "Neuansatz",
              "doppelter_satz": "doppelter Satz", "manuell": "von Hand", "pause": "Pause/Stille", "rand": "Anfang/Ende"}
ZEILE_MAX = 8            # Wörter je Zeile in der Übersicht — kurz genug, um die Nummer eines Wortes sicher abzuzählen
DREHBUCH_MINDESTENS = 0.6  # so viel vom Text muss zum Video passen, sonst wird nichts geändert
_ZAHL = re.compile(r"\d")
BETONT_WOERTER = frozenset("euro prozent million millionen milliarde milliarden tausend".split())


class PlanFehler(ModulFehler):
    pass


def schreiben(pfad: Path, daten: dict) -> None:
    """JSON als UTF-8 ohne BOM, erst daneben und dann umbenannt — ein Abbruch hinterlässt keinen halben Plan."""
    neben = pfad.with_suffix(pfad.suffix + ".neu")
    neben.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    neben.replace(pfad)


def lesen(pfad: Path) -> dict:
    if not pfad.is_file():
        raise PlanFehler(f"Es gibt noch keinen Schnittplan ({pfad}). Zuerst vorbereiten. Wurde mit --ordner vorbereitet, "
                         "hier den Arbeitsordner statt des Videos angeben.")
    plan = json.loads(pfad.read_text(encoding="utf-8"))
    if plan.get("version") != PLAN_VERSION:
        raise PlanFehler("Der Schnittplan stammt von einer anderen Fassung des Moduls. Neu anlegen mit vorbereiten "
                         "(das Transkript bleibt erhalten).")
    return plan


def betonen_auto(woerter: list[dict], art: str) -> int:
    """Wörter markieren, die im Untertitel hervorstechen sollen. ``zahlen``: Zahlen, Prozent, Geld —
    an ihnen bleibt das Auge hängen. Von Hand gesetzte oder gelöschte Betonungen bleiben unberührt."""
    n = 0
    for w in woerter:
        if w.get("betont_hand"):
            continue
        soll = art == "zahlen" and bool(_ZAHL.search(w["w"]) or "%" in w["w"] or "€" in w["w"]
                                        or sl.norm(w["w"]) in BETONT_WOERTER)
        w["betont"] = soll
        n += soll
    return n


def _uebernehmen(plan: dict, alt: dict) -> int:
    """Entscheidungen aus dem alten Plan in den neuen tragen (gleiches Transkript, anderer Stil)."""
    n = 0
    for neu_w, alt_w in zip(plan["woerter"], alt["woerter"]):
        if "w_erkannt" in alt_w:
            neu_w["w"], neu_w["w_erkannt"] = alt_w["w"], alt_w["w_erkannt"]
            n += 1
        if alt_w.get("betont_hand"):
            neu_w["betont"], neu_w["betont_hand"] = alt_w.get("betont", False), True
            n += 1
    nach_ort = {(k["art"], k["von"], k["bis"]): k for k in plan["kandidaten"]}
    for k in alt.get("kandidaten", []):
        passend = nach_ort.get((k["art"], k["von"], k["bis"]))
        if passend and k.get("entschieden"):
            sl.kandidat_setzen(plan["woerter"], passend, k["entschieden"] == "angenommen")
            passend["entschieden"] = k["entschieden"]
            n += 1
    for neu_w, alt_w in zip(plan["woerter"], alt["woerter"]):
        if alt_w.get("hand") in ("weg", "schnitt"):
            neu_w["weg"], neu_w["hand"] = "manuell", alt_w["hand"]
            n += alt_w["hand"] == "weg"
        elif alt_w.get("hand") == "doch":
            neu_w["weg"], neu_w["hand"] = None, "doch"
            n += 1
    for name in ("zeit_schnitte", "zeit_halten", "schlagzeilen"):
        plan[name] = [list(x) if isinstance(x, list) else dict(x) for x in alt.get(name, [])]
        n += len(plan[name])
    return n


def neu(video: Path, info: dict, stil: dict, transkript: dict, alt: dict | None = None) -> tuple[dict, int]:
    """Aus Transkript und Stil den Plan bauen: Füllwörter und sichere Versprecher sind markiert.

    ``alt`` ist der bisherige Plan desselben Transkripts (Stilwechsel): Seine Entscheidungen bleiben.
    Zweiter Wert: wie viele übernommen wurden.
    """
    woerter = [dict(w, weg=None) for w in transkript["woerter"]]
    opt = stil["schnitt"]
    sl.fuellwoerter_markieren(woerter, opt)
    kandidaten = sl.kandidaten_finden(woerter, opt)
    sl.kandidaten_anwenden(woerter, kandidaten, bool(opt.get("unsichere_anwenden")))
    st = video.stat()
    plan = {
        "version": PLAN_VERSION,
        "erstellt": datetime.now().isoformat(timespec="seconds"),
        "quelle": str(video),
        "quelle_bytes": st.st_size,
        "quelle_geaendert": int(st.st_mtime),
        "auskunft": info,
        "bildrate": "{0.numerator}/{0.denominator}".format(bildrate_waehlen(info, stil["bild"]["fps"])),
        "stil": {k: v for k, v in stil.items() if not k.startswith("_")},
        "transkription": {k: v for k, v in transkript.items() if k != "woerter"},
        "woerter": woerter,
        "kandidaten": kandidaten,
        "zeit_schnitte": [],
        "zeit_halten": [],
        "schlagzeilen": [],
        "segmente": [],
        "statistik": {},
    }
    uebernommen = 0
    if alt and len(alt.get("woerter", [])) == len(woerter) \
            and alt.get("transkription", {}).get("schluessel") == transkript.get("schluessel"):
        uebernommen = _uebernehmen(plan, alt)
    betonen_auto(woerter, stil["untertitel"].get("betonen", "aus"))
    return plan, uebernommen


def rechnen(plan: dict, huelle: Huelle | None) -> None:
    """Segmente und Zahlen aus dem jetzigen Stand der Wörter neu rechnen."""
    fps = Fraction(plan["bildrate"])
    for k in plan["kandidaten"]:
        teile = plan["woerter"][k["von"]:k["bis"] + 1]
        k["angewandt"] = all(w.get("weg") for w in teile)
    plan["segmente"] = sl.segmente_bauen(plan["woerter"], plan["auskunft"]["dauer"], fps, plan["stil"]["schnitt"],
                                         huelle, plan["zeit_schnitte"], plan["zeit_halten"])
    plan["statistik"] = sl.statistik(plan["woerter"], plan["segmente"], plan["auskunft"]["dauer"], plan["kandidaten"])


# ---------------------------------------------------------------------------------------------------
# Ändern

def _bereiche(text: str, hoechstens: int) -> list[tuple[int, int]]:
    """„12-18,40“ → [(12, 18), (40, 40)]"""
    aus = []
    for stueck in (text or "").replace(" ", "").split(","):
        if not stueck:
            continue
        a, _, b = stueck.partition("-")
        try:
            von, bis = int(a), int(b or a)
        except ValueError:
            raise PlanFehler(f"„{stueck}“ ist kein Wortbereich. So geht es: 12-18,40") from None
        if not 0 <= von <= bis <= hoechstens:
            raise PlanFehler(f"Wortbereich {stueck} liegt außerhalb von 0 bis {hoechstens}")
        aus.append((von, bis))
    return aus


def _zeiten(text: str, dauer: float) -> list[list[float]]:
    """„10.5-14.2,30-33“ → [[10.5, 14.2], [30.0, 33.0]] (Sekunden im Rohvideo)"""
    aus = []
    for stueck in (text or "").replace(" ", "").split(","):
        if not stueck:
            continue
        a, _, b = stueck.partition("-")
        try:
            von, bis = float(a), float(b)
        except ValueError:
            raise PlanFehler(f"„{stueck}“ ist kein Zeitbereich. So geht es: 10.5-14.2 (Sekunden im Rohvideo)") from None
        if not 0 <= von < bis <= dauer + 0.5:
            raise PlanFehler(f"Zeitbereich {stueck} liegt außerhalb von 0 bis {dauer:.1f} s")
        aus.append([von, min(bis, dauer)])
    return aus


def _ohne(bereiche: list, von: float, bis: float) -> list[list[float]]:
    """Aus einer Liste von Zeitbereichen das Stück [von, bis] herausnehmen."""
    return [[a, b] for a, b in sl._abziehen([(float(x), float(y)) for x, y in bereiche], [(von, bis)]) if b - a > 0.02]


def drehbuch_anwenden(woerter: list[dict], text: str) -> list[str]:
    """Liegt der gesprochene Text schon vor (Drehbuch, vorgelesener Beitrag), gilt seine Schreibweise.

    Whisper liefert die Zeiten, das Drehbuch die Wörter: Namen, Satzzeichen und Großschreibung stimmen
    dann. Vorsichtig, weil ein falsch zugeordnetes Wort schlimmer ist als ein falsch geschriebenes:
    - Abgeglichen wird nur mit den Wörtern, die im Video bleiben — ein geschnittenes „ähm“ oder ein
      verworfener Anlauf bekommt keinen Drehbuchtext.
    - Ersetzt wird nur, wo beides zusammenpasst: dasselbe Wort anders geschrieben, ein ähnliches Wort
      („Magie“ → „MAGI“) oder dieselben Zeichen anders getrennt („2“ + „,4“ → „2,4“).
    - Passt das Drehbuch insgesamt nicht zum Video, wird gar nichts geändert.
    """
    soll = text.split()
    bleibt = [w for w in woerter if not w.get("weg")]
    ist = [sl.norm(w.get("w_erkannt", w["w"])) for w in bleibt]
    ziel = [sl.norm(s) for s in soll]
    passend = SequenceMatcher(None, ist, ziel, autojunk=False)
    gleich = sum(b.size for b in passend.get_matching_blocks())
    anteil = gleich / max(1, len(ist), len(ziel))
    if anteil < DREHBUCH_MINDESTENS:
        raise PlanFehler(f"Das Drehbuch passt nicht zu diesem Video ({gleich} von {max(len(ist), len(ziel))} Wörtern gleich) "
                         "— nichts geändert. Ist es die richtige Datei?")

    def setzen(w: dict, neu: str) -> int:
        if neu == w["w"]:
            return 0
        w.setdefault("w_erkannt", w["w"])
        w["w"] = neu
        return 1

    anders, offen = 0, []
    for art, i0, i1, j0, j1 in passend.get_opcodes():
        n, m = i1 - i0, j1 - j0
        if art == "equal":
            anders += sum(setzen(bleibt[i0 + k], soll[j0 + k]) for k in range(n))
        elif art == "replace" and n == m:
            for k in range(n):
                a, b = ist[i0 + k], ziel[j0 + k]
                if sl.aehnlich(a, b) or SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.6:
                    anders += setzen(bleibt[i0 + k], soll[j0 + k])
                else:
                    offen.append(f"{bleibt[i0 + k]['i']} „{bleibt[i0 + k]['w']}“ ↔ „{soll[j0 + k]}“")
        elif art == "replace" and "".join(ist[i0:i1]) == "".join(ziel[j0:j1]):
            # Dieselben Zeichen, nur anders in Wörter geteilt: Die ersten Wörter bekommen den Text, was
            # Whisper mehr hat, bleibt im Untertitel leer (seine Zeit gehört weiter zum Wort davor).
            for k in range(n):
                neu = soll[j0 + k] if k < min(n, m) - 1 else " ".join(soll[j0 + k:j1]) if k == min(n, m) - 1 else ""
                anders += setzen(bleibt[i0 + k], neu)
        elif art in ("replace", "delete"):
            offen.append(f"{bleibt[i0]['i']}–{bleibt[i1 - 1]['i']} „{sl._text(woerter, bleibt[i0]['i'], bleibt[i1 - 1]['i'])}“"
                         + (f" ↔ „{' '.join(soll[j0:j1])}“" if m else " (fehlt im Drehbuch)"))
        elif art == "insert":
            offen.append(f"nach Wort {bleibt[i0 - 1]['i'] if i0 else 0}: „{' '.join(soll[j0:j1])}“ steht im Drehbuch, wurde aber nicht gehört")
    getan = [f"Drehbuch angewandt: {anders} Wörter richtiggestellt, {gleich} von {len(ist)} Wörtern stimmen im Wortlaut ({anteil:.0%})"]
    if offen:
        getan.append(f"{len(offen)} Stelle(n) passen nicht und bleiben, wie sie erkannt wurden: " + " · ".join(offen[:6])
                     + (" …" if len(offen) > 6 else ""))
    return getan


def _schlagzeile(angabe: str, letztes: int) -> dict:
    """„0-6=Cutter wollen nicht, dass du|das weißt.|weißt.“ → Schlagzeile über den Wörtern 0 bis 6."""
    bereich, trenner, rest = angabe.partition("=")
    teile = [t.strip() for t in rest.split("|")]
    if not trenner or not teile or not teile[-1 if len(teile) == 1 else 1]:
        raise PlanFehler(f"„{angabe}“ versteht --schlagzeile nicht. So geht es: 0-6=kleine Zeile|GROSSE ZEILE|Akzentwort "
                         "(kleine Zeile und Akzentwort dürfen fehlen: 0-6=GROSSE ZEILE)")
    bereiche = _bereiche(bereich, letztes)
    if len(bereiche) != 1:
        raise PlanFehler(f"„{angabe}“: vor dem = steht genau ein Wortbereich, zum Beispiel 0-6.")
    von, bis = bereiche[0]
    klein, gross, akzent = ("", teile[0], "") if len(teile) == 1 else (teile[0], teile[1], teile[2] if len(teile) > 2 else "")
    if akzent and akzent not in gross:
        raise PlanFehler(f"Das Akzentwort „{akzent}“ kommt in der großen Zeile „{gross}“ nicht vor.")
    return {"von": von, "bis": bis, "klein": klein, "gross": gross, "akzent": akzent}


def aendern(plan: dict, weg: str = "", doch: str = "", annehmen: str = "", ablehnen: str = "",
            schnitt: str = "", halten: str = "", zuruecksetzen: bool = False, schreibweise: list[str] | None = None,
            drehbuch: str | None = None, betonen: str = "", unbetonen: str = "", schlagzeile: list[str] | None = None,
            schlagzeilen_weg: bool = False) -> list[str]:
    """Den Plan ändern. Liefert Zeilen, die sagen, was wirklich geschehen ist — zum Gegenprüfen."""
    woerter, getan = plan["woerter"], []
    letztes = len(woerter) - 1
    dauer = plan["auskunft"]["dauer"]
    nach_id = {k["id"]: k for k in plan["kandidaten"]}

    if zuruecksetzen:
        schreibweisen = 0
        for w in woerter:
            w["weg"] = None
            w.pop("hand", None)
            w.pop("betont_hand", None)
            if "w_erkannt" in w:
                w["w"] = w.pop("w_erkannt")
                schreibweisen += 1
        sl.fuellwoerter_markieren(woerter, plan["stil"]["schnitt"])
        for k in plan["kandidaten"]:
            k["angewandt"] = False
            k.pop("entschieden", None)
        sl.kandidaten_anwenden(woerter, plan["kandidaten"], bool(plan["stil"]["schnitt"].get("unsichere_anwenden")))
        betonen_auto(woerter, plan["stil"]["untertitel"].get("betonen", "aus"))
        plan["zeit_schnitte"], plan["zeit_halten"], plan["schlagzeilen"] = [], [], []
        getan.append("zurückgesetzt auf den Stand nach den Regeln"
                     + (f" — auch {schreibweisen} Schreibweisen sind wieder wie erkannt" if schreibweisen else ""))

    for kennung, an in [(x, True) for x in annehmen.replace(" ", "").split(",") if x] + \
                       [(x, False) for x in ablehnen.replace(" ", "").split(",") if x]:
        k = nach_id.get(kennung)
        if k is None:
            raise PlanFehler(f"Kandidat „{kennung}“ gibt es nicht. Vorhanden: {', '.join(nach_id) or 'keiner'}")
        sl.kandidat_setzen(woerter, k, an)
        k["entschieden"] = "angenommen" if an else "abgelehnt"
        getan.append(f"{kennung} {'angenommen — raus' if an else 'abgelehnt — bleibt'}: {k['von']}–{k['bis']} „{k['text']}“")

    for von, bis in _bereiche(weg, letztes):
        for w in woerter[von:bis + 1]:
            if not w.get("weg"):
                w["weg"], w["hand"] = "manuell", "weg"
        getan.append(f"raus: {von}–{bis} „{sl._text(woerter, von, bis)}“")

    for von, bis in _bereiche(doch, letztes):
        for w in woerter[von:bis + 1]:
            if w.get("hand") == "schnitt":     # lag in einem Zeitbereich, der raus sollte: den dort öffnen
                plan["zeit_schnitte"] = _ohne(plan["zeit_schnitte"], w["von"] - 0.05, w["bis"] + 0.05)
            w["weg"], w["hand"] = None, "doch"
        getan.append(f"bleibt doch: {von}–{bis} „{sl._text(woerter, von, bis)}“")

    if drehbuch:
        getan += drehbuch_anwenden(woerter, drehbuch)

    for angabe in schreibweise or []:
        nummer, trenner, text = angabe.partition("=")
        text = text.strip()
        if not trenner or not nummer.strip().isdigit() or not text or " " in text:
            raise PlanFehler(f"„{angabe}“ versteht --schreibweise nicht. So geht es: 12=Raphael (ein Wort, Satzzeichen dürfen dran)")
        nr = int(nummer)
        if not 0 <= nr <= letztes:
            raise PlanFehler(f"Wort {nr} gibt es nicht (0 bis {letztes})")
        w = woerter[nr]
        w.setdefault("w_erkannt", w["w"])
        getan.append(f"Schreibweise: Wort {nr} „{w['w']}“ → „{text}“")
        w["w"] = text

    for bereiche, an in ((betonen, True), (unbetonen, False)):
        for von, bis in _bereiche(bereiche, letztes):
            for w in woerter[von:bis + 1]:
                w["betont"], w["betont_hand"] = an, True
            getan.append(f"{'betont' if an else 'nicht mehr betont'}: {von}–{bis} „{sl._text(woerter, von, bis)}“")

    # Zeitbereiche: Die spätere Anweisung gewinnt. Ein neues --halten hebt einen Schnitt an derselben
    # Stelle auf und umgekehrt — sonst stünden beide im Plan und niemand wüsste, was gilt.
    for von, bis in _zeiten(schnitt, dauer):
        plan["zeit_halten"] = _ohne(plan["zeit_halten"], von, bis)
        plan["zeit_schnitte"].append([von, bis])
        treffer = [w for w in woerter if von <= (w["von"] + w["bis"]) / 2 < bis]
        for w in treffer:
            if not w.get("weg"):
                w["weg"], w["hand"] = "manuell", "schnitt"
        zeile = f"Zeitbereich raus: {von:.2f}–{bis:.2f} s".replace(".", ",")
        if treffer:
            zeile += f" — trifft Wörter {treffer[0]['i']}–{treffer[-1]['i']} „{sl._text(woerter, treffer[0]['i'], treffer[-1]['i'])}“"
        angeschnitten = [w for w in woerter if not w.get("weg") and (w["von"] + 0.03 < von < w["bis"] - 0.03
                                                                      or w["von"] + 0.03 < bis < w["bis"] - 0.03)]
        if angeschnitten:
            zeile += " · Achtung: schneidet mitten in " + ", ".join(f"Wort {w['i']} „{w['w']}“" for w in angeschnitten[:2])
        getan.append(zeile)
    for von, bis in _zeiten(halten, dauer):
        vorher = len(plan["zeit_schnitte"])
        plan["zeit_schnitte"] = _ohne(plan["zeit_schnitte"], von, bis)
        zurueck = 0
        for w in woerter:
            if w.get("hand") == "schnitt" and von <= (w["von"] + w["bis"]) / 2 < bis:
                w["weg"] = None
                w.pop("hand")
                zurueck += 1
        plan["zeit_halten"].append([von, bis])
        getan.append(f"Zeitbereich bleibt in jedem Fall: {von:.2f}–{bis:.2f} s".replace(".", ",")
                     + (f" — ein Schnitt dort ist aufgehoben, {zurueck} Wörter sind wieder drin"
                        if zurueck or len(plan["zeit_schnitte"]) != vorher else ""))

    if schlagzeilen_weg:
        getan.append(f"{len(plan['schlagzeilen'])} Schlagzeile(n) entfernt")
        plan["schlagzeilen"] = []
    for angabe in schlagzeile or []:
        s = _schlagzeile(angabe, letztes)
        plan["schlagzeilen"] = [x for x in plan["schlagzeilen"] if x["bis"] < s["von"] or x["von"] > s["bis"]] + [s]
        plan["schlagzeilen"].sort(key=lambda x: x["von"])
        getan.append(f"Schlagzeile über den Wörtern {s['von']}–{s['bis']}: " + (f"{s['klein']} / " if s["klein"] else "")
                     + s["gross"] + (f" (Akzent: {s['akzent']})" if s["akzent"] else ""))

    # Wer --doch oder --weg auf die Wörter eines Kandidaten anwendet, hat ihn damit entschieden.
    for k in plan["kandidaten"]:
        teile = woerter[k["von"]:k["bis"] + 1]
        if any(w.get("hand") == "doch" for w in teile) and not any(w.get("weg") for w in teile):
            k["entschieden"] = "abgelehnt"
        elif all(w.get("weg") for w in teile) and any(w.get("hand") in ("weg", "schnitt") for w in teile):
            k["entschieden"] = "angenommen"
    return getan


# ---------------------------------------------------------------------------------------------------
# Übersicht

def uhr(t: float) -> str:
    """Sekunden als mm:ss,z — erst auf Zehntel runden, dann teilen (sonst wird aus 59,96 s „00:60,0“)."""
    z = round(max(0.0, t) * 10)
    return f"{z // 600:02d}:{z % 600 // 10:02d},{z % 10}"


def kurzfassung(plan: dict) -> list[str]:
    """Die Zahlen in vier Zeilen — ohne ein Wort aus dem Video."""
    st, info = plan["statistik"], plan["auskunft"]
    sek, stk, stellen = st["sekunden"], st["stueck"], st.get("stellen", {})
    teile = []
    for g in ("pause", "fuellwort", "wiederholung", "neuansatz", "doppelter_satz", "manuell", "rand"):
        if sek.get(g, 0) >= 0.05 or stk.get(g, 0):
            n, s = stk.get(g, 0), stellen.get(g, 0)
            zusatz = (f" ({n}×)" if n and g in ("pause", "fuellwort")
                      else f" ({s} Stelle{'n' if s != 1 else ''}, {n} Wörter)" if n else "")
            teile.append(f"{GRUND_TEXT[g]} −{sek.get(g, 0):.1f} s".replace(".", ",") + zusatz)
    tr = plan["transkription"]
    quer = info["breite"] > info["hoehe"] and plan["stil"]["bild"]["format"] == "original"
    return [
        f"VIDEO     {Path(plan['quelle']).name} · {uhr(info['dauer'])} · {info['breite']}×{info['hoehe']} · "
        f"{float(Fraction(plan['bildrate'])):.4g} Bilder/s" + (f" · HDR ({info['hdr']})" if info.get("hdr") else "")
        + (" · Querformat bleibt quer (der Stil lässt das Format)" if quer else ""),
        f"ERKANNT   {st['woerter']} Wörter · Sprache {tr['sprache']} · Modell {tr['modell']} auf "
        f"{'Grafikkarte' if tr['geraet'] == 'cuda' else 'Prozessor'} in {tr['sekunden_rechnen']:.1f} s".replace(".", ","),
        f"ERGEBNIS  {uhr(st['dauer_ergebnis'])} statt {uhr(st['dauer_roh'])} "
        f"(−{st['gekuerzt']:.1f} s, {st['segmente']} Stücke) · Stil {plan['stil']['name']}".replace(".", ","),
        "RAUS      " + (" · ".join(teile) if teile else "nichts"),
    ]


def kandidaten_zeilen(plan: dict) -> list[str]:
    """Die Versprecher-Stellen in drei Gruppen: offen, entschieden, geschnitten."""
    def zeile(k: dict) -> str:
        return f"  {k['id']:>4}  Wörter {k['von']}–{k['bis']}  „{k['text']}“  ·  {k['grund']}"

    offen = [k for k in plan["kandidaten"] if not k["angewandt"] and not k.get("entschieden")]
    bleibt = [k for k in plan["kandidaten"] if not k["angewandt"] and k.get("entschieden")]
    raus = [k for k in plan["kandidaten"] if k["angewandt"]]
    zeilen: list[str] = []
    if offen:
        zeilen += ["", "OFFEN — nicht geschnitten, bitte entscheiden (annehmen = fliegt raus, ablehnen = bleibt und gilt als entschieden):"]
        zeilen += [zeile(k) for k in offen]
    if raus:
        zeilen += ["", "GESCHNITTEN (ablehnen = bleibt doch drin):"] + [zeile(k) for k in raus]
    if bleibt:
        zeilen += ["", "ENTSCHIEDEN — bleibt drin:"] + [zeile(k) for k in bleibt]
    if plan["zeit_schnitte"] or plan["zeit_halten"]:
        zeilen.append("")
        zeilen += [f"ZEITBEREICH RAUS    {a:.2f}–{b:.2f} s (Rohvideo)".replace(".", ",") for a, b in plan["zeit_schnitte"]]
        zeilen += [f"ZEITBEREICH BLEIBT  {a:.2f}–{b:.2f} s (Rohvideo)".replace(".", ",") for a, b in plan["zeit_halten"]]
    if plan.get("schlagzeilen"):
        zeilen.append("")
        zeilen += [f"SCHLAGZEILE  Wörter {s['von']}–{s['bis']}: " + (f"{s['klein']} / " if s["klein"] else "") + s["gross"]
                   for s in plan["schlagzeilen"]]
    return zeilen


def textzeilen(plan: dict, von: int = 0, bis: int | None = None) -> list[str]:
    """Der Wortlaut mit Wortnummern. Jede Zeile: Nummer des ersten Wortes, Zeit im Rohvideo, Zeit im
    fertigen Video (leer, wenn die ganze Zeile rausfliegt), dann die Wörter."""
    woerter, opt = plan["woerter"], plan["stil"]["schnitt"]
    achse = sl.Zeitachse(plan["segmente"])
    bis = len(woerter) - 1 if bis is None else min(bis, len(woerter) - 1)
    zeilen: list[str] = []
    zeile: list[str] = []
    drin: list[dict] = []
    erste = von

    def raus() -> None:
        if not zeile:
            return
        fertig = next((achse.wort(w["von"], w["bis"]) for w in drin if not w.get("weg")), None)
        zeilen.append(f"{erste:5d} | {uhr(woerter[erste]['von'])} | {uhr(fertig[0]) if fertig else '   –   '} | " + " ".join(zeile))
        zeile.clear()
        drin.clear()

    def gekuerzt(a: float, b: float) -> bool:
        """Liegt zwischen a und b wirklich ein Schnitt? Nur dann ist die Pause „gekürzt“."""
        return not any(s["von"] <= a and b <= s["bis"] for s in plan["segmente"])

    for w in woerter[von:bis + 1]:
        if not zeile:
            erste = w["i"]
        # Ein Listenplatz = genau ein Stück in der Zeile: leere Wörter als „·“, Leerzeichen im Wort als „_“.
        text = (w["w"] or "·").replace(" ", "_")
        text = f"*{text}*" if w.get("betont") and not w.get("weg") else text
        zeile.append(f"[-{text}-]" if w.get("weg") else text)
        drin.append(w)
        danach = woerter[w["i"] + 1] if w["i"] < len(woerter) - 1 else None
        nach = danach["von"] - w["bis"] if danach else 0.0
        lang = nach >= opt["pause_ab"]
        if lang and not w.get("weg") and not danach.get("weg"):
            zeile.append(f"‖{nach:.1f}".replace(".", ",") + ("" if gekuerzt(w["bis"], danach["von"]) else "(bleibt)"))
        if len(drin) >= ZEILE_MAX or sl.satzende(w["w"]) or lang:
            raus()
    raus()
    return zeilen


def uebersicht(plan: dict, mit_text: bool = True) -> str:
    """Der Plan zum Lesen — für das Gehirn und für Chef. Erst die Zahlen, dann die Stellen, die eine
    Entscheidung brauchen, dann der Wortlaut. ``mit_text=False`` lässt den Wortlaut ganz weg (vertraulich)."""
    zeilen = kurzfassung(plan)
    if not mit_text:
        offen = sum(1 for k in plan["kandidaten"] if not k["angewandt"] and not k.get("entschieden"))
        zeilen.append(f"VERTRAULICH — kein Wortlaut in dieser Übersicht. {offen} unsichere Stelle(n) bleiben unangetastet.")
        return "\n".join(zeilen) + "\n"
    zeilen += kandidaten_zeilen(plan)
    kurz = plan["statistik"].get("zu_kurz_zum_schneiden")
    if kurz:
        zeilen += ["", f"HINWEIS  {kurz} entfernte(s) Wort/Wörter sind unter 80 ms kurz und bleiben hörbar (im Untertitel fehlen sie)."]
    zeilen += ["", "TEXT   Nummer des ersten Wortes | Zeit im Rohvideo | Zeit im fertigen Video | Wörter   "
                   "([-…-] fliegt raus · ‖ Pause in s, wird gekürzt · *…* im Untertitel betont · „·“ leeres Wort)"]
    zeilen += textzeilen(plan)
    return "\n".join(zeilen) + "\n"


# ---------------------------------------------------------------------------------------------------
# EDL für Schnittprogramme

def _tc(bild: int, basis: int) -> str:
    return f"{bild // (3600 * basis):02d}:{bild // (60 * basis) % 60:02d}:{bild // basis % 60:02d}:{bild % basis:02d}"


def edl_cmx3600(plan: dict) -> str:
    """Die Schnittliste im Format CMX 3600 — das lesen DaVinci Resolve und Premiere.

    Zeitcodes zählen Bilder ohne Drop-Frame ab 00:00:00:00 (Quelle) und 01:00:00:00 (Ergebnis).
    """
    basis = max(1, round(float(Fraction(plan["bildrate"]))))
    name = Path(plan["quelle"]).name
    zeilen = [f"TITLE: {Path(plan['quelle']).stem} geschnitten", "FCM: NON-DROP FRAME", ""]
    pos = 3600 * basis
    for nr, s in enumerate(plan["segmente"], 1):
        laenge = s["m"] - s["k"]
        zeilen.append(f"{nr:03d}  AX       AA/V  C        {_tc(s['k'], basis)} {_tc(s['m'], basis)} "
                      f"{_tc(pos, basis)} {_tc(pos + laenge, basis)}")
        zeilen.append(f"* FROM CLIP NAME: {name}")
        pos += laenge
    return "\n".join(zeilen) + "\n"
