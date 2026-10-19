"""Untertitel — wenige Wörter groß im Bild, das gerade gesprochene Wort hervorgehoben.

Technik: Die Wörter werden zu kleinen Gruppen gebündelt. Für eine Gruppe mit n Wörtern stehen n Zeilen
in der ASS-Datei; jede zeigt die ganze Gruppe und hebt genau ein Wort hervor. Die Zeilen schließen
lückenlos aneinander an, deshalb flackert nichts.

Zwei Arten (``untertitel.art``): ``farbe`` zeigt die ganze Gruppe und färbt das gesprochene Wort;
``aufbau`` lässt die Gruppe Wort für Wort entstehen — was noch nicht gesprochen ist, bleibt unsichtbar
(oder blass, ``kommend``), behält aber seinen Platz, damit nichts rutscht.

Dazu kommt, was Zuschauer hält (alles abschaltbar, Abschnitt ``bindung`` im Stil):
- **Betonte Wörter** (Zahlen, Geld, was das Gehirn markiert) tragen eine eigene Farbe — das Auge bleibt hängen.
- **Schlagzeilen** oben im Bild: eine kleine und eine große Zeile mit einem Akzentwort, für den Einstieg
  und die Kernaussagen.
- **Fortschrittsbalken** am oberen Rand: Wer sieht, dass es gleich geschafft ist, bleibt eher dran.

Alle Zeiten werden in Bildnummern des fertigen Videos gerechnet und erst zum Schluss in ASS-Zeit
(Hundertstel) umgeschrieben — so wechselt die Hervorhebung genau auf einem Bild und nie dazwischen.
Gemessen: libass zeigt eine Zeile genau dann, wenn Start ≤ Bildzeit < Ende.

Was die Messung an Fallen gezeigt hat und hier berücksichtigt ist:
- ``\\r`` setzt auch die Schriftgröße zurück → Farbe und Größe werden ausdrücklich zurückgestellt.
- Ein vergrößertes Wort schiebt in einer mittig gesetzten Zeile seine Nachbarn (bis 30 Pixel) →
  mit Vergrößerung gibt es zwei Ebenen: die Zeile ohne das aktive Wort, darüber nur das aktive Wort.
- libass ersetzt eine unbekannte Schrift still durch Arial → ``schrift_aus_protokoll`` liest das
  ffmpeg-Protokoll und meldet es.
"""
from __future__ import annotations

import math
import re
import unicodedata
from fractions import Fraction

from . import schnittlogik as sl
from . import schrift

ZEILEN_PAUSE = 0.45    # ab dieser Lücke beginnt eine neue Gruppe
NACHHALL = 0.6         # so lange bleibt eine Gruppe nach ihrem letzten Wort höchstens stehen
POP_MS, POP_VON = 80, 85        # Einblenden: von 85 % auf 100 % in 80 ms
AKTIV_MS = 70                   # so schnell wächst das aktive Wort
KLEINSTE_SCHRIFT = 0.6          # Rand und Schatten schrumpfen höchstens auf diesen Anteil mit
HELL_AB = 150                   # ab dieser Helligkeit (0 bis 255) hinter dem Text wird die Schrift dunkel
_SATZZEICHEN = ".,;:…\"„“”«»()[]–—"
_STEUERZEICHEN = re.compile(r"[\u0000-\u001f\u007f\u0085​-‏  ⁠﻿]")


