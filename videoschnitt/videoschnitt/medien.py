"""Medien — was über das Rohvideo zu wissen ist, sein Ton als WAV und der Lautstärke-Verlauf.

Alle Zeiten liegen auf der Zeitachse der Datei (Null = Anfang des Containers), nicht auf der einer
einzelnen Spur: Handyvideos lassen Bild oder Ton gern ein paar Hundertstel später anfangen.
"""
from __future__ import annotations

import json
import subprocess
import wave
from fractions import Fraction
from pathlib import Path

import numpy as np

from . import ModulFehler, umgebung

UEBLICHE_BILDRATEN = (24, 25, 30, 50, 60)
HDR_KENNUNGEN = {"arib-std-b67": "HLG", "smpte2084": "PQ"}


class MedienFehler(ModulFehler):
    pass


def _bruch(text: str | None) -> Fraction | None:
    try:
        z, _, n = (text or "").partition("/")
        wert = Fraction(int(z), int(n or 1))
        return wert if wert > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _drehung(strom: dict) -> int:
    """Um wie viel Grad der Abspieler das Bild dreht (Handy hochkant gefilmt)."""
    for seite in strom.get("side_data_list") or []:
        if "rotation" in seite:
            try:
                return int(round(float(seite["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    try:
        return int(round(float((strom.get("tags") or {}).get("rotate", 0)))) % 360
    except (TypeError, ValueError):
        return 0


def auskunft(pfad: Path) -> dict:
    """Mit ffprobe nachsehen, was das Video ist. Breite und Höhe sind die, die man beim Abspielen sieht."""
    lauf = subprocess.run(
        [umgebung.ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(pfad)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if lauf.returncode != 0:
        raise MedienFehler(f"ffprobe kann die Datei nicht lesen: {lauf.stderr.strip()[:300]}")
    daten = json.loads(lauf.stdout)
    stroeme = daten.get("streams", [])
    bild = next((s for s in stroeme if s.get("codec_type") == "video"
                 and not (s.get("disposition") or {}).get("attached_pic")), None)
    ton = next((s for s in stroeme if s.get("codec_type") == "audio"), None)
    if bild is None:
        raise MedienFehler("Die Datei hat keine Bildspur.")
    if ton is None:
        raise MedienFehler("Die Datei hat keine Tonspur — ohne Ton gibt es nichts zu transkribieren.")

    breite, hoehe = int(bild["width"]), int(bild["height"])
    sar = _bruch((bild.get("sample_aspect_ratio") or "").replace(":", "/"))
    if sar and sar != 1:
        breite = int(round(breite * sar))
    drehung = _drehung(bild)
    if drehung in (90, 270):
        breite, hoehe = hoehe, breite

    mittel, nenn = _bruch(bild.get("avg_frame_rate")), _bruch(bild.get("r_frame_rate"))
    rate = mittel or nenn or Fraction(30)
    # Schwankende Bildrate (Handy): mittlere und Nennrate klaffen auseinander.
    schwankt = bool(mittel and nenn and abs(float(mittel) / float(nenn) - 1) > 0.01)

    dauer = float(bild.get("duration") or daten.get("format", {}).get("duration") or 0)
    if dauer <= 0:
        dauer = float(daten.get("format", {}).get("duration") or 0)
    if dauer <= 0:
        raise MedienFehler("ffprobe nennt keine Dauer.")

    return {
        "datei": str(pfad),
        "dauer": dauer,
        "breite": breite,
        "hoehe": hoehe,
        "drehung": drehung,
        "bildrate": f"{rate.numerator}/{rate.denominator}",
        "bildrate_schwankt": schwankt,
        "bild_codec": bild.get("codec_name"),
        "pixelformat": bild.get("pix_fmt"),
        "hdr": HDR_KENNUNGEN.get(bild.get("color_transfer") or ""),
        "bild_start": float(bild.get("start_time") or 0),
        "ton_codec": ton.get("codec_name"),
        "ton_rate": int(ton.get("sample_rate") or 0),
        "ton_kanaele": int(ton.get("channels") or 0),
        "ton_start": float(ton.get("start_time") or 0),
    }


def bildrate_waehlen(info: dict, wunsch) -> Fraction:
    """Die feste Bildrate des Ergebnisses. Schwankende oder sehr hohe Raten werden auf eine übliche gelegt."""
    if wunsch != "original":
        return Fraction(wunsch).limit_denominator(1001)
    rate = _bruch(info["bildrate"]) or Fraction(30)
    if info.get("bildrate_schwankt") or rate > 60:
        return Fraction(min(UEBLICHE_BILDRATEN, key=lambda r: abs(r - min(float(rate), 60.0))))
    return rate.limit_denominator(1001)


def ton_herausziehen(video: Path, wav: Path) -> None:
    """Den Ton als 16-kHz-Mono-WAV ablegen — so will ihn Whisper, und so rechnet die Hüllkurve.

    ``first_pts=0`` füllt vorn mit Stille auf, falls die Tonspur später anfängt: Sekunde 0 der WAV
    ist dann Sekunde 0 der Datei.
    """
    lauf = subprocess.run(
        [umgebung.ffmpeg(), "-y", "-v", "error", "-i", str(video), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
         "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", str(wav)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if lauf.returncode != 0 or not wav.is_file():
        raise MedienFehler(f"ffmpeg konnte den Ton nicht herausziehen: {lauf.stderr.strip()[:300]}")


class Band:
    """Was hinter einem Textband im Bild liegt: Helligkeit (aufrufen) und mittlere Farbe, je Zeitpunkt des Rohvideos."""

    def __init__(self, farben: np.ndarray, je_sekunde: int):
        self.farben, self.je_sekunde = farben, je_sekunde
        self.hell = farben @ np.array([0.299, 0.587, 0.114])

    def _nr(self, sekunde: float) -> int:
        return min(len(self.hell) - 1, max(0, int(sekunde * self.je_sekunde)))

    def __call__(self, sekunde: float) -> float:
        """Helligkeit, 0 = schwarz, 255 = weiß."""
        return float(self.hell[self._nr(sekunde)])

    def farbe(self, sekunde: float) -> tuple[float, float, float]:
        r, g, b = self.farben[self._nr(sekunde)]
        return float(r), float(g), float(b)


def helligkeit_messen(video: Path, mitte: float, je_sekunde: int = 15) -> Band | None:
    """Helligkeit und Farbe des Bildes in einem Textband — als Funktion der Zeit im Rohvideo.

    ``mitte`` ist die Lage des Bandes als Anteil der Bildhöhe. Gemessen wird am Rohbild; schneidet der
    Stil das Bild zu, stimmt das Band nur ungefähr. Liefert None, wenn die Messung nicht gelingt.
    """
    oben = min(max(mitte - 0.06, 0.0), 0.88)
    lauf = subprocess.run(
        [umgebung.ffmpeg(), "-v", "error", "-i", str(video), "-an",
         "-vf", f"fps={je_sekunde},crop=iw*0.7:ih*0.12:iw*0.15:ih*{oben:.3f},scale=16:4,format=rgb24",
         "-f", "rawvideo", "-"], capture_output=True)
    if lauf.returncode != 0 or len(lauf.stdout) < 192:
        return None
    roh = np.frombuffer(lauf.stdout[:len(lauf.stdout) // 192 * 192], dtype=np.uint8).reshape(-1, 64, 3)
    return Band(roh.mean(axis=1), je_sekunde)


class Huelle:
    """Lautstärke-Verlauf des Tons in 10-ms-Schritten (dB). Sagt, wo wirklich Stille ist.

    Whisper-Wortgrenzen sind auf 50 bis 100 ms unscharf, und ein Wortende läuft gern in die Pause
    hinein. Die Hüllkurve zieht Wortgrenzen an den hörbaren Rand und legt Schnittkanten an die
    leiseste Stelle in der Nähe.
    """

    SCHRITT = 0.01
    FUGE_TIEFE = 4.0    # dB, die eine Delle unter ihrer Umgebung liegen muss, um als Fuge zu gelten
    ATMER_WEG = 0.15    # Sekunden: Liegt die nächste Stille weiter weg, ist dazwischen ein Atmer, kein Wortrand

    def __init__(self, db: np.ndarray, schwelle: float | None = None):
        self.db = db
        self.schwelle = self._schwelle(db) if schwelle is None else schwelle
        self.spitze = float(np.percentile(db, 95)) if db.size else -20.0   # so laut ist hier Sprache
        self._still: np.ndarray | None = None

    @staticmethod
    def _schwelle(db: np.ndarray) -> float:
        """Ab wann es als „laut“ gilt — richtet sich nach der Aufnahme, nicht nach einer festen Zahl.

        Boden = leise 10 % (Raumrauschen), Spitze = laute 5 % (Sprache). Die Schwelle liegt 10 dB über
        dem Boden, höchstens 35 dB unter der Sprache (stilles Studio) und mindestens 12 dB darunter
        (lauter Raum) — sonst gälte leise Sprache als Stille.
        """
        if db.size == 0:
            return -50.0
        boden, spitze = (float(x) for x in np.percentile(db, (10, 95)))
        return min(max(boden + 10.0, spitze - 35.0), spitze - 12.0)

    @classmethod
    def aus_wav(cls, pfad: Path) -> "Huelle":
        with wave.open(str(pfad), "rb") as f:
            if f.getnchannels() != 1 or f.getsampwidth() != 2:
                raise MedienFehler("Die Hüllkurve erwartet eine Mono-WAV mit 16 Bit.")
            rate = f.getframerate()
            roh = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0
        sprung = max(1, round(rate * cls.SCHRITT))
        fenster = 2 * sprung
        # Fenster um die Schrittmitte legen: Schritt j steht für die Zeit [j, j+1) * 10 ms.
        roh = np.concatenate((np.zeros(sprung // 2), roh, np.zeros(fenster)))
        summe = np.concatenate(([0.0], np.cumsum(roh * roh)))
        anzahl = max(1, (roh.size - fenster) // sprung)
        start = np.arange(anzahl) * sprung
        rms = np.sqrt((summe[start + fenster] - summe[start]) / fenster)
        return cls(20.0 * np.log10(np.maximum(rms, 1e-6)))

    def _schritt(self, t: float) -> int:
        return min(max(int(t / self.SCHRITT), 0), self.db.size)

    def eingrenzen(self, von: float, bis: float) -> tuple[float, float]:
        """Ein Wort auf seinen hörbaren Teil einziehen (nie ausdehnen). Ist nichts hörbar, bleibt es."""
        a, b = self._schritt(von), min(self.db.size, int(np.ceil(bis / self.SCHRITT)))
        if b <= a:
            return von, bis
        laut = np.flatnonzero(self.db[a:b] > self.schwelle)
        if laut.size == 0:
            return von, bis
        neu_von = max(von, (a + int(laut[0])) * self.SCHRITT)
        neu_bis = min(bis, (a + int(laut[-1]) + 1) * self.SCHRITT)
        return (neu_von, neu_bis) if neu_bis > neu_von else (von, bis)

    def _stille(self) -> np.ndarray:
        """Je Schritt: Ist hier wirklich Stille? Kurze Lücken mitten im Sprechen zählen nicht — das sind
        die Verschlüsse von b, d, g, k, p, t. Eine Kante dort schnitte ein Wort durch („fer|tig“)."""
        if self._still is None:
            still = np.ones(self.db.size, dtype=bool)
            for von, bis in self.inseln():
                still[int(round(von / self.SCHRITT)):int(round(bis / self.SCHRITT))] = False
            self._still = still
        return self._still

    def kante(self, lo: float, hi: float, wunsch: float, fuge: bool = True, zurueck: float = 0.03, vor: float = 0.03) -> float:
        """Wo eine Schnittkante zwischen ``lo`` und ``hi`` am besten sitzt.

        Liegt dort Stille: der Wunschpunkt, wenn er still ist (dann bleibt genau die gewollte Luft
        stehen), sonst die nächste stille Stelle.

        Liegt dort keine Stille und ``fuge`` ist an, gehen zwei Wörter ineinander über. Dann zählt die
        Fuge — die Delle im Lautstärke-Verlauf, an der ein Wort ins nächste kippt. Gesucht wird sie
        höchstens ``zurueck`` vor ``lo`` und ``vor`` hinter ``hi``; wie weit das sein darf, weiß der
        Aufrufer (nie weiter als ein halbes Nachbarwort). Gibt es keine deutliche Delle, oder ist
        ``fuge`` aus (reine Pause mit Geräusch), bleibt es beim Wunschpunkt.
        """
        s = self.SCHRITT
        a, b = self._schritt(lo - 0.03), min(self.db.size, int(np.ceil((hi + 0.03) / s)))
        if b <= a:
            return wunsch
        still = a + np.flatnonzero(self._stille()[a:b])
        if still.size:
            if np.any(still == self._schritt(wunsch)):
                return wunsch
            mitten = (still + 0.5) * s
            naechste = float(mitten[int(np.argmin(np.abs(mitten - wunsch)))])
            # In einer reinen Pause liegt zwischen Wunschpunkt und Stille manchmal ein Atmer. Die Kante geht
            # dann nicht um ihn herum (sonst bliebe er ganz stehen und die Pause würde nie kurz), sondern
            # bleibt am Wunschpunkt — die kurze Blende macht den Rest unhörbar.
            return wunsch if not fuge and abs(naechste - wunsch) > self.ATMER_WEG else naechste
        if not fuge:
            return wunsch
        a, b = self._schritt(lo - zurueck), min(self.db.size, int(np.ceil((hi + vor) / s)))
        if b <= a:
            return wunsch
        stueck = self.db[a:b]
        tief = int(np.argmin(stueck))
        if float(np.median(stueck)) - float(stueck[tief]) >= self.FUGE_TIEFE:
            return (a + tief + 0.5) * s
        return wunsch

    def inseln(self, luecke: float = 0.12, mindestens: float = 0.03) -> list[tuple[float, float]]:
        """Die Stücke, in denen wirklich etwas zu hören ist — als (von, bis) in Sekunden.

        Kurze Stille (unter ``luecke``) trennt nicht: das sind Verschlusslaute mitten im Wort.
        Kürzere Schnipsel als ``mindestens`` zählen nicht: das sind Knackser.
        """
        laut = np.concatenate(([0], (self.db > self.schwelle).astype(np.int8), [0]))
        kanten = np.flatnonzero(np.diff(laut))
        roh = [(int(a) * self.SCHRITT, int(b) * self.SCHRITT) for a, b in zip(kanten[::2], kanten[1::2])]
        aus: list[tuple[float, float]] = []
        for von, bis in roh:
            if aus and von - aus[-1][1] < luecke:
                aus[-1] = (aus[-1][0], bis)
            else:
                aus.append((von, bis))
        return [(von, bis) for von, bis in aus if bis - von >= mindestens]

    def stille_anteil(self) -> float:
        return float(np.mean(self.db <= self.schwelle)) if self.db.size else 0.0
