"""Prüft die Schnittlogik ohne Medien — kostet nichts, braucht weder ffmpeg noch Whisper.

Aufruf:  python tests\\test_schnittlogik.py
"""
from __future__ import annotations

import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from videoschnitt import schnittlogik as sl  # noqa: E402
from videoschnitt import stil as stilmodul  # noqa: E402

OPT = json.loads((Path(__file__).resolve().parent.parent / "stile" / "standard.json")
                 .read_text(encoding="utf-8"))["schnitt"]


def woerter(text: str, tempo: float = 0.3, luecke: float = 0.05) -> list[dict]:
    """Aus einem Satz eine Wortliste bauen. ``|1.5`` hinter einem Wort heißt: danach 1,5 s Pause."""
    aus, t = [], 0.5
    for stueck in text.split():
        pause = luecke
        if "|" in stueck:
            stueck, p = stueck.split("|")
            pause = float(p)
        aus.append({"i": len(aus), "w": stueck, "von": round(t, 3), "bis": round(t + tempo, 3), "p": 0.9, "weg": None})
        t += tempo + pause
    return aus


def geplant(text: str, **mehr) -> tuple[list[dict], list[dict]]:
    w = woerter(text)
    opt = {**OPT, **mehr}
    sl.fuellwoerter_markieren(w, opt)
    k = sl.kandidaten_finden(w, opt)
    sl.kandidaten_anwenden(w, k, opt.get("unsichere_anwenden", False))
    return w, k


def bleibt(w: list[dict]) -> str:
    return " ".join(x["w"] for x in w if not x.get("weg"))


class Fuellwoerter(unittest.TestCase):
    def test_laute_in_allen_schreibweisen(self):
        for laut in ("äh", "Ähm,", "ääähm", "Öhm", "hm", "Hmm.", "mhm", "ehm", "uhm", "äm", "M,", "E,", "mm", "Em.", "Mh", "Mmh", "ahm"):
            self.assertTrue(sl.ist_fuellwort(laut, set()), laut)

    def test_echte_woerter_bleiben(self):
        for wort in ("um", "eh", "ehe", "Ehe", "ihm", "Uhr", "am", "im", "Oma", "Hemd", "nehme", "es", "er", "E-Mail", "Emma", "Ahm­ed"):
            self.assertFalse(sl.ist_fuellwort(wort, set()), wort)

    def test_streng_nimmt_weiche_fuellwoerter(self):
        w, _ = geplant("Das ist also halt gut")
        self.assertEqual(bleibt(w), "Das ist also halt gut")
        w, _ = geplant("Das ist also halt gut", streng=True)
        self.assertEqual(bleibt(w), "Das ist gut")


class Wiederholungen(unittest.TestCase):
    def test_zwei_woerter_doppelt(self):
        w, k = geplant("Heute wir haben wir haben ein neues Thema.")
        self.assertEqual(bleibt(w), "Heute wir haben ein neues Thema.")
        self.assertTrue(k[0]["sicher"])

    def test_wiederholung_ueber_fuellwort_hinweg(self):
        w, _ = geplant("wir haben ähm wir haben heute Zeit")
        self.assertEqual(bleibt(w), "wir haben heute Zeit")

    def test_dreifach_bleibt_einmal(self):
        w, _ = geplant("Und ich ich ich gehe")
        self.assertEqual(bleibt(w), "Und ich gehe")

    def test_absichtliche_dopplung_ist_nur_vorschlag(self):
        for satz in ("Das ist sehr sehr gut", "Leute, die die Arbeit machen", "Nein, nein, so nicht", "und und und"):
            w, k = geplant(satz)
            self.assertEqual(bleibt(w), satz, satz)
            self.assertTrue(k and not k[0]["sicher"], satz)

    def test_unsichere_auf_wunsch(self):
        w, _ = geplant("Das ist sehr sehr gut", unsichere_anwenden=True)
        self.assertEqual(bleibt(w), "Das ist sehr gut")

    def test_abschaltbar(self):
        w, k = geplant("wir haben wir haben Zeit", wiederholungen=False, neuansaetze=False, doppelte_saetze=False)
        self.assertEqual(k, [])
        self.assertEqual(bleibt(w), "wir haben wir haben Zeit")