def woerter_im_ergebnis(woerter: list[dict], segmente: list[dict]) -> list[dict]:
    """Die Wörter, die bleiben, mit ihren Zeiten im geschnittenen Video.

    Beginnt nach einem Schnitt ein Satz mit einem Wort, das vorher mitten im Satz stand („Äh, fangen
    wir an“ → „fangen wir an“), wird es großgeschrieben — sonst stünde der Satzanfang klein im Bild.
    """
    achse = sl.Zeitachse(segmente)
    aus: list[dict] = []
    satz_neu = True
    for w in woerter:
        if w.get("weg"):
            continue
        ort = achse.wort(w["von"], w["bis"])
        if ort is None:
            continue
        text = w["w"]
        if satz_neu and text:
            stelle = next((k for k, z in enumerate(text) if z.isalpha()), None)
            if stelle is not None and text[stelle].islower():
                text = text[:stelle] + text[stelle].upper() + text[stelle + 1:]
        if text:
            satz_neu = sl.satzende(text)
        von = max(ort[0], aus[-1]["von"]) if aus else ort[0]
        aus.append({"i": w["i"], "w": text, "von": von, "bis": max(ort[1], von), "quelle": w["von"],
                    "betont": bool(w.get("betont"))})
    return aus


def anzeigetext(text: str, opt: dict) -> str:
    """Ein Wort, wie es im Bild steht. Alles, was eine ASS-Zeile sprengen könnte, fliegt raus:
    geschweifte Klammern und Rückstriche wären Befehle, ein Zeilenumbruch schnitte den Rest ab."""
    t = _STEUERZEICHEN.sub(" ", unicodedata.normalize("NFC", text))
    t = t.replace("{", "").replace("}", "").replace("\\", "").strip()
    if not opt.get("satzzeichen"):
        t = t.strip(_SATZZEICHEN + "-").strip()
    if opt.get("grossbuchstaben"):
        t = t.upper()   # ß wird „SS“ — das große ẞ fehlt in fast allen fetten Schriften
    return re.sub(r"\s+", " ", t)


def gruppen_bilden(woerter: list[dict], opt: dict, fps: Fraction, bilder_gesamt: int) -> list[dict]:
    """Wörter zu Gruppen bündeln und jedem Wort das Bild geben, auf dem es aufleuchtet."""
    gruppen: list[list[dict]] = []
    aktuell: list[dict] = []
    for w in woerter:
        text = anzeigetext(w["w"], opt)
        if not text:
            continue
        eintrag = {"text": text, "von": w["von"], "bis": w["bis"], "satzende": sl.satzende(w["w"]),
                   "quelle": w.get("quelle", w["von"]), "betont": bool(w.get("betont"))}
        if aktuell:
            zu_lang = len(" ".join(x["text"] for x in aktuell) + " " + text) > opt["zeichen_max"]
            if (len(aktuell) >= opt["woerter_max"] or zu_lang or aktuell[-1]["satzende"]
                    or w["von"] - aktuell[-1]["bis"] > ZEILEN_PAUSE):
                gruppen.append(aktuell)
                aktuell = []
        aktuell.append(eintrag)
    if aktuell:
        gruppen.append(aktuell)

    aus: list[dict] = []
    letztes = -1
    for g in gruppen:
        g = [w for w in g if max(letztes + 1, round(w["von"] * fps)) < bilder_gesamt] or g[:1]
        for w in g:
            w["bild"] = max(letztes + 1, round(w["von"] * fps))
            letztes = w["bild"]
        aus.append({"woerter": g, "ende": min(bilder_gesamt, max(letztes + 1, round((g[-1]["bis"] + NACHHALL) * fps)))})
    for g, danach in zip(aus, aus[1:]):
        g["ende"] = min(g["ende"], danach["woerter"][0]["bild"])
    return [g for g in aus if g["woerter"][0]["bild"] < bilder_gesamt and g["ende"] > g["woerter"][0]["bild"]]


def _farbe(hexfarbe: str) -> str:
    """#RRGGBB → Farbe für einen ASS-Befehl im Text (&HBBGGRR&)."""
    return f"&H{hexfarbe[5:7]}{hexfarbe[3:5]}{hexfarbe[1:3]}&".upper()


def _stilfarbe(hexfarbe: str, durchsicht: int = 0) -> str:
    """#RRGGBB → Farbe für die Style-Zeile (&HAABBGGRR, AA = Durchsichtigkeit)."""
    return f"&H{durchsicht:02X}{hexfarbe[5:7]}{hexfarbe[3:5]}{hexfarbe[1:3]}".upper()


