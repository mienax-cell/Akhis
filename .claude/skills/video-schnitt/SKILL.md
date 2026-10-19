---
version: 0.4.0
name: video-schnitt
description: |
  Schneidet ein Rohvideo auf dem eigenen Rechner: Pausen, Füllwörter („ähm") und
  Versprecher raus, Untertitel drauf, dazu Zoom-Wechsel, betonte Wörter,
  Schlagzeilen und Fortschrittsbalken; fertiges MP4 daneben. Nutzen bei
  "schneid das Video [Pfad]", "schneide ... im Stil von [reel/standard/...]",
  "mach ein Reel / Short / TikTok daraus", "Untertitel drauf", "kürz die Pausen
  raus", "schneid es wie dieses Video". Läuft ganz lokal (faster-whisper,
  ffmpeg), das Rohvideo bleibt unangetastet. NICHT für Aufnahmen mit Kundendaten
  und nicht zum Erzeugen neuer Bilder oder Videos.
argument-hint: "[Pfad zum Rohvideo] [Stil]"
---

# Video-Schnitt

**Paketordner:** der Ordner, in dem `CLAUDE.md` und `einrichten.ps1` liegen — alle Pfade unten gelten ab dort.
„Chef“ heißt in diesem Skill: der Mensch, mit dem du gerade arbeitest.

Werkzeug: `python "videoschnitt\schnitt.py" <befehl>`
(unten kurz `schnitt.py`). Videopfade in Anführungszeichen. `schnitt.py --help` und `schnitt.py <befehl> --help`
erklären jeden Schalter. Vor dem ersten Video auf einem Rechner: `schnitt.py pruefen`.

## Welcher Stil?

`schnitt.py stile` zeigt alle mit Format. „Reel", „Short", „TikTok" sind Wünsche, keine Stile:

- **reel** — dicht geschnitten, Untertitel bauen sich auf, Zahlen betont, Zoom-Takt, Balken. Format bleibt, wie gefilmt.
- **schnell** — macht als einziger von selbst Hochformat 9:16.
- **standard**, **ruhig**, **magi** — siehe Liste.

Nennt Chef keinen Stil oder sagt „wie mein letztes": nicht still `standard` nehmen. `--stil letzter` nimmt den zuletzt
benutzten; gibt es keinen, Chef mit Auswahl fragen. Ist das Rohvideo quer und er will ein Reel: fragen, ob zugeschnitten
werden soll (dann `schnell` oder ein eigener Stil mit `"bild": {"format": "9:16"}`).

## Ablauf

1. **Vorbereiten** — `schnitt.py vorbereiten "<video>" --stil <stil>`
   Nennt Chef Namen oder Fachwörter aus dem Video: `--namen "Name eins, Name zwei"`.
2. **Lesen und entscheiden.** Oben stehen die Zahlen, dann `OFFEN` (Stellen, die die Regeln nicht selbst schneiden),
   dann der Text mit Wortnummern (`[-so-]` fliegt raus, `‖1,8` Pause, `*so*` betont). Wie ein sorgfältiger Cutter:
   - `OFFEN`: echter Versprecher oder abgebrochener Anlauf → `--annehmen kN`. Gewollte Wiederholung oder Reihung
     („fangt früh an zu sparen, fangt früh an zu investieren") → `--ablehnen kN`. Im Zweifel ablehnen und Chef die Stelle nennen.
   - Den übrigen Text lesen: Versprecher, die keine Regel fand (`--weg 12-18`), verhörte Namen und Wörter
     (`--schreibweise 55=Raphael`). Hat Chef den Text des Videos als Datei: `--drehbuch text.txt`.
   - In Maßen, was Zuschauer hält: eine Schlagzeile für den Einstieg und höchstens zwei für Kernaussagen
     (`--schlagzeile "0-6=kleine Zeile|GROSSE ZEILE|Akzentwort"`, möglichst Chefs eigene Worte), dazu die wenigen
     Wörter betonen, auf die es ankommt (`--betonen 12,26`). Nicht jedes zweite Wort.
   Alles in einem Aufruf: `schnitt.py aendern "<video>" --ablehnen k1 --schreibweise 40=Fangt --betonen 12 --schlagzeile "…"`.
   Die Antwort nennt wörtlich, was geändert wurde — gegenlesen. Gibt es nichts zu ändern: `aendern` auslassen.
3. **Rendern** — `schnitt.py rendern "<video>" --bilder 3` (lange Videos im Hintergrund oder mit langem Zeitlimit;
   bei einem neuen Stil erst `--probe 10`).
4. **Ansehen und melden.** Die Zeile `BILDER` nennt drei Standbilder im Arbeitsordner (`blick-1.png` …): mit Read
   ansehen. Liegen Untertitel auf dem Gesicht (Selfie)? Dann eigener Stil mit `"untertitel": {"position": 0.8}`.
   Chef dann in zwei Sätzen: wo die Datei liegt (Pfad aus der Zeile `FERTIG`), wie lang vorher und nachher, was
   rausflog, was offen blieb, und was du nach Sinn statt nach Gehör geändert hast. `ACHTUNG` und `NICHT IN ORDNUNG`
   nie verschweigen.

Schnell und ohne Lesen des Wortlauts: `schnitt.py alles "<video>" --stil <stil>` (nur Regeln).

## Nachbessern

- Plan noch einmal lesen: `schnitt.py zeigen "<video>"` (ändert nichts; bei langen Videos `--von 300 --bis 600`).
- **Sekunden:** Nennt Chef eine Sekunde, meint er fast immer das fertige Video. Der Plan zeigt je Zeile beide Zeiten
  (Rohvideo | fertig); `--schnitt` und `--halten` wollen Rohvideo-Sekunden. Im Zweifel die Stelle vorlesen und fragen.
- „Schneid den Anfang bis … weg": `--schnitt 0-3.1`; die Antwort nennt die getroffenen Wörter. Zurück: `--halten 0-3.1`.
- „Untertitel größer / gelb / weiter unten" oder ein anderer Stil: neue Datei `<name>.json` mit `"erbt": "<stil>"` und
  nur den geänderten Schlüsseln (Schlüssel und Bedeutung: `videoschnitt\README.md`), dann
  `schnitt.py vorbereiten "<video>" --stil <pfad>` — die Entscheidungen aus `aendern` bleiben erhalten — und neu rendern.
- Alles zurück auf die Regeln: `aendern --zuruecksetzen`.
- Jedes weitere Rendern legt eine neue Fassung an (`-geschnitten-2.mp4` …). Chef sagen, welche die neue ist; ältere nur
  auf sein Wort löschen.

## Stil aus einem Vorbild

„Schneid es wie dieses Video": `schnitt.py referenz "<vorbild>"` liefert Messwerte (Sprechtempo, längste Pause,
Vorschlag für `pause_ab`/`pause_ziel`) und Standbilder. Die Bilder ansehen (Schrift, Farben, Lage, Wörter je Zeile),
dann eine Stil-Datei mit `"erbt": "reel"` und den Abweichungen anlegen. Du siehst Standbilder, keinen Film — das Chef sagen.