class Neuansaetze(unittest.TestCase):
    def test_abgebrochener_anlauf(self):
        w, _ = geplant("Der wichtigste Punkt ist, dass man...|1.2 Der wichtigste Punkt ist, dass man jeden Tag übt.")
        self.assertEqual(bleibt(w), "Der wichtigste Punkt ist, dass man jeden Tag übt.")

    def test_anlauf_mit_anderem_ende(self):
        # Bricht hart ab (Auslassungspunkte): sicher. Nur ein Komma: Vorschlag — es könnte eine Reihung sein.
        w, _ = geplant("Und dann gehen wir in die...|0.5 und dann gehen wir in den Keller.")
        self.assertEqual(bleibt(w), "und dann gehen wir in den Keller.")
        w, k = geplant("Und dann gehen wir in die,|0.5 und dann gehen wir in den Keller.")
        self.assertEqual(len(bleibt(w).split()), 13)
        self.assertTrue(k and not k[0]["sicher"])

    def test_parallelsaetze_bleiben_stehen(self):
        for satz in ("Ich war in Berlin, ich war in Hamburg, ich war in München.",
                     "Man kann das so machen, man kann das aber auch anders machen.",
                     "Das ist wirklich, wirklich wichtig.",
                     "Ja ja, ja ja, das kenne ich."):
            w, k = geplant(satz)
            self.assertEqual(bleibt(w), satz, satz)
            self.assertTrue(all(not x["sicher"] for x in k), satz)

    def test_selbstverbesserung_und_bruchstueck(self):
        w, _ = geplant("Der wichtigste, also der wichtigste Punkt ist das Sparen.")
        self.assertEqual(bleibt(w), "der wichtigste Punkt ist das Sparen.")
        w, _ = geplant("Die Versich- Versicherung zahlt.")
        self.assertEqual(bleibt(w), "Die Versicherung zahlt.")

    def test_unscharf_erkannter_anlauf(self):
        w, _ = geplant("Der wichtigste Punk ist dass man|1.0 Der wichtigste Punkt ist dass man jeden Tag übt.")
        self.assertEqual(bleibt(w), "Der wichtigste Punkt ist dass man jeden Tag übt.")

    def test_anapher_bleibt_stehen(self):
        satz = "Ich will mehr Zeit.|0.4 Ich will mehr Geld.|0.4 Ich will mehr Ruhe."
        w, k = geplant(satz)
        self.assertEqual(bleibt(w), satz.replace("|0.4", ""))
        self.assertTrue(all(not x["sicher"] for x in k))

    def test_gewollte_reihung_bleibt_stehen(self):
        # So sprach Chefs Kollege im ersten echten Testvideo — die erste Fassung der Regel schnitt den ersten Halbsatz weg.
        satz = ("Fangt so früh an kontinuierlich Rücklagen zu bilden, fangt so früh wie es geht an "
                "Vermögensaufbau zu betreiben.")
        w, k = geplant(satz)
        self.assertEqual(bleibt(w), satz)
        self.assertTrue(k and not k[0]["sicher"])

    def test_eh_ist_nur_vorschlag(self):
        w, k = geplant("Das ist, eh,|0.4 ganz einfach")
        self.assertEqual(bleibt(w), "Das ist, eh, ganz einfach")
        self.assertEqual([x["art"] for x in k], ["fuellwort"])
        w, k = geplant("Das ist eh klar")
        self.assertEqual(k, [])

    def test_gleicher_anfang_ohne_bruch_ist_nur_vorschlag(self):
        satz = "Wenn man das macht und wenn man das richtig macht dann klappt es"
        w, k = geplant(satz)
        self.assertEqual(bleibt(w), satz)