def _akzent(opt: dict, grund_farbe: tuple[float, float, float] | None) -> str:
    """Die Akzentfarbe, die sich vom Hintergrund am meisten abhebt (Orange auf rotem Hemd liest sich nicht).
    Zur Wahl stehen ``farbe_betont`` und ``farbe_betont_2``; ohne Messung gilt die erste."""
    wahl = [f for f in (opt.get("farbe_betont") or opt["farbe_aktiv"], opt.get("farbe_betont_2")) if f]
    if grund_farbe is None or len(wahl) < 2:
        return wahl[0]

    def abstand(hexfarbe: str) -> float:
        return sum((int(hexfarbe[k:k + 2], 16) - g) ** 2 for k, g in zip((1, 3, 5), grund_farbe))
    return max(wahl, key=abstand)


def _zeit(bild: int, fps: Fraction) -> str:
    """Bildnummer → ASS-Zeit, abgerundet auf Hundertstel: Das liegt sicher nach dem Bild davor und
    spätestens auf diesem Bild. Ende einer Zeile und Start der nächsten sind derselbe Wert."""
    cs = math.floor(Fraction(bild * 100) / fps)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _groesse(prozent: float, pop: bool, ms: int = POP_MS) -> str:
    """Größen-Befehl: fest, oder beim Einblenden von klein auf Zielgröße wachsend."""
    ziel = round(prozent)
    if not pop:
        return f"\\fscx{ziel}\\fscy{ziel}"
    start = round(prozent * POP_VON / 100)
    return f"\\fscx{start}\\fscy{start}\\t(0,{ms},\\fscx{ziel}\\fscy{ziel})"


def _zeilen_einer_gruppe(texte: list[str], farben: list[str], nr: int, lage: str, aktiv: str, faktor: float, pop: bool,
                         kommend: str | None = None) -> list[tuple[int, str]]:
    """Die ASS-Texte für „Wort nr ist dran“. Liefert (Ebene, Text) — eine Zeile, mit Vergrößerung zwei.

    ``farben`` ist die Ruhefarbe jedes Wortes (betonte Wörter haben eine eigene). ``kommend`` ist die
    Durchsichtigkeit (ASS, „FF“ = unsichtbar) der Wörter, die noch nicht gesprochen sind; None zeigt sie voll.
    """
    def zeile(sichtbar, aktive_farbe: str, aktiv_befehle: str, nach_aktiv: str) -> str:
        """Wort für Wort setzen; ein Befehl steht nur dort, wo sich Farbe oder Durchsicht ändert."""
        teile, farbe, durch = [], None, "00"
        for k, t in enumerate(texte):
            soll_farbe = aktive_farbe if k == nr else farben[k]
            soll_durch = sichtbar(k)
            befehl = (f"\\1c{soll_farbe}" if soll_farbe != farbe else "") + (f"\\alpha&H{soll_durch}&" if soll_durch != durch else "")
            if k == nr:
                befehl += aktiv_befehle
            elif k == nr + 1:
                befehl += nach_aktiv
            teile.append((f"{{{befehl}}}" if befehl else "") + t)
            farbe, durch = soll_farbe, soll_durch
        return " ".join(teile)

    spaeter = kommend or "00"
    if faktor <= 1:
        kopf = lage + (_groesse(100, True) if pop else "")
        return [(0, f"{{{kopf}}}" + zeile(lambda k: spaeter if k > nr else "00", aktiv, "", ""))]
    # Zwei Ebenen: Beide setzen dieselbe Zeile, zeigen aber verschiedene Teile. Die Nachbarn stehen in
    # Ebene 0 und rühren sich nicht; das aktive Wort wächst in Ebene 1 um seine eigene Mitte.
    ruhe = _groesse(100, pop)
    wachsen = (_groesse(faktor * 100, True) if pop
               else f"\\t(0,{AKTIV_MS},\\fscx{round(faktor * 100)}\\fscy{round(faktor * 100)})")
    unten = f"{{{lage}{ruhe if pop else ''}}}" + zeile(lambda k: "FF" if k == nr else spaeter if k > nr else "00", aktiv, "", "")
    oben = f"{{{lage}{ruhe if pop else ''}}}" + zeile(lambda k: "00" if k == nr else "FF", aktiv, wachsen, ruhe)
    return [(0, unten), (1, oben)]


