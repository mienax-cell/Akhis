"""Schnittlogik — aus Wörtern mit Zeiten wird ein Schnittplan.

Reine Rechnung ohne ffmpeg und ohne Whisper, damit sie sich ohne Medien prüfen lässt
(``tests\\test_schnittlogik.py``). Die Einheit ist das Wort: jedes Wort bleibt oder fliegt raus
(``weg`` nennt den Grund). Pausen sind keine eigenen Einträge, sie werden beim Bauen der Segmente
nach Regel gekürzt.

Ein Wort ist ein dict: ``i`` (Nummer = Platz in der Liste), ``w`` (Text mit Satzzeichen),
``von``/``bis`` (Sekunden im Rohvideo), ``p`` (Sicherheit der Erkennung), ``weg`` (None oder Grund).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from fractions import Fraction

# Gedehnte Füllaute, wie auch immer Whisper sie schreibt: äh, ääh, ähm, öhm, ehm, hm, hmm, mhm, uhm, äm —
# und, wenn Whisper nur den Laut hinschreibt, ein einzelnes „M“ oder „E“ (gesehen in langen Videos).
# „um“ und „eh“ fehlen mit Absicht — im Deutschen sind das echte Wörter. „eh“ wird nur vorgeschlagen.
_FUELL_MUSTER = re.compile(r"^(ä+h*m*|ä+h+e+m+|a+h+m+|ö+h*m*|e+h*m+|h+m+h*|m+h*m*|u+h+m+|e)$")

# Wörter, mit denen man sich selbst verbessert: „der wichtigste, also der wichtigste Punkt“.
BRUECKEN = frozenset("also nein ne nee quatsch sorry entschuldigung beziehungsweise bzw besser".split())

# Einzelne Wörter, die man absichtlich doppelt sagt („sehr, sehr gut“, „die, die …“, „und, und, und“).
# Stehen sie doppelt da, ist das nur ein Vorschlag, kein sicherer Schnitt.
DOPPELT_ERLAUBT = frozenset(
    "die der das sie und sehr ganz viel so ja nein doch immer lange bitte danke na ach oh hey hallo ok okay "
    "gut mehr wieder schnell komm los ha haha nie super nur ganz genau stopp hopp top".split())

GRUENDE = ("fuellwort", "wiederholung", "neuansatz", "doppelter_satz", "manuell")

MAX_WIEDERHOLUNG = 12      # so viele Wörter darf ein unmittelbar wiederholtes Stück lang sein
MAX_NEUANSATZ_WOERTER = 12  # so weit darf ein abgebrochener Anlauf vor dem Neuansatz zurückliegen
MAX_NEUANSATZ_ZEIT = 10.0
SATZ_PAUSE = 0.7           # ab dieser Lücke gilt ein Stück als eigener Satz, auch ohne Punkt
BRUCH_PAUSE = 0.3          # ab dieser Lücke vor dem Neuansatz gilt der Anlauf als abgebrochen
MIN_GEWINN = 0.08          # ein Schnitt, der weniger wegnimmt, lohnt den Sprung nicht


def norm(text: str) -> str:
    """Wort zum Vergleichen: klein, ohne Satzzeichen."""
    return re.sub(r"[^\w]+", "", text.lower()).replace("_", "")


def aehnlich(a: str, b: str) -> bool:
    """Zwei Wörter gelten als dasselbe, auch wenn die Erkennung eines leicht anders geschrieben hat
    („Punk“ / „Punkt“). Kurze Wörter müssen genau stimmen — „der“ ist nicht „den“."""
    if a == b:
        return bool(a)
    if min(len(a), len(b)) < 4:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.8


def satzende(text: str) -> bool:
    """Endet das Wort einen Satz? Auslassungspunkte zählen nicht — die stehen für Abbrechen."""
    t = text.rstrip("\"'»«“”„)] ")
    if t.endswith(("...", "…")):
        return False
    return t.endswith((".", "!", "?"))


def bricht_ab(text: str) -> bool:
    """Steht am Wort ein Zeichen fürs Abbrechen oder Weiterreden (Komma, Strich, Auslassung)?"""
    t = text.rstrip("\"'»«“”„)] ")
    return t.endswith((",", "-", "–", "—", "...", "…"))


def ist_fuellwort(text: str, liste: frozenset[str] | set[str]) -> bool:
    n = norm(text)
    return bool(n) and (n in liste or bool(_FUELL_MUSTER.match(n)))


def fuellwoerter_markieren(woerter: list[dict], opt: dict) -> int:
    """Füllwörter auf ``weg`` setzen. Liefert, wie viele es sind."""
    liste = {norm(x) for x in opt.get("fuellwoerter", [])}
    if opt.get("streng"):
        liste |= {norm(x) for x in opt.get("fuellwoerter_streng", [])}
    n = 0
    for w in woerter:
        if not w.get("weg") and ist_fuellwort(w["w"], liste):
            w["weg"] = "fuellwort"
            n += 1
    return n


def _text(woerter: list[dict], von: int, bis: int) -> str:
    return " ".join(w["w"] for w in woerter[von:bis + 1])


def kandidaten_finden(woerter: list[dict], opt: dict) -> list[dict]:
    """Versprecher suchen: unmittelbare Wiederholungen, doppelte Sätze, abgebrochene Anläufe.

    Liefert Kandidaten mit ``sicher`` (ja/nein). Markiert selbst nichts — das macht
    ``kandidaten_anwenden``. Füllwörter müssen vorher markiert sein: „wir haben ähm wir haben“
    ist erst ohne das „ähm“ eine Wiederholung.

    Die Leitlinie nach dem Gegenlesen: **Sicher ist nur, was nichts Eigenes verliert.** Deutsch lebt
    von Parallelsätzen („Ich war in Berlin, ich war in Hamburg“) — ein Komma oder eine kurze Pause ist
    kein Abbruch. Sicher geschnitten wird ein Anlauf nur, wenn er ganz in dem aufgeht, was danach
    kommt, oder wenn er hart abbricht (Füllwort, Strich, Auslassungspunkte). Alles andere ist ein
    Vorschlag, den das Gehirn oder Chef entscheidet.
    """
    aktiv = [w for w in woerter if not w.get("weg")]
    tok = [norm(w["w"]) for w in aktiv]
    n_aktiv = len(aktiv)
    belegt = [False] * n_aktiv
    funde: list[dict] = []

    def luecke_vor(j: int) -> float:
        return aktiv[j]["von"] - aktiv[j - 1]["bis"] if j > 0 else 0.0

    def fuellwort_vor(j: int) -> bool:
        return j > 0 and aktiv[j]["i"] - aktiv[j - 1]["i"] > 1

    def harter_bruch(j: int) -> bool:
        """Bricht der Anlauf vor Wort j hörbar ab — Füllwort dazwischen, Strich oder Auslassungspunkte?"""
        if j <= 0:
            return False
        ende = aktiv[j - 1]["w"].rstrip("\"'»«“”„)] ")
        return fuellwort_vor(j) or ende.endswith(("-", "–", "—", "...", "…"))

    def weicher_bruch(j: int) -> bool:
        return j > 0 and (luecke_vor(j) >= BRUCH_PAUSE or bricht_ab(aktiv[j - 1]["w"]))

    def merken(art: str, i: int, j: int, sicher: bool, grund: str) -> None:
        """Aktive Wörter i bis j-1 als Kandidat vormerken (j ist das erste, das bleibt)."""
        for k in range(i, j):
            belegt[k] = True
        von, bis = aktiv[i]["i"], aktiv[j - 1]["i"]
        funde.append({"art": art, "von": von, "bis": bis, "sicher": sicher, "angewandt": False,
                      "grund": grund, "text": _text(woerter, von, bis)})

    # (0) Ein einzelnes „eh“ zwischen Komma oder Pausen ist meist ein Füllaut, aber im Süden auch ein Wort
    #     („das ist eh klar“) — nur vorschlagen.
    for k, w in enumerate(aktiv):
        if tok[k] == "eh" and (bricht_ab(w["w"]) or luecke_vor(k) >= 0.2
                               or (k + 1 < n_aktiv and luecke_vor(k + 1) >= 0.2)):
            merken("fuellwort", k, k + 1, False, "klingt nach einem Füllaut („eh“) — bitte prüfen")

    if opt.get("wiederholungen", True):
        # (a0) Wortbruchstück: „Versich- Versicherung“ — das Stück vor dem Strich fliegt.
        for k in range(n_aktiv - 1):
            roh = aktiv[k]["w"].rstrip("\"'»«“”„)] ,")
            if (not belegt[k] and roh.endswith(("-", "–")) and len(tok[k]) >= 2 and tok[k + 1].startswith(tok[k])
                    and len(tok[k + 1]) > len(tok[k])):
                merken("wiederholung", k, k + 1, True, "Wort abgebrochen und neu angesetzt")

        # (a) Unmittelbare Wiederholung: dasselbe Stück zweimal direkt hintereinander → das erste fliegt.
        i = 0
        while i < n_aktiv:
            sprung = 1
            for n in range(min(MAX_WIEDERHOLUNG, (n_aktiv - i) // 2), 0, -1):
                if not all(tok[i:i + n]) or tok[i:i + n] != tok[i + n:i + 2 * n] or any(belegt[i:i + 2 * n]):
                    continue
                nur_erlaubte = all(t in DOPPELT_ERLAUBT or t.isdigit() for t in tok[i:i + n])
                if n == 1:
                    # „wirklich, wirklich“ mit Komma ist Betonung; „ich ich“ ohne ist Stottern.
                    sicher = not nur_erlaubte and not bricht_ab(aktiv[i]["w"]) and not satzende(aktiv[i]["w"])
                    grund = "Wort doppelt" if sicher else "Wort doppelt — kann Absicht sein"
                else:
                    sicher = not nur_erlaubte
                    grund = f"{n} Wörter direkt wiederholt" + ("" if sicher else " — kann Absicht sein")
                merken("wiederholung", i, i + n, sicher, grund)
                sprung = n
                break
            i += sprung

    # Sätze: an Punkt/Ausrufe-/Fragezeichen oder an einer deutlichen Pause getrennt.
    saetze: list[tuple[int, int]] = []
    anfang = 0
    for k in range(n_aktiv):
        letzter = k == n_aktiv - 1
        if letzter or satzende(aktiv[k]["w"]) or luecke_vor(k + 1) >= SATZ_PAUSE:
            saetze.append((anfang, k + 1))
            anfang = k + 1

    # (b) Zwei Sätze hintereinander fast gleich → der frühere fliegt (der letzte Anlauf ist der gewollte).
    #     Oder der frühere ist nur der abgebrochene Anfang des späteren — er geht ganz im späteren auf.
    if opt.get("doppelte_saetze", True) or opt.get("neuansaetze", True):
        for (a0, a1), (b0, b1) in zip(saetze, saetze[1:]):
            ta, tb = tok[a0:a1], tok[b0:b1]
            if len(ta) < 3 or len(tb) < 3 or any(belegt[a0:a1]) or not all(ta) or not all(tb):
                continue
            gleich = SequenceMatcher(None, ta, tb, autojunk=False).ratio()
            if opt.get("doppelte_saetze", True) and gleich >= 0.8:
                merken("doppelter_satz", a0, a1, gleich >= 0.9,
                       f"Satz zweimal gesagt ({gleich:.0%} gleich)" + ("" if gleich >= 0.9 else " — bitte prüfen"))
                continue
            if opt.get("neuansaetze", True) and len(tb) > len(ta):
                # Wort für Wort (verzeiht Schreibweisen) oder als Folge (verzeiht ein fehlendes Wort)
                vorn = max(sum(aehnlich(x, y) for x, y in zip(ta, tb)) / len(ta),
                           SequenceMatcher(None, ta, tb[:len(ta)], autojunk=False).ratio())
                if vorn >= 0.85:
                    fertig = satzende(aktiv[a1 - 1]["w"])
                    merken("neuansatz", a0, a1, not fertig,
                           "abgebrochener Anlauf, danach neu angesetzt" if not fertig
                           else "gleicher Satzanfang, aber vollständiger Satz — bitte prüfen")

    # (c) Neuansatz mitten im Satz: ein Stück Anfang kommt nach ein paar Wörtern noch einmal.
    if opt.get("neuansaetze", True):
        i = 0
        while i < n_aktiv:
            if belegt[i] or not tok[i]:
                i += 1
                continue
            gefunden = False
            for j in range(i + 2, min(i + MAX_NEUANSATZ_WOERTER, n_aktiv - 1) + 1):
                if aktiv[j]["von"] - aktiv[i]["von"] > MAX_NEUANSATZ_ZEIT:
                    break
                m = 0
                while i + m < j and j + m < n_aktiv and aehnlich(tok[i + m], tok[j + m]):
                    m += 1
                if m < 2 or i + m == j or any(belegt[i:j]):
                    # i + m == j wäre eine unmittelbare Wiederholung — die hat (a) schon bewertet
                    continue
                fertig = any(satzende(aktiv[k]["w"]) for k in range(i, j))
                # Was der Anlauf an Eigenem hat — Wörter, die danach nicht wiederkommen. Brückenwörter
                # („also“, „nein“) zählen nicht: Sie sind selbst das Zeichen fürs Verbessern.
                bruecke = any(tok[k] in BRUECKEN for k in range(i + m, j))
                eigene = sum(1 for k in range(i + m, j) if tok[k] not in BRUECKEN)
                if not fertig and eigene == 0 and (bruecke or weicher_bruch(j)):
                    merken("neuansatz", i, j, True, f"{m} Wörter gesagt, dann verbessert und neu angesetzt")
                elif not fertig and m >= 3 and eigene <= 2 and harter_bruch(j):
                    merken("neuansatz", i, j, True, f"abgebrochen, dann neu mit denselben {m} Wörtern")
                elif m >= 3 or (not fertig and weicher_bruch(j)):
                    merken("neuansatz", i, j, False,
                           f"gleicher Anfang ({m} Wörter)"
                           + (", aber vollständiger Satz" if fertig
                              else f", dazwischen {eigene} eigene Wörter — kann eine gewollte Reihung sein" if eigene
                              else ", ohne hörbaren Bruch") + " — bitte prüfen")
                else:
                    continue
                i = j
                gefunden = True
                break
            if not gefunden:
                i += 1

    funde.sort(key=lambda k: k["von"])
    for nr, k in enumerate(funde, 1):
        k["id"] = f"k{nr}"
    return funde


def kandidaten_anwenden(woerter: list[dict], kandidaten: list[dict], auch_unsichere: bool = False) -> None:
    """Sichere Kandidaten (auf Wunsch alle) in die Wörter eintragen."""
    for k in kandidaten:
        if k["sicher"] or auch_unsichere:
            kandidat_setzen(woerter, k, True)


def kandidat_setzen(woerter: list[dict], kandidat: dict, an: bool) -> None:
    """Einen Kandidaten annehmen oder wieder zurücknehmen."""
    for w in woerter[kandidat["von"]:kandidat["bis"] + 1]:
        if an and not w.get("weg"):
            w["weg"] = kandidat["art"]
        elif not an and w.get("weg") == kandidat["art"]:
            w["weg"] = None
    kandidat["angewandt"] = an


# ---------------------------------------------------------------------------------------------------
# Segmente

def _vereinen(stuecke: list[tuple[float, float]]) -> list[tuple[float, float]]:
    aus: list[tuple[float, float]] = []
    for von, bis in sorted(s for s in stuecke if s[1] > s[0]):
        if aus and von <= aus[-1][1]:
            aus[-1] = (aus[-1][0], max(aus[-1][1], bis))
        else:
            aus.append((von, bis))
    return aus


def _abziehen(stuecke: list[tuple[float, float]], weg: list[tuple[float, float]]) -> list[tuple[float, float]]:
    aus = list(stuecke)
    for w0, w1 in weg:
        neu = []
        for von, bis in aus:
            if w1 <= von or w0 >= bis:
                neu.append((von, bis))
                continue
            if w0 > von:
                neu.append((von, w0))
            if w1 < bis:
                neu.append((w1, bis))
        aus = neu
    return aus


def segmente_bauen(woerter: list[dict], dauer: float, fps: Fraction, opt: dict, huelle=None,
                   zeit_schnitte: list | tuple = (), zeit_halten: list | tuple = ()) -> list[dict]:
    """Aus den Wörtern, die bleiben, die Stücke bauen, die im Video bleiben.

    ``huelle`` (Lautstärke-Verlauf, siehe ``medien.Huelle``) ist freiwillig: mit ihr rutscht eine
    Schnittkante in die Stille oder in die Fuge zwischen zwei Wörtern; ohne sie sitzt sie am
    rechnerischen Wunschpunkt.

    Jedes Segment liegt auf dem Bildraster: ``k`` ist das erste Bild, ``m`` das erste nicht mehr
    gezeigte, ``von = k/fps``, ``bis = m/fps``. Bild und Ton werden mit denselben Grenzen geschnitten,
    deshalb kann über viele Schnitte nichts auseinanderlaufen.

    Drei Zusagen, jede aus einem Fund beim Gegenlesen:
    - Von einem Wort, das bleibt, fehlt nie mehr als die Hälfte — egal wohin die Kante rutschen möchte.
    - Ein entferntes Wort ist auch am Anfang und Ende des Videos nicht mehr zu hören.
    - Nach einem Zeitschnitt bleiben keine Splitter von ein paar Bildern stehen.
    """
    fps = Fraction(fps)
    bleibt = [w for w in woerter if not w.get("weg")]
    halbe = opt["pause_ziel"] / 2

    def kante(lo: float, hi: float, wunsch: float, fuge: bool, zurueck: float = 0.03, vor: float = 0.03) -> float:
        if hi < lo:
            lo = hi = (lo + hi) / 2
        wunsch = min(max(wunsch, lo), hi)
        return huelle.kante(lo, hi, wunsch, fuge, zurueck, vor) if huelle is not None else wunsch

    def laenge(w: dict) -> float:
        return max(0.0, w["bis"] - w["von"])

    roh: list[tuple[float, float]] = []
    if bleibt:
        erstes, letztes = bleibt[0], bleibt[-1]
        davor = [w for w in woerter[:erstes["i"]] if w.get("weg")]
        danach = [w for w in woerter[letztes["i"] + 1:] if w.get("weg")]
        if davor:   # ein entferntes Wort vor dem ersten: die Luft am Anfang darf nicht in es hineinreichen
            start = kante(min(davor[-1]["bis"], erstes["von"]), erstes["von"], erstes["von"] - opt["vorlauf"], True,
                          min(0.03, laenge(davor[-1])), min(0.08, laenge(erstes) / 2))
        else:
            start = max(0.0, erstes["von"] - opt["anfang_luft"])
        for a, b in zip(bleibt, bleibt[1:]):
            raus = [w for w in woerter[a["i"] + 1:b["i"]] if w.get("weg")]
            # Nach einem Satzende darf etwas mehr Luft bleiben als mitten im Satz.
            nach = max(opt["nachlauf"], halbe) if satzende(a["w"]) else opt["nachlauf"]
            vor = max(opt["vorlauf"], halbe) if satzende(a["w"]) else opt["vorlauf"]
            if raus:
                ende = kante(a["bis"], max(a["bis"], raus[0]["von"]), a["bis"] + nach, True,
                             min(0.03, laenge(a) / 2), min(0.08, laenge(raus[0])))
                anfang = kante(min(raus[-1]["bis"], b["von"]), b["von"], b["von"] - vor, True,
                               min(0.03, laenge(raus[-1])), min(0.08, laenge(b) / 2))
            elif b["von"] - a["bis"] >= opt["pause_ab"]:
                # Reine Pause: keine Fuge suchen. Ist dort keine Stille (Geräusch, Musik), wird an den
                # Wunschpunkten geschnitten — die Pause ist ja trotzdem zu lang.
                ende = kante(a["bis"], b["von"], a["bis"] + max(opt["nachlauf"], halbe), False)
                anfang = kante(a["bis"], b["von"], b["von"] - max(opt["vorlauf"], halbe), False)
            else:
                continue
            # Nie mehr als die Hälfte eines Wortes opfern, das bleibt.
            ende = max(ende, a["bis"] - laenge(a) / 2)
            anfang = min(anfang, b["von"] + laenge(b) / 2)
            if anfang - ende < MIN_GEWINN:
                continue
            roh.append((start, ende))
            start = anfang
        if danach:
            schluss = kante(letztes["bis"], max(letztes["bis"], danach[0]["von"]), letztes["bis"] + opt["nachlauf"], True,
                            min(0.03, laenge(letztes) / 2), min(0.08, laenge(danach[0])))
        else:
            schluss = min(dauer, letztes["bis"] + opt["ende_luft"])
        roh.append((start, max(schluss, start)))

    # Die spätere Anweisung gewinnt schon beim Ändern des Plans (plan.aendern räumt Überschneidungen aus);
    # hier gilt deshalb einfach: Schnitte abziehen, dann Halte-Bereiche dazulegen.
    stuecke = _abziehen(_vereinen(roh), [(float(v), float(b)) for v, b in zeit_schnitte])
    if zeit_schnitte:   # Splitter: Reste unter 0,3 s, in denen kein Wort mehr zur Hälfte liegt
        def traegt(von: float, bis: float) -> bool:
            return bis - von >= 0.3 or any(von <= (w["von"] + w["bis"]) / 2 < bis for w in bleibt)
        stuecke = [s for s in stuecke if traegt(*s)]
    stuecke = _vereinen(stuecke + [(max(0.0, float(v)), min(dauer, float(b))) for v, b in zeit_halten])

    # Aufs Bildraster legen. Nachbarn dürfen sich nicht überlappen; berühren sie sich, sind sie eins.
    bilder_gesamt = max(1, int(dauer * fps))
    segmente: list[dict] = []
    for von, bis in stuecke:
        k = max(0, round(von * fps))
        m = min(bilder_gesamt, round(bis * fps))
        if segmente:
            k = max(k, segmente[-1]["m"])
        if m - k < 2:
            m = min(bilder_gesamt, k + 2)
        if m - k < 1:
            continue
        if segmente and k == segmente[-1]["m"]:
            segmente[-1]["m"] = m
            segmente[-1]["bis"] = float(m / fps)
        else:
            segmente.append({"k": k, "m": m, "von": float(k / fps), "bis": float(m / fps)})
    return segmente


def statistik(woerter: list[dict], segmente: list[dict], dauer: float, kandidaten: list[dict] | None = None) -> dict:
    """Was fliegt raus und warum — in Sekunden, Wörtern und Stellen. Die Summe ist genau die gekürzte Zeit."""
    ergebnis = sum(s["bis"] - s["von"] for s in segmente)
    luecken: list[tuple[float, float, str]] = []
    pos = 0.0
    for nr, s in enumerate(segmente):
        if s["von"] > pos:
            luecken.append((pos, s["von"], "rand" if nr == 0 else "pause"))
        pos = s["bis"]
    if dauer > pos:
        luecken.append((pos, dauer, "rand"))

    sekunden = {g: 0.0 for g in GRUENDE + ("pause", "rand")}
    stueck = {g: 0 for g in GRUENDE + ("pause",)}
    for von, bis, art in luecken:
        rest = bis - von
        for w in woerter:
            g = w.get("weg")
            if not g or w["bis"] <= von or w["von"] >= bis:
                continue
            anteil = max(0.0, min(w["bis"], bis) - max(w["von"], von))
            sekunden[g] = sekunden.get(g, 0.0) + anteil
            rest -= anteil
        sekunden[art] += max(0.0, rest)
        if art == "pause" and not any(w.get("weg") and von <= (w["von"] + w["bis"]) / 2 < bis for w in woerter):
            stueck["pause"] += 1
    hoerbar = 0    # entfernt markiert, aber zu kurz zum Herausschneiden (unter 80 ms zwischen zwei Wörtern)
    for w in woerter:
        if w.get("weg") in stueck:
            mitte = (w["von"] + w["bis"]) / 2
            if any(s["von"] <= mitte < s["bis"] for s in segmente):
                hoerbar += 1
            else:
                stueck[w["weg"]] += 1
    # Stellen: ein abgebrochener Anlauf aus sechs Wörtern ist eine Stelle, nicht sechs.
    stellen = {g: 0 for g in GRUENDE}
    for k in kandidaten or []:
        if k.get("angewandt") and k["art"] in stellen and k["art"] != "fuellwort":
            stellen[k["art"]] += 1
    stellen["fuellwort"] = stueck["fuellwort"]
    lauf = False
    for w in woerter:                      # von Hand: zusammenhängende Wörter zählen als eine Stelle
        hand = w.get("weg") == "manuell"
        stellen["manuell"] += hand and not lauf
        lauf = hand

    def im_ergebnis(w: dict) -> bool:
        mitte = (w["von"] + w["bis"]) / 2
        return any(s["von"] <= mitte < s["bis"] for s in segmente)
    return {
        "dauer_roh": round(dauer, 3),
        "dauer_ergebnis": round(ergebnis, 3),
        "gekuerzt": round(dauer - ergebnis, 3),
        "segmente": len(segmente),
        "woerter": len(woerter),
        "woerter_bleiben": sum(1 for w in woerter if not w.get("weg") and im_ergebnis(w)),
        "sekunden": {k: round(v, 3) for k, v in sekunden.items()},
        "stueck": stueck,
        "stellen": stellen,
        "zu_kurz_zum_schneiden": hoerbar,
    }


class Zeitachse:
    """Rechnet Zeiten des Rohvideos in Zeiten des geschnittenen Videos um."""

    def __init__(self, segmente: list[dict]):
        self.segmente = segmente
        self.versatz: list[float] = []
        pos = 0.0
        for s in segmente:
            self.versatz.append(pos)
            pos += s["bis"] - s["von"]
        self.dauer = pos

    def segment_von(self, t: float) -> int | None:
        for nr, s in enumerate(self.segmente):
            if s["von"] <= t < s["bis"]:
                return nr
        return None

    def zurueck(self, zeit: float) -> float | None:
        """Zeit im geschnittenen Video → Zeit im Rohvideo."""
        for nr, s in enumerate(self.segmente):
            if self.versatz[nr] <= zeit < self.versatz[nr] + s["bis"] - s["von"]:
                return s["von"] + zeit - self.versatz[nr]
        return None

    def wort(self, von: float, bis: float) -> tuple[float, float] | None:
        """Ein Wort (Rohzeit) auf die neue Zeitachse legen. None, wenn es nicht im Ergebnis liegt."""
        nr = self.segment_von((von + bis) / 2)
        if nr is None:
            # Die Mitte liegt knapp daneben — das Segment nehmen, das das Wort am meisten überdeckt.
            beste, nr = 0.0, None
            for kandidat, s in enumerate(self.segmente):
                ueber = min(bis, s["bis"]) - max(von, s["von"])
                if ueber > beste:
                    beste, nr = ueber, kandidat
            if nr is None:
                return None
        s = self.segmente[nr]
        a = self.versatz[nr] + min(max(von, s["von"]), s["bis"]) - s["von"]
        b = self.versatz[nr] + min(max(bis, s["von"]), s["bis"]) - s["von"]
        return (a, max(b, a))