class DoppelteSaetze(unittest.TestCase):
    def test_satz_zweimal(self):
        w, k = geplant("Das ist der zweite Anlauf für diesen Satz.|0.8 Das ist der zweite Anlauf für diesen Satz.|0.5 Weiter.")
        self.assertEqual(bleibt(w), "Das ist der zweite Anlauf für diesen Satz. Weiter.")

    def test_satz_fast_gleich(self):
        w, k = geplant("Heute zeige ich euch drei einfache Tricks für bessere Videos.|0.9 "
                       "Heute zeige ich euch drei einfache Tricks für eure Videos.")
        self.assertEqual(bleibt(w), "Heute zeige ich euch drei einfache Tricks für eure Videos.")

    def test_verschiedene_saetze_bleiben(self):
        satz = "Der erste Tipp ist Licht.|0.5 Der zweite Tipp ist Ton.|0.5 Der dritte Tipp ist Ruhe."
        w, k = geplant(satz)
        self.assertEqual(bleibt(w), satz.replace("|0.5", ""))
        self.assertTrue(all(not x["sicher"] for x in k))


class Segmente(unittest.TestCase):
    FPS = Fraction(30)

    def bauen(self, text: str, dauer: float = 60.0, **mehr):
        w, _ = geplant(text, **mehr)
        return w, sl.segmente_bauen(w, dauer, self.FPS, {**OPT, **mehr})

    def test_ohne_pause_ein_stueck(self):
        w, seg = self.bauen("Hallo zusammen das ist ein Test")
        self.assertEqual(len(seg), 1)
        self.assertAlmostEqual(seg[0]["von"], 0.5 - OPT["anfang_luft"], delta=1 / 30)
        self.assertAlmostEqual(seg[0]["bis"], w[-1]["bis"] + OPT["ende_luft"], delta=1 / 30)

    def test_lange_pause_wird_gekuerzt(self):
        w, seg = self.bauen("Hallo zusammen.|2.0 Das ist ein Test")
        self.assertEqual(len(seg), 2)
        bleibt_stehen = (seg[0]["bis"] - w[1]["bis"]) + (w[2]["von"] - seg[1]["von"])
        self.assertAlmostEqual(bleibt_stehen, OPT["pause_ziel"], delta=2 / 30)

    def test_kurze_pause_bleibt(self):
        _, seg = self.bauen("Hallo zusammen.|0.4 Das ist ein Test")
        self.assertEqual(len(seg), 1)

    def test_fuellwort_wird_herausgeschnitten(self):
        w, seg = self.bauen("Hallo ähm zusammen")
        self.assertEqual(len(seg), 2)
        self.assertLessEqual(seg[0]["bis"], w[1]["von"] + 1 / 30)
        self.assertGreaterEqual(seg[1]["von"], w[1]["bis"] - 1 / 30)

    def test_raster_und_reihenfolge(self):
        _, seg = self.bauen("Eins|1.0 zwei ähm drei|1.5 vier vier fünf.|2.0 Sechs")
        for s in seg:
            self.assertEqual(s["von"], s["k"] / 30)
            self.assertEqual(s["bis"], s["m"] / 30)
            self.assertGreaterEqual(s["m"] - s["k"], 2)
        for a, b in zip(seg, seg[1:]):
            self.assertGreater(b["k"], a["m"])

    def test_bleibt_in_der_videolaenge(self):
        w, seg = self.bauen("Hallo zusammen", dauer=1.2)
        self.assertLessEqual(seg[-1]["m"], 36)

    def test_gebrochene_bildrate(self):
        w, _ = geplant("Hallo zusammen.|2.0 Das ist ein Test")
        fps = Fraction(30000, 1001)
        seg = sl.segmente_bauen(w, 60.0, fps, OPT)
        for s in seg:
            self.assertAlmostEqual(s["von"], float(s["k"] / fps), places=9)

    def test_zeitschnitt_und_halten(self):
        w, _ = geplant("Hallo zusammen.|5.0 Das ist ein Test")
        seg = sl.segmente_bauen(w, 60.0, self.FPS, OPT, zeit_halten=[(2.0, 4.0)])
        self.assertEqual(len(seg), 3)
        self.assertAlmostEqual(seg[1]["von"], 2.0, delta=1 / 30)
        seg = sl.segmente_bauen(w, 60.0, self.FPS, OPT, zeit_schnitte=[(0.0, 3.0)])
        self.assertGreaterEqual(seg[0]["von"], 3.0 - 1 / 30)

    def test_entferntes_wort_am_rand_ist_weg(self):
        w, _ = geplant("Ähm hallo zusammen das ist ein Test also")
        w[-1]["weg"] = "manuell"
        seg = sl.segmente_bauen(w, 30.0, self.FPS, OPT)
        self.assertGreaterEqual(seg[0]["von"], w[0]["bis"] - 1 / 30)       # das „Ähm“ vorn
        self.assertLessEqual(seg[-1]["bis"], w[-1]["von"] + 1 / 30)        # das „also“ hinten

    def test_zeitschnitt_laesst_keinen_splitter(self):
        w, _ = geplant("Hallo zusammen.|2.0 Das ist ein Test und jetzt kommt noch ein Satz der raus soll okay.")
        seg = sl.segmente_bauen(w, 30.0, self.FPS, OPT, zeit_schnitte=[(3.2, 9.0)])
        self.assertEqual(len(seg), 1)

    def test_nichts_uebrig(self):
        w, _ = geplant("ähm äh hm")
        self.assertEqual(sl.segmente_bauen(w, 10.0, self.FPS, OPT), [])

    def test_statistik_geht_auf(self):
        w, seg = self.bauen("Hallo ähm zusammen.|2.0 Jetzt ich ich bin da", dauer=20.0)
        st = sl.statistik(w, seg, 20.0)
        self.assertAlmostEqual(st["dauer_roh"] - st["dauer_ergebnis"], sum(st["sekunden"].values()), places=2)
        self.assertEqual(st["stueck"]["fuellwort"], 1)
        self.assertEqual(st["stueck"]["wiederholung"], 1)
        self.assertEqual(st["stueck"]["pause"], 1)
        self.assertEqual(st["woerter_bleiben"], 6)

    def test_stellen_zaehlen_anlaeufe_nicht_woerter(self):
        w, k = geplant("Der wichtigste Punkt ist, dass man...|1.2 Der wichtigste Punkt ist, dass man jeden Tag übt.")
        seg = sl.segmente_bauen(w, 30.0, self.FPS, OPT)
        st = sl.statistik(w, seg, 30.0, k)
        self.assertEqual(st["stueck"]["wiederholung"], 6)
        self.assertEqual(st["stellen"]["wiederholung"], 1)