def _schlagzeilen(zeilen: list[str], schlagzeilen: list[dict], nach_nummer: dict, opt: dict, breite: int, hoehe: int,
                  fps: Fraction, bilder_gesamt: int, ist_hell, grund_oben=lambda bild: None,
                  starts: list[int] | None = None) -> int:
    """Große Zeilen oben im Bild: klein darüber, groß darunter, ein Wort in der Akzentfarbe."""
    kante = min(breite, hoehe)
    gross_fs, klein_fs = round(0.105 * kante), round(0.047 * kante)
    fett = bool(opt.get("fett"))
    gesetzt = 0
    for s in schlagzeilen:
        treffer = [nach_nummer[i] for i in range(s["von"], s["bis"] + 1) if i in nach_nummer]
        if not treffer:
            continue   # alle Wörter dieser Schlagzeile sind geschnitten
        start = max(0, treffer[0][0] - 2)
        ende = min(bilder_gesamt, treffer[-1][1] + round(0.35 * fps))
        if ende <= start:
            continue
        hell = ist_hell(start)
        text_farbe = _farbe(opt["farbe_dunkel"] if hell else opt["farbe"])
        rand = f"\\3c{_farbe(opt['farbe'] if hell else opt['umriss_farbe'])}"
        gross = anzeigetext(s["gross"], {"satzzeichen": True})
        akzent = anzeigetext(s.get("akzent") or "", {"satzzeichen": True})
        weite, _ = schrift.breite(gross, gross_fs, opt["schrift"], fett, opt.get("schrift_datei"))
        fs = gross_fs if weite <= 0.9 * breite else max(12, int(gross_fs * 0.9 * breite / weite))
        if akzent and akzent in gross:
            davor, danach = gross.split(akzent, 1)
            gross = f"{davor}{{\\1c{_farbe(_akzent(opt, grund_oben(start)))}}}{akzent}{{\\1c{text_farbe}}}{danach}"
        pop = _groesse(100, True, 110)
        blende = "\\fad(0,120)"
        x = breite // 2
        if s.get("klein"):
            klein = anzeigetext(s["klein"], {"satzzeichen": True})
            zeilen.append(f"Dialogue: 2,{_zeit(start, fps)},{_zeit(ende, fps)},Wort,,0,0,0,,"
                          f"{{\\an5\\pos({x},{round(0.115 * hoehe)})\\fs{klein_fs}\\bord{round(klein_fs * 0.05, 1)}\\blur1\\1c{text_farbe}{rand}{blende}}}{klein}")
        zeilen.append(f"Dialogue: 2,{_zeit(start, fps)},{_zeit(ende, fps)},Wort,,0,0,0,,"
                      f"{{\\an5\\pos({x},{round(0.175 * hoehe)})\\fs{fs}\\bord{round(fs * 0.035, 1)}\\blur2\\1c{text_farbe}{rand}{pop}{blende}}}{gross}")
        gesetzt += 1
        if starts is not None:
            starts.append(start)
    return gesetzt


