"""Transkription — aus dem Ton werden Wörter mit Zeiten (faster-whisper, auf dem Rechner).

Zwei Sperren stehen im Code, nicht in einer Anweisung:
- Es wird nie ein Modell geladen, das nicht schon auf dem Rechner liegt (``local_files_only``).
  Herunterladen geht nur über den eigenen Befehl ``modell-holen``.
- Kein Ton verlässt den Rechner.

Der Ton wird an Sprechpausen in Stücke unter 30 Sekunden geteilt und Stück für Stück erkannt. Der Grund
ist gemessen: Whisper arbeitet in 30-Sekunden-Fenstern, und der Hinweis „schreib auch die Ähms hin“ gilt
nur für das erste. In einem 12-Minuten-Video wurden so 5 von 60 Füllwörtern erkannt — der Rest stand als
„M,“ und „E,“ im Text. Mit eigenen Stücken bekommt jedes seinen Hinweis.
"""
from __future__ import annotations

import re
import time
import wave
from pathlib import Path

import numpy as np

from . import ModulFehler, umgebung
from .medien import Huelle
from .schnittlogik import ist_fuellwort, satzende

STUECK_ZIEL = 20.0   # so lang soll ein Stück etwa sein
STUECK_MAX = 28.0    # und nie länger als das (Whisper sieht 30 Sekunden auf einmal)
STUECK_MIN = 6.0


class TranskriptFehler(ModulFehler):
    pass


def modell_waehlen(wunsch: str) -> str:
    """„auto“ = das beste Modell, das schon da ist. Ein Name = genau dieses, sonst Fehler mit dem Weg."""
    if wunsch == "auto":
        da = umgebung.modelle_vorhanden()
        if not da:
            raise TranskriptFehler("Auf dem Rechner liegt kein Whisper-Modell. Mit Chefs Ja laden:  "
                                   "schnitt.py modell-holen small --ja   (ca. 480 MB)")
        return da[0]
    if not umgebung.modell_ort(wunsch):
        mb = umgebung.MODELL_GROESSE_MB.get(wunsch)
        if mb is None:
            raise TranskriptFehler(f"Das Modell „{wunsch}“ kennt das Modul nicht. Möglich: {', '.join(umgebung.MODELL_VORLIEBE)}")
        raise TranskriptFehler(f"Das Modell „{wunsch}“ liegt nicht auf dem Rechner. Mit Chefs Ja laden:  "
                               f"schnitt.py modell-holen {wunsch} --ja   (ca. {mb} MB)")
    return wunsch


def _laden(name: str, geraet: str):
    """Modell laden — erst auf der Grafikkarte, bei jedem Fehler dort auf dem Prozessor."""
    from faster_whisper import WhisperModel

    ort = umgebung.modell_ort(name)
    versuche = []
    if geraet in ("auto", "cuda") and umgebung.cuda_karten() > 0:
        versuche.append(("cuda", "float16"))
    if geraet != "cuda" or not versuche:
        versuche.append(("cpu", "int8"))
    fehler = None
    for wo, rechenart in versuche:
        try:
            return WhisperModel(ort, device=wo, compute_type=rechenart, local_files_only=True), wo, rechenart
        except Exception as e:  # die Grafikkarte scheitert auf viele Arten (Treiber, DLL, Speicher)
            fehler = e
    raise TranskriptFehler(f"Das Modell „{name}“ lässt sich nicht laden: {fehler}")


def stuecke_waehlen(huelle: Huelle, dauer: float) -> list[tuple[float, float]]:
    """Den Ton an Sprechpausen in Stücke teilen, jedes höchstens ``STUECK_MAX`` lang.

    Getrennt wird mitten in einer Pause — bevorzugt in der längsten, die im Zielbereich liegt. Gibt es
    dort keine (jemand redet 28 Sekunden ohne Luft zu holen), dann hart an der Obergrenze.
    """
    inseln = huelle.inseln()
    pausen = [((b0 + a1) / 2, a1 - b0) for (_, b0), (a1, _) in zip(inseln, inseln[1:]) if a1 - b0 >= 0.2]
    grenzen = [0.0]
    while dauer - grenzen[-1] > STUECK_MAX:
        pos = grenzen[-1]
        moeglich = [(mitte, laenge) for mitte, laenge in pausen if pos + STUECK_MIN <= mitte <= pos + STUECK_MAX]
        gut = [p for p in moeglich if p[0] >= pos + STUECK_ZIEL - 8] or moeglich
        grenzen.append(max(gut, key=lambda p: p[1])[0] if gut else pos + STUECK_MAX)
    grenzen.append(dauer)
    return [(a, b) for a, b in zip(grenzen, grenzen[1:]) if b - a > 0.05]