## Grenzen

- Nie das Rohvideo überschreiben oder löschen.
- Nie ein Modell herunterladen ohne Chefs Ja (`modell-holen … --ja` erst nach seiner Zustimmung, mit Größe).
- Meldet `pruefen` etwas als FEHLT: Chef den genannten Befehl zeigen, nicht selbst installieren.
- Aufnahmen mit Kunden: nicht über Claude. Besteht Chef darauf: nur `alles --vertraulich`, dann Schritt 2 und 4
  auslassen (keine Standbilder ansehen, keine Datei aus dem Arbeitsordner öffnen), nur die Zahlen melden und sagen:
  „Angesehen habe ich es nicht, das musst du selbst."
- Das Modell `small` (liegt dem Paket bei) verhört sich bei schnellem Sprechen. Was du nach Sinn richtigstellst,
  sagst du Chef dazu.
- Stand und Lücken: `videoschnitt\README.md`. Sie stammt vom Rechner, auf dem das Werkzeug gebaut wurde — Pfade wie
  `Desktop\claude\…` und das Skript `mitnehmen\paket_bauen.ps1` gibt es in diesem Paket nicht.

## Klänge zu Bildeffekten

Regel: Zu Bildeffekten gehören leise Klänge, aber nicht übertreiben — der Fokus liegt auf dem Gesprochenen.
Der Stil `reel` macht das von selbst (ein leiser Luftzug je Schlagzeile, `ton.effekte` 0.7). Eigene Klänge:
`rendern "<video>" --klaenge liste.json` mit `[{"zeit": 12.4, "art": "pop", "staerke": 0.8}]` (Zeit im fertigen
Video; Arten: wusch, pop, tick, klick, glocke, tiefe, aufstieg, schnipp). Sparsam setzen und nie auf ein betontes
Wort legen. Du kannst nicht hören: Lautstärke nur messen, das Urteil hat Chef.

## Grafik über dem Video (Karten, Schaubilder)

Wenn Chef „mit Grafik“ oder „mit Einblendungen“ sagt: nach dem Schnittplan eine Szenen-Seite schreiben und ablichten.
Braucht Node ab Version 22 und Edge oder Chrome.

1. `schnitt.py zeigen` lesen — die Wortnummern sind die Zeitpunkte (`data-ab="w:26"`).
2. Ein Standbild des Videos ansehen und den freien Platz suchen (nie über Gesicht oder Untertitel).
3. Seite schreiben: Der Aufbau (Bausteine, Zeitpunkte, Aussehen) steht oben in `videoschnitt\grafik\motor.js`.
   Eine fertige Beispielseite für Grafik über einem gefilmten Video liegt dem Paket nicht bei.
   Erst `schnitt.py grafik "<ordner>" --szenen seite.html --bild 7.5` und das Bild ansehen, dann ganz.
4. `schnitt.py rendern "<ordner>"` — die Grafik liegt dann von selbst über dem Bild. Vorher die Schlagzeilen des Plans
   entfernen (`aendern --schlagzeilen-weg`), sonst steht beides übereinander.

Regel: Die Grafik zeigt nur, was im Video gesagt wird. Keine Zahl und kein Fakt von außen; ein Schaubild ohne Zahlen
heißt „Schema“. Was du umformuliert hast, Chef sagen.