def ass_bauen(woerter: list[dict], segmente: list[dict], opt: dict, breite: int, hoehe: int, fps: Fraction,
              helligkeit=None, helligkeit_oben=None, schlagzeilen: list[dict] | None = None,
              bindung: dict | None = None) -> tuple[str, dict]:
    """Die ASS-Datei als Text. Zweiter Wert: Zahlen fürs Protokoll (Gruppen, Zeilen, kleinste Schrift).

    ``helligkeit(sekunde_im_rohvideo)`` sagt, wie hell das Bild hinter dem Text ist (0 bis 255). Damit
    wechselt die Schrift auf hellem Grund von selbst auf die dunkle Farbe (``kontrast: auto``).
    ``helligkeit_oben`` ist dasselbe für das Band der Schlagzeilen.
    """
    fps = Fraction(fps)
    bindung = bindung or {}
    bilder_gesamt = sum(s["m"] - s["k"] for s in segmente)
    im_ergebnis = woerter_im_ergebnis(woerter, segmente)
    gruppen = gruppen_bilden(im_ergebnis, opt, fps, bilder_gesamt) if opt.get("an", True) else []

    groesse = max(8, round(opt["groesse"] * min(breite, hoehe)))
    umriss = round(opt["umriss"] * groesse, 1)
    schatten = round(opt["schatten"] * groesse, 1)
    weichheit = round(float(opt.get("umriss_weich") or 0) * groesse, 1)
    x = breite // 2
    y = round((opt.get("position_quer") if breite > hoehe and opt.get("position_quer") else opt["position"]) * hoehe)
    aufbau = opt.get("art") == "aufbau"
    kommend = f"{round((1 - float(opt.get('kommend') or 0)) * 255):02X}" if aufbau else None
    faktor = float(opt.get("aktiv_groesse") or 1.0)
    fett = bool(opt.get("fett"))
    pop = bool(opt.get("einblenden"))
    grenze = opt["breite_max"] * breite
    auto = opt.get("kontrast") == "auto"
    achse = sl.Zeitachse(segmente)

    def hell_im_ergebnis(bild: int, messung) -> bool | None:
        """Ist der Grund bei diesem Bild des fertigen Videos hell?"""
        if not auto or messung is None:
            return None
        quelle = achse.zurueck(float(Fraction(bild) / fps))
        wert = messung(quelle) if quelle is not None else None
        return None if wert is None else wert > HELL_AB

    def weite(text: str) -> tuple[float, bool]:
        return schrift.breite(text, groesse, opt["schrift"], fett, opt.get("schrift_datei"))

    kopf = "\n".join([
        "[Script Info]",
        "; MAGI Videoschnitt",
        "ScriptType: v4.00+",
        f"PlayResX: {breite}",
        f"PlayResY: {hoehe}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: None",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding",
        f"Style: Wort,{opt['schrift']},{groesse},{_stilfarbe(opt['farbe'])},&H000000FF,{_stilfarbe(opt['umriss_farbe'])},"
        f"{_stilfarbe('#000000', 0x80)},{-1 if fett else 0},0,0,0,100,100,0,0,1,{umriss},{schatten},5,0,0,0,1",
        "Style: Balken,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])

    zeilen: list[str] = []
    kleinste, gemessen, dunkle = groesse, True, 0
    for g in gruppen:
        texte = [w["text"] for w in g["woerter"]]
        tinte, echt = weite(" ".join(texte))
        if faktor > 1:
            tinte += max(weite(t)[0] for t in texte) * (faktor - 1)
        gemessen = gemessen and echt
        aussen = 2 * umriss + schatten
        lage = f"\\an5\\pos({x},{y})" + (f"\\blur{weichheit}" if weichheit else "")
        grund, aktiv = _farbe(opt["farbe"]), _farbe(opt["farbe_aktiv"])
        dunkel_setzen = False
        if auto and helligkeit is not None:
            werte = [v for v in (helligkeit(w["quelle"]) for w in g["woerter"]) if v is not None]
            dunkel_setzen = bool(werte) and sum(werte) / len(werte) > HELL_AB
            # Kippt der Grund, während die Gruppe noch nachsteht (Szenenwechsel), endet sie dort —
            # sonst stünde dunkle Schrift auf dunklem Grund oder helle auf hellem.
            for bild in range(g["woerter"][-1]["bild"] + 1, g["ende"]):
                jetzt = hell_im_ergebnis(bild, helligkeit)
                if jetzt is not None and jetzt != dunkel_setzen:
                    g["ende"] = bild
                    break
        if dunkel_setzen:
            # Heller Grund: dunkle Schrift, heller Hof. Ist das aktive Wort so hell wie die Schrift
            # sonst, wechselt es mit — sonst bliebe es weiß auf Weiß.
            grund = _farbe(opt["farbe_dunkel"])
            if opt["farbe_aktiv"].upper() == opt["farbe"].upper():
                aktiv = grund
            lage += f"\\3c{_farbe(opt['farbe'])}"
            dunkle += 1
        hinter = None
        if auto and helligkeit is not None and hasattr(helligkeit, "farbe") and any(w["betont"] for w in g["woerter"]):
            proben = [helligkeit.farbe(w["quelle"]) for w in g["woerter"]]
            hinter = tuple(sum(p[k] for p in proben) / len(proben) for k in range(3))
        betont = _farbe(_akzent(opt, hinter))
        farben = [betont if w["betont"] else grund for w in g["woerter"]]
        if tinte + aussen > grenze:
            # Zu breit: Schrift so weit verkleinern, dass die Zeile samt Rand hineinpasst.
            k = grenze / (tinte + aussen)
            if k < KLEINSTE_SCHRIFT:
                k = (grenze - KLEINSTE_SCHRIFT * aussen) / tinte
            passt = max(8, int(groesse * k))
            k = passt / groesse
            lage += (f"\\fs{passt}\\bord{round(max(umriss * KLEINSTE_SCHRIFT, umriss * k), 1)}"
                     f"\\shad{round(max(schatten * KLEINSTE_SCHRIFT, schatten * k), 1)}")
            kleinste = min(kleinste, passt)

        for nr, w in enumerate(g["woerter"]):
            start = w["bild"]
            ende = g["woerter"][nr + 1]["bild"] if nr + 1 < len(g["woerter"]) else g["ende"]
            if ende <= start:
                continue
            # Ein betontes Wort behält seine Farbe auch, während es gesprochen wird.
            aktiv_hier = farben[nr] if w["betont"] else aktiv
            for ebene, text in _zeilen_einer_gruppe(texte, farben, nr, lage, aktiv_hier, faktor, pop and nr == 0, kommend):
                zeilen.append(f"Dialogue: {ebene},{_zeit(start, fps)},{_zeit(ende, fps)},Wort,,0,0,0,,{text}")

    # Schlagzeilen: an Wortnummern gebunden, damit sie nach jedem Umschneiden noch stimmen
    nach_nummer = {}
    for w in im_ergebnis:
        a = round(w["von"] * fps)
        nach_nummer[w["i"]] = (a, max(a + 1, round(w["bis"] * fps)))
    def grund_oben(bild: int):
        quelle = achse.zurueck(float(Fraction(bild) / fps))
        return helligkeit_oben.farbe(quelle) if auto and quelle is not None and hasattr(helligkeit_oben, "farbe") else None

    titel_starts: list[int] = []
    titel = _schlagzeilen(zeilen, schlagzeilen or [], nach_nummer, opt, breite, hoehe, fps, bilder_gesamt,
                          lambda bild: bool(hell_im_ergebnis(bild, helligkeit_oben)), grund_oben, starts=titel_starts)

    balken = bool(bindung.get("fortschritt")) and bilder_gesamt > 1
    if balken:
        # Ein Rechteck über die ganze Breite, das in der Breite von 0 auf 100 % wächst — einmal gesetzt
        # für das ganze Video. Es sitzt am oberen Rand; unten liegen bei TikTok und Instagram die Knöpfe.
        hoch = max(4, round(float(bindung.get("fortschritt_hoehe", 0.006)) * hoehe))
        ms = round(float(Fraction(bilder_gesamt) / fps) * 1000)
        zeilen.append(f"Dialogue: 3,{_zeit(0, fps)},{_zeit(bilder_gesamt, fps)},Balken,,0,0,0,,"
                      f"{{\\an7\\pos(0,0)\\1c{_farbe(bindung.get('fortschritt_farbe') or opt['farbe_aktiv'])}\\1a&H18&"
                      f"\\fscx0\\t(0,{ms},\\fscx100)\\p1}}m 0 0 l {breite} 0 l {breite} {hoch} l 0 {hoch}{{\\p0}}")

    info = {"gruppen": len(gruppen), "zeilen": len(zeilen), "schrift": opt["schrift"], "groesse": groesse,
            "kleinste_groesse": kleinste, "breite_gemessen": gemessen, "position": [x, y], "art": opt.get("art", "farbe"),
            "gruppen_dunkle_schrift": dunkle, "betonte_woerter": sum(w["betont"] for g in gruppen for w in g["woerter"]),
            "schlagzeilen": titel, "schlagzeilen_bilder": titel_starts, "fortschrittsbalken": balken,
            "breiteste": max(gruppen, key=lambda g: len(" ".join(w["text"] for w in g["woerter"])))["woerter"][0]["bild"] if gruppen else None,
            "erste": gruppen[0]["woerter"][0]["bild"] if gruppen else None,
            "letzte": gruppen[-1]["woerter"][-1]["bild"] if gruppen else None}
    return kopf + "\n" + "\n".join(zeilen) + "\n", info


def srt_bauen(woerter: list[dict], segmente: list[dict], opt: dict, fps: Fraction) -> str:
    """Dieselben Gruppen als schlichte SRT-Datei — zum Hochladen als Untertitelspur."""
    fps = Fraction(fps)
    bilder_gesamt = sum(s["m"] - s["k"] for s in segmente)
    gruppen = gruppen_bilden(woerter_im_ergebnis(woerter, segmente), {**opt, "grossbuchstaben": False, "satzzeichen": True},
                             fps, bilder_gesamt)

    def zeit(bild: int) -> str:
        ms = round(Fraction(bild * 1000) / fps)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    bloecke = []
    for nr, g in enumerate(gruppen, 1):
        bloecke.append(f"{nr}\n{zeit(g['woerter'][0]['bild'])} --> {zeit(g['ende'])}\n" + " ".join(w["text"] for w in g["woerter"]))
    return "\n\n".join(bloecke) + "\n"


_SCHRIFTWAHL = re.compile(r"fontselect: \((.+?), (\d+), (\d)\) -> (.+?), (\d+), (.+)$")
_ZEICHEN_FEHLT = re.compile(r"Glyph (0x[0-9A-Fa-f]+) not found")


def schrift_aus_protokoll(protokoll: str, gewollt: str) -> dict:
    """Aus dem ffmpeg-Protokoll lesen, welche Schrift libass wirklich genommen hat.

    libass meldet keinen Fehler, wenn es die Schrift nicht findet — es nimmt Arial, und ffmpeg endet
    mit Erfolg. Nur die Zeile ``fontselect: (Name, …) -> Datei`` verrät es.
    """
    def kern(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    genommen, ersetzt, fehlend = [], [], []
    for zeile in protokoll.splitlines():
        m = _SCHRIFTWAHL.search(zeile)
        if m and kern(m.group(1)) == kern(gewollt) and m.group(4) not in genommen:
            genommen.append(m.group(4))
            # „Arial Black“ wird zu „Arial-Black“, „Segoe UI“ fett zu „SegoeUI-Bold“ — der Kern des Namens muss vorn stehen.
            if not kern(m.group(4)).startswith(kern(gewollt)):
                ersetzt.append(m.group(4))
        g = _ZEICHEN_FEHLT.search(zeile)
        if g and g.group(1) not in fehlend:
            fehlend.append(g.group(1))
    return {"genommen": genommen, "ersetzt": ersetzt, "zeichen_fehlen": fehlend}