def transkribieren(wav: Path, sprache: str | None = "de", modell: str = "auto", geraet: str = "auto",
                   hinweis: str | None = None, melden=None, namen: str | None = None) -> dict:
    """Den Ton in Wörter mit Zeiten verwandeln. ``melden(anteil)`` bekommt den Fortschritt (0 bis 1).

    ``namen`` sind Eigennamen und Fachwörter aus dem Video („MAGI, Balthasar“). Whisper schreibt sie
    dann eher richtig, statt das nächstbeste bekannte Wort zu nehmen.
    """
    name = modell_waehlen(modell)
    with wave.open(str(wav), "rb") as f:
        if f.getframerate() != 16000 or f.getnchannels() != 1 or f.getsampwidth() != 2:
            raise TranskriptFehler("Die Transkription erwartet eine Mono-WAV mit 16 kHz und 16 Bit.")
        ton = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    dauer = len(ton) / 16000
    stuecke = stuecke_waehlen(Huelle.aus_wav(wav), dauer)

    t0 = time.monotonic()
    whisper, wo, rechenart = _laden(name, geraet)
    geladen = time.monotonic() - t0
    zustand = {"sprache": sprache or None, "sicher": 1.0}

    def lauf(m, von: float, bis: float) -> list[tuple[str, float, float, float]]:
        teile, info = m.transcribe(
            ton[int(von * 16000):int(bis * 16000)],
            language=zustand["sprache"],
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            # Nicht auf den eigenen Text davor stützen: sonst glättet Whisper Wiederholungen weg
            # oder dreht sich in einer Schleife fest. Wir wollen wörtlich, auch das Verhaspelte.
            condition_on_previous_text=False,
            initial_prompt=hinweis or None,
            hotwords=namen or None,
            beam_size=5,
        )
        woerter = [(w.word, float(w.start) + von, float(w.end) + von, float(w.probability))
                   for s in teile for w in (s.words or [])]
        if zustand["sprache"] is None:      # die Sprache des ersten Stücks gilt für alle
            zustand["sprache"], zustand["sicher"] = info.language, float(info.language_probability)
        return woerter

    t1 = time.monotonic()
    roh: list[tuple[str, float, float, float]] = []
    for von, bis in stuecke:
        try:
            roh += lauf(whisper, von, bis)
        except Exception as e:
            if wo != "cuda":
                raise TranskriptFehler(f"Die Transkription ist gescheitert: {e}") from e
            # Manche Grafikkarten-Fehler zeigen sich erst beim Rechnen (cuDNN fehlt, Speicher voll).
            whisper, wo, rechenart = _laden(name, "cpu")
            roh += lauf(whisper, von, bis)
        if melden:
            melden(bis / dauer if dauer else 1.0)
    gerechnet = time.monotonic() - t1

    return {
        "modell": name,
        "geraet": wo,
        "rechenart": rechenart,
        "sprache": zustand["sprache"] or (sprache or "?"),
        "sprache_sicher": round(zustand["sicher"], 3),
        "dauer": dauer,
        "stuecke": len(stuecke),
        "sekunden_laden": round(geladen, 2),
        "sekunden_rechnen": round(gerechnet, 2),
        "woerter": _aufbereiten(roh),
    }


def _aufbereiten(roh: list[tuple[str, float, float, float]]) -> list[dict]:
    """Whisper-Ausgabe zu sauberen Wörtern: getrimmt, in Reihenfolge, Satzzeichen am Wort davor."""
    woerter: list[dict] = []
    for text, von, bis, p in roh:
        text = text.strip()
        if not text:
            continue
        if not re.search(r"\w", text):
            # Reines Satzzeichen („…“, „-“) hängt Whisper manchmal als eigenes „Wort“ an.
            if woerter:
                woerter[-1]["w"] += text
            continue
        if woerter:
            von = max(von, woerter[-1]["von"])
        bis = max(bis, von + 0.02)
        woerter.append({"i": len(woerter), "w": text, "von": round(von, 3), "bis": round(bis, 3),
                        "p": round(p, 3), "weg": None})
    return woerter