class ZeitachseTest(unittest.TestCase):
    def test_umrechnen(self):
        seg = [{"k": 0, "m": 30, "von": 0.0, "bis": 1.0}, {"k": 90, "m": 150, "von": 3.0, "bis": 5.0}]
        z = sl.Zeitachse(seg)
        self.assertEqual(z.dauer, 3.0)
        self.assertEqual(z.wort(0.2, 0.4), (0.2, 0.4))
        self.assertEqual(z.wort(3.5, 4.0), (1.5, 2.0))
        self.assertIsNone(z.wort(1.5, 2.0))
        a, b = z.wort(2.9, 3.4)   # ragt vorn über die Kante — wird an die Kante gelegt
        self.assertAlmostEqual(a, 1.0)
        self.assertAlmostEqual(b, 1.4)


class Stile(unittest.TestCase):
    def test_alle_stile_laden(self):
        namen = [n for n, _ in stilmodul.liste()]
        self.assertIn("standard", namen)
        for name in namen:
            s = stilmodul.laden(name)
            self.assertEqual(s["name"], name)
            self.assertEqual(s["_warnungen"], [], name)

    def test_erben(self):
        s = stilmodul.laden("schnell")
        self.assertTrue(s["schnitt"]["streng"])
        self.assertEqual(s["ton"]["ziel_lufs"], -14)          # geerbt
        self.assertIn("ähm", s["schnitt"]["fuellwoerter"])     # geerbt

    def test_unbekannter_stil(self):
        with self.assertRaises(stilmodul.StilFehler):
            stilmodul.laden("gibtsnicht")


if __name__ == "__main__":
    unittest.main(verbosity=1)