HAENGT = 0.25        # so weit muss ein Wort in eine Stille ragen, um als verrutscht zu gelten
KOPF_MIN = 0.08      # so viel unerklärter Ton muss dann vor dem nächsten Wort liegen
KOPF_MAX = 0.8       # … und höchstens so viel, sonst ist es kein einzelnes Wort mehr
PAUSE_MIN = 0.3      # ab dieser Länge ist eine Stille eine Pause
EIGEN_MAX = 0.06     # hat das Wort mehr eigenen Sprech-Ton als das, liegt es richtig und bleibt
ATMER_LEISER = 18.0  # dB unter der Sprechlautstärke: was leiser ist, gilt als Atmer, nicht als Wort
RAND = 1.0           # so viel Ton am Rand eines Sprechstücks bekommt das Randwort dazu. Großzügig mit
                     # Absicht: lieber einen überhörten Laut behalten als ein Wortende („fer-tig“) verlieren


ANLAUT = 0.15        # so viel leiser Ton direkt vor einem Wort gilt als sein Anlaut (ein „s“, „f“, „h“)


def _ohne_atmer(huelle: Huelle, von: float, bis: float) -> float:
    """Wo das erste Wort eines Sprechstücks wirklich beginnt, wenn es mit einem Atmer anfängt.

    Vor einem neuen Satz wird Luft geholt, und der Atmer hängt lückenlos am ersten Wort — Whisper rechnet
    ihn dem Wort zu. Er ist aber kein Wort: viel leiser als Sprache und länger als jeder Anlaut. Bleibt er
    am Wort, lässt sich die Pause davor nie kurz schneiden (gemessen an Avas Stimme: an neun Satzanfängen
    blieben je 0,5 bis 0,8 statt 0,2 Sekunden stehen). Also beginnt das Wort kurz vor seinem ersten
    sprech-lauten Ton; der Atmer davor gehört zur Pause. Ein Wort, das nirgends sprech-laut wird, bleibt.
    """
    a, b = int(von / huelle.SCHRITT), min(huelle.db.size, int(np.ceil(bis / huelle.SCHRITT)))
    laut = np.flatnonzero(huelle.db[a:b] > huelle.spitze - ATMER_LEISER)
    if laut.size and laut[0] * huelle.SCHRITT > ANLAUT:
        return von + laut[0] * huelle.SCHRITT - ANLAUT
    return von


def verankern(woerter: list[dict], huelle: Huelle) -> None:
    """Die Wortzeiten von Whisper am hörbaren Ton festmachen.

    Whisper trifft Wortgrenzen auf 50 bis 100 ms — außer an Pausen. Dort macht es zwei Fehler, die
    beim Schneiden hörbar würden:

    1. Das erste Wort eines neuen Satzes landet am Ende des Satzes davor und „hängt“ in der Stille.
       Sein wirklicher Ton steht unerklärt vor dem nächsten Wort. → Es kommt dorthin. (Gesehen bei der
       Windows-Stimme und bei ElevenLabs; dort lag sogar noch ein Atmer dazwischen.)
    2. Ein Wort endet zu früh oder beginnt zu spät; ein Rest Ton am Rand des Sprechstücks gehört
       dann keinem Wort. → Das Randwort bekommt ihn, sonst schnitte eine Pausenkürzung ihn ab
       (gemessen: von „fertig.“ fehlte das „-tig“, weil Whisper das Wort im Verschluss des t beendete).

    Danach wird jedes Wort auf seinen hörbaren Teil eingezogen. Die Zeiten von Whisper bleiben als
    ``von_roh``/``bis_roh`` stehen.
    """
    for w in woerter:
        w.setdefault("von_roh", w["von"])
        w.setdefault("bis_roh", w["bis"])
        w["von"], w["bis"] = w["von_roh"], w["bis_roh"]
    inseln = huelle.inseln()
    if not inseln or not woerter:
        return

    # 0. Geister: Der Hinweis „schreib auch die Ähms hin“ verleitet Whisper dazu, in eine stille Pause
    #    ein „ähm“ zu schreiben, das niemand gesagt hat. Ein Füllwort ohne hörbaren Ton fliegt aus der Liste.
    def hoerbar(w: dict) -> float:
        a, b = int(w["von_roh"] / huelle.SCHRITT), min(huelle.db.size, int(np.ceil(w["bis_roh"] / huelle.SCHRITT)))
        return float(np.count_nonzero(huelle.db[a:b] > huelle.schwelle)) * huelle.SCHRITT if b > a else 0.0

    echt = [w for w in woerter if not (ist_fuellwort(w["w"], frozenset()) and hoerbar(w) < 0.03)]
    if len(echt) != len(woerter):
        woerter[:] = echt
        for nr, w in enumerate(woerter):
            w["i"] = nr

    # 1. Verrutschte Wörter über die Pause holen. Vier Zeichen müssen zusammenkommen:
    #    Das Wort davor beendet einen Satz, und Whisper lässt dieses Wort lückenlos anschließen —
    #    die Pause steht also hinter dem ersten Wort des neuen Satzes statt davor. Das Wort ragt in
    #    Stille. Und direkt vor dem nächsten Wort steht Ton, der keinem Wort gehört: sein wahrer Platz.
    def stille_in(von: float, bis: float) -> float:
        return (bis - von) - sum(max(0.0, min(bis, b) - max(von, a)) for a, b in inseln)

    def eigener_ton(w: dict) -> float:
        """Wie viel sprech-lauter Ton in der Whisper-Spanne des Wortes liegt, der nicht einfach der
        Ausklang des Wortes davor ist. Ein Atmer zählt nicht — er ist viel leiser als Sprache."""
        schritt = huelle.SCHRITT
        a, b = int(w["von_roh"] / schritt), min(huelle.db.size, int(np.ceil(w["bis_roh"] / schritt)))
        rest = next((ende for start, ende in inseln if start <= w["von_roh"] < ende), w["von_roh"])
        a = max(a, int(np.ceil(rest / schritt)))      # der Rest des Sprechstücks davor gehört dem Wort davor
        return float(np.count_nonzero(huelle.db[a:b] > huelle.spitze - ATMER_LEISER)) * schritt if b > a else 0.0

    for nr in range(1, len(woerter) - 1):
        davor, w, danach = woerter[nr - 1], woerter[nr], woerter[nr + 1]
        insel = next(((a, b) for a, b in inseln if a - 0.05 <= danach["von_roh"] < b), None)
        if insel is None:
            continue
        kopf = danach["von_roh"] - insel[0]
        if (satzende(davor["w"]) and w["von_roh"] - davor["bis_roh"] < 0.15
                and danach["von_roh"] - w["bis_roh"] >= PAUSE_MIN
                and stille_in(w["von_roh"], w["bis_roh"]) >= HAENGT
                and KOPF_MIN <= kopf <= KOPF_MAX
                and eigener_ton(w) < EIGEN_MAX):
            w["von"], w["bis"] = insel[0], danach["von_roh"]
            w["verrutscht"] = True

    # 2. Auf den hörbaren Teil einziehen
    for w in woerter:
        von, bis = huelle.eingrenzen(w["von"], w["bis"])
        w["von"], w["bis"] = von, bis

    # 3. Ränder der Sprechstücke den Randwörtern geben
    k = 0
    for von, bis in inseln:
        while k < len(woerter) and (woerter[k]["von"] + woerter[k]["bis"]) / 2 < von:
            k += 1
        erstes = k
        while k < len(woerter) and (woerter[k]["von"] + woerter[k]["bis"]) / 2 < bis:
            k += 1
        if k == erstes:
            continue
        a, z = woerter[erstes], woerter[k - 1]
        if 0 < a["von"] - von <= RAND:
            a["von"] = von
        a["von"] = _ohne_atmer(huelle, a["von"], a["bis"])
        if 0 < bis - z["bis"] <= RAND:
            z["bis"] = bis

    # 4. Überlappungen auflösen, runden
    for a, b in zip(woerter, woerter[1:]):
        if b["von"] < a["bis"]:
            mitte = min(max((a["bis"] + b["von"]) / 2, a["von"] + 0.01), max(b["bis"] - 0.01, a["von"] + 0.01))
            a["bis"] = b["von"] = mitte
            b["bis"] = max(b["bis"], b["von"] + 0.01)
    for w in woerter:
        w["von"] = round(w["von"], 3)
        w["bis"] = round(max(w["bis"], w["von"] + 0.01), 3)


def modell_holen(name: str) -> str:
    """Ein Modell aus dem Netz laden (Hugging Face). Der einzige Ort im Modul, der etwas herunterlädt."""
    from faster_whisper.utils import download_model
    return download_model(name)
