# MAGI · Videoschnitt

Rohvideo rein, fertiges Video raus: Pausen, Füllwörter und Versprecher fliegen raus, Untertitel kommen drauf,
dazu in Maßen, was Zuschauer hält (Zoom-Wechsel, betonte Wörter, Schlagzeilen, Fortschrittsbalken). Alles läuft auf
dem Rechner (faster-whisper, ffmpeg) — kein Ton und kein Bild verlässt ihn. Das Rohvideo wird nie verändert.

**Stand 2026-10-12, Version 0.4:** gebaut, gemessen, von drei unabhängigen Prüfern gegengelesen (Rechnung, Bedienung,
Codex) und nachgebessert. Sechs Videos sind durchgelaufen (Chefs Vorbild, das Testvideo eines Kollegen in zwei
Fassungen, MAGIs Erklärvideo in zwei Fassungen, das Werbevideo). Neu in 0.3: leise Klänge zu Bildeffekten,
Bewegungsgrafik aus dem Browser, Atmer bleiben nicht mehr an Satzanfängen hängen. Neu in 0.4: **Grafik über gefilmten
Videos** (`schnitt.py grafik`). Der vierte Prüfer (Rendern mit schwierigen Handyvideos) ist nicht fertig geworden —
siehe unten.

## Was installiert sein muss

Auf Chefs PC ist alles da (`python schnitt.py pruefen`, auch von außerhalb der Claude-App geprüft):

| Was | Wozu | Falls es fehlt |
|---|---|---|
| Python 3.10+ | läuft alles drin | — |
| ffmpeg + ffprobe mit libass, Version 7 oder neuer (hier 9.0.2 full) | schneiden, Untertitel einbrennen | `winget install --id Gyan.FFmpeg -e --scope user` |
| `faster-whisper`, `numpy` | Wörter mit Zeiten erkennen | `python -m pip install faster-whisper numpy` |
| `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` | Whisper auf der Grafikkarte (freiwillig) | `python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` |
| `pillow` | Zeilenbreite ausmessen (freiwillig, sonst geschätzt) | `python -m pip install pillow` |
| ein Whisper-Modell | liegt: `small` | `python schnitt.py modell-holen large-v3-turbo --ja` (ca. 1,6 GB, **nur mit Chefs Ja**) |

Das Modul lädt nie von selbst etwas herunter.

## Bedienen

Üblicher Ablauf: `vorbereiten` → (`zeigen`, `aendern`) → `rendern`. `python schnitt.py --help` und jedes
`<befehl> --help` erklären alles auf Deutsch.

```
python schnitt.py stile                                 Stile mit Format
python schnitt.py vorbereiten VIDEO --stil reel         transkribieren + Plan nach Regeln (--namen "MAGI, Raphael")
python schnitt.py zeigen VIDEO [--von 300 --bis 600]    Plan lesen, ändert nichts
python schnitt.py aendern VIDEO --annehmen k2 --ablehnen k1 --weg 12-18 --doch 40
                              --schnitt 10.5-14.2 --halten 30-33          (Sekunden des Rohvideos)
                              --schreibweise 55=Raphael --drehbuch text.txt
                              --betonen 7,21-22 --schlagzeile "0-6=kleine Zeile|GROSSE ZEILE|Akzentwort"
                              --zuruecksetzen
python schnitt.py rendern VIDEO --bilder 3 [--probe 10] [--ausgabe X.mp4]
python schnitt.py alles VIDEO --stil reel [--vertraulich]   beides in einem Zug, nur nach Regeln
python schnitt.py referenz VORBILD.mp4                  Standbilder + Takt eines Vorbilds
```

- Neben dem Video entsteht `<name>.schnitt\`: Transkript, `schnittplan.json`, lesbare `schnittplan.txt`, `schnitt.edl`,
  Untertitel als `.ass`/`.srt`, `bericht.md`, `blick-*.png`.
- Das Ergebnis heißt `<name>-geschnitten.mp4`; gibt es das schon, `-geschnitten-2`, `-3` … Der Pfad steht in der Zeile
  `FERTIG`. Die Probe (`-probe.mp4`) wird jedes Mal ersetzt.
- Ein zweites `vorbereiten` mit anderem Stil **behält** die Entscheidungen aus `aendern`.
- Zeiten im Plan sind Rohvideo-Zeiten; die Spalte daneben zeigt die Stelle im fertigen Video.

## Wie es arbeitet

1. **Transkription** (`transkript.py`): Der Ton wird an Pausen in Stücke unter 30 s geteilt, jedes Stück einzeln
   erkannt (sonst gilt der Hinweis „schreib die Ähms hin" nur für die ersten 30 s). Danach werden die Wörter am
   hörbaren Ton **verankert** und erfundene Füllwörter in der Stille gestrichen.
2. **Schnittlogik** (`schnittlogik.py`): Füllwörter, Wiederholungen, abgebrochene Anläufe, doppelte Sätze.
   **Sicher geschnitten wird nur, was nichts Eigenes verliert.** Parallelsätze („Ich war in Berlin, ich war in
   Hamburg") bleiben und stehen als offene Frage im Plan. Pausen ab `pause_ab` werden auf `pause_ziel` gekürzt.
3. **Rendern** (`rendern.py`): ein ffmpeg-Lauf, geschnitten in ganzen Bildnummern und Abtastwerten; Bild und Ton
   getrennt zusammengesetzt (das Bild darf öfter wechseln). Lautheit: erst messen, dann fest anheben. Danach wird
   nachgezählt, nicht geglaubt.

## Stile

Ein Stil ist eine JSON-Datei; `standard.json` hat alle Schlüssel, jeder andere erbt (`"erbt": "reel"`) und nennt nur
Abweichungen. `--stil` nimmt einen Namen aus `stile\` oder den Pfad einer Datei.

| Stil | Format | Kurz |
|---|---|---|
| `standard` | wie gefilmt | Großbuchstaben, gesprochenes Wort gelb |
| `ruhig` | wie gefilmt | lässt Atempausen, dezente Untertitel |
| `schnell` | **9:16** | harte Schnitte, auch weiche Füllwörter raus, Zoom |
| `reel` | wie gefilmt | nach Chefs Vorbild: dicht, Untertitel bauen sich auf, Zahlen betont, Zoom-Takt, Balken |
| `magi` | wie gefilmt | wie reel in MAGIs Farben, ohne Zoom/Balken (für Grafik-Videos) |

Die wichtigsten Schlüssel (Größen = Anteil der kürzeren Bildkante, Lagen = Anteil der Bildhöhe von oben):

- `schnitt`: `pause_ab`, `pause_ziel`, `streng` (auch „also", „halt" …), `vorlauf`, `nachlauf`
- `untertitel`: `art` (`farbe` | `aufbau`), `schrift` (Name wie in Windows, sonst nimmt libass still Arial → `ACHTUNG`),
  `groesse`, `position` (bei Selfies eher 0.8, damit nichts auf dem Mund liegt), `farbe`, `farbe_aktiv`,
  `farbe_dunkel` + `kontrast: auto` (auf hellem Grund dunkle Schrift), `betonen` (`aus` | `zahlen`),
  `farbe_betont` / `farbe_betont_2` (es gewinnt, was sich vom Hintergrund abhebt), `woerter_max`, `zeichen_max`
- `bindung`: `fortschritt` (Balken oben)
- `bild`: `format` (`original`, `9:16`, `4:5`, `1:1`, `16:9`), `anpassen` (`zuschneiden` | `einpassen`),
  `zoom_bei_schnitt` (z. B. 1.12), `zoom_takt` (spätestens alle n Sekunden ein Wechsel), `zoom_mitte_y`
- `ton`: `lautheit`, `ziel_lufs`, `raumklang` (0 bis 1), `effekte` (Klänge zu Bildeffekten: 0 aus, 1 normal, bis 2)

## Klänge zu Bildeffekten

Wo im Bild etwas passiert, darf es leise klingen — aber die Stimme bleibt vorn (Chef: „übertreib nicht“). `videoschnitt\klang.py`
rechnet acht kurze Klänge selbst (`wusch`, `pop`, `tick`, `klick`, `glocke`, `tiefe`, `aufstieg`, `schnipp`): keine
Fremddateien, keine Lizenzen. Gemischt wird nach dem Einpegeln der Stimme und vor dem Begrenzer.

- Stil-Schalter `ton.effekte`: Bei einem Wert über 0 bekommt jede Schlagzeile einen leisen Luftzug (`reel`: 0.7).
- Eigene Liste: `rendern VIDEO --klaenge liste.json` mit `[{"zeit": 12.4, "art": "pop", "staerke": 0.8}]` — die Zeit
  zählt im fertigen Video.
- Gemessen an beiden Motion-Videos: Die Klangspur liegt 22 bis 24 dB unter der Stimme, ihre Spitzen bei −15 dB.
  **Ob das beim Hören passt, kann nur Chef sagen** — lauter oder leiser macht man es mit `ton.effekte`.

## Bewegungsgrafik (Szenen als Webseite)

`grafik\ablichten.mjs` öffnet eine Webseite unsichtbar in Edge oder Chrome, ruft für jedes Bild `window.zeit(t)` auf und
fotografiert das Ergebnis; die Bilder gehen direkt an ffmpeg. Gebraucht wird nur Node ab Version 22 — nichts wird
installiert oder geladen. Tempo am PC: 10 bis 13 Bilder je Sekunde bei 1080×1920.

    node grafik\ablichten.mjs szene.html --aus film.mp4 --dauer 12 [--daten werte.json] [--ton stimme.wav]
                                          [--uhr stuecke.json] [--auskunft aus.json] [--bild 3.5] [--durchsichtig]

- `--uhr` bekommt die Stücke eines Schnittplans. Dann zählt die Zeit der Szene nur in den Bildern, die der Schnitt
  behält: Die Rohfassung steht in den Pausen still, und nach dem Schnitt läuft die Grafik ohne Sprung durch
  (nachgemessen: Bild aus dem fertigen Film gegen die Seite zur selben Sekunde, Abweichung unter 1 von 255).
- `--auskunft` schreibt, was die Seite in `window.AUSKUNFT` ablegt — so kommen die Klang-Zeitpunkte zum Schnitt.
- `--durchsichtig` lichtet mit durchsichtigem Grund ab (für die Grafik über gefilmten Videos, siehe unten).
- Bauen: `beispiele\magi-erklaert-sich\motion.py` (`--daten`, `--bogen`, `--bild`, `--film`, `--projekt ORDNER`).

## Grafik über einem gefilmten Video

Karten, Schrift im Takt der Stimme, Zähler und kleine Schaubilder liegen über dem Bild — unter den Untertiteln.

    python schnitt.py grafik  <video oder arbeitsordner> --szenen seite.html [--bild 7.5]
    python schnitt.py rendern <video oder arbeitsordner>          (nimmt grafik.mov von selbst; --ohne-grafik lässt sie weg)

- Die Szenen-Seite ist HTML mit ein paar data-Angaben; den Rest macht `grafik\motor.js` (wird von selbst geladen,
  der Aufbau steht oben in der Datei). Zeitpunkte sind **Wortnummern aus `zeigen`**: `data-ab="w:26"` heißt „wenn Wort 26
  beginnt“. Eine `.zeile` erscheint Wort für Wort mit den gesprochenen Wörtern. `data-klang="pop:0.6"` setzt einen Klang dazu.
- Heraus kommt `grafik.mov` im Arbeitsordner (durchsichtig, so lang wie das Ergebnis). Ändert sich danach der Schnitt,
  verweigert `rendern` die alte Grafik und verlangt ein neues Ablichten.
- Wohin die Karten dürfen, entscheidet man je Video an einem Standbild (`--bild`): Es gibt keine Gesichtserkennung.
  Beim Video des Kollegen ist es der freie Streifen über dem Kopf.
- **Die Grafik zeigt nur, was im Video gesagt wird.** Zahlen und Fakten, die der Sprecher nicht nennt, kommen nicht
  hinein; Schaubilder ohne Zahlen heißen „Schema“.
- Braucht Node ab Version 22 und Edge oder Chrome. Tempo am PC: etwa 12 Bilder je Sekunde (28 s Video in 71 s).
- Beispiel: `Desktop\claude\videos\kollege-test\grafik\szenen.html` → `Kollege-Rente-motion.mp4`.

## Gemessen (2026-10-11, RTX 4060)

- `tests\test_schnittlogik.py`: 38 Prüfungen der Logik ohne Medien.
- `tests\selbsttest.py`: **23 von 23**. Testaufnahme 63,4 s → 36,1 s; alle 5 Füllwörter, Wiederholung, Anlauf und
  doppelter Satz raus, gewollte Anapher bleibt; das Ergebnis neu transkribiert: 100 % der saubere Text.
- `tests\gleichlauf_pruefen.py`: Bild und Ton nach 40 bis 110 Schnitten bei 25, 29,97, 30 und 60 Bildern/s höchstens
  0,2 ms auseinander — auch mit Zoom-Wechseln, die nur das Bild teilen.
- Raumklang-Filter (Stärke 0,7) am Video des Kollegen, am selben Ton gemessen: Pausen 9 dB leiser, Nachklang fällt
  13 dB schneller ab, das Topfige um 300 Hz 4 dB zurück. **Den Hall unter der laufenden Stimme nimmt er nicht weg** —
  dafür bräuchte es ein gelerntes Modell (DeepFilterNet), das nur mit Chefs Ja installiert würde.
- Tempo: 63 s transkribiert in 2 s, 36 s gerendert in 5 s (NVENC).
- Atmer (2026-10-12): An Avas Stimme blieben an neun Satzanfängen 0,5 bis 0,8 statt 0,2 s stehen, weil der Atmer
  als Teil des ersten Wortes galt und die Schnittkante um ihn herumlief. Behoben in `transkript.verankern` und
  `Huelle.kante`; danach wieder Selbsttest 23/23, Logik 38/38, Wahrheitsprobe 27 von 28 Stücken.

## Was nicht geprüft ist — ehrlich

- **Gedrehte Handyvideos, schwankende Bildrate, später beginnende Tonspur, HDR** (`HDR_KETTE` in `rendern.py`):
  ungeprüft. Der Prüfer dafür ist am Nutzungslimit abgebrochen.
- **Das Modell `small` verhört sich bei echtem Sprechen** („fang zu früh" statt „fangt so früh"). Beim Video des
  Kollegen wurden neun Wörter nach Sinn richtiggestellt, nicht nach Gehör. Besser: `large-v3-turbo`.
- Wo ein Wort ohne Pause in ein Füllwort übergeht, sitzt der Schnitt auf etwa 50 ms genau.
- Untertitel können bei Selfies auf dem Gesicht liegen — die Lage (`untertitel.position`) stellt man je Video ein;
  eine Gesichtserkennung gibt es nicht.
- Zoom-Wechsel sind harte Sprünge zwischen zwei Größen, keine weiche Kamerafahrt.
- `schnitt.edl` ist in keinem Schnittprogramm geprüft.
- **Kundenaufnahmen gehören nicht durch MAGIs Gehirn** (Regel „nur Privates"). Wenn überhaupt: `alles --vertraulich`,
  und dann nichts ansehen — die Untertitel stehen ja im Bild.

## Mitnehmen auf einen anderen Rechner

`powershell -NoProfile -ExecutionPolicy Bypass -File mitnehmen\paket_bauen.ps1` packt das **Komplettpaket** nach
`Desktop\MAGI-Komplettpaket` (575 MB): MAGI selbst (`MAGI.exe`, Einstellungen, Quelltext, Bauplan, Charakter), das
Schnitt-Werkzeug mit dem Modell `small`, die eigenen Skills, `einrichten.ps1`, `LIES-MICH.md`. Nicht darin: Schlüssel,
Anmeldungen, Vault, Chats. Auf dem anderen Rechner `einrichten.ps1` starten: Es kopiert an den richtigen Platz, prüft
und nennt die Befehle für das, was fehlt — es installiert und lädt nichts selbst und überschreibt kein vorhandenes MAGI.

**Warum der Quelltext mitkommt:** MAGI findet seinen Ordner über `quelle\MAGI.csproj`. Liegt nur die `MAGI.exe` da,
hält es `programm\` für sein Zuhause, und Claude arbeitet im falschen Ordner (so war das erste Paket vom 2026-10-11).

Geprüft am PC auf einem leeren Probe-Ordner: `einrichten.ps1` läuft durch, MAGI, Werkzeug und Skills liegen am Platz,
`pruefen` meldet BEREIT. Das Werkzeug allein lief dort früher auch im „Laptop-Modus“ (Prozessor statt Grafikkarte,
Modell nur aus dem Paket): Selbsttest 23 von 23. Am 2026-10-12 außerdem: alle Dateien des Pakets mit den Originalen
verglichen (gleich), und **MAGI aus dem eingerichteten Probe-Ordner gestartet** — von außerhalb der Claude-App, in MAGIs
Selbsttest: Fenster da, Gehirn bereit (Claude Pro), `daten\` am richtigen Platz. **Auf dem Laptop selbst ist nichts gemessen.**

Von außerhalb der Claude-App gestartet (so wie MAGI es tut): `tests\aussen_pruefen.ps1 -Video <video>` — lief am PC durch.

## Beispiele

- `beispiele\magi-erklaert-sich\` — MAGI erklärt sich selbst: Zahlen aus dem Projekt (`daten.py`), Avas Stimme
  (`stimme.py`, nur mit `--stimme-holen`). Zwei Fassungen aus derselben Aufnahme:
  - `bauen.py` + `bild.py` (Pillow): `ausgabe\MAGI-erklaert-sich.mp4` (60 s, mit Untertiteln).
  - `motion.py` + `motion\szenen.html` (Browser): `ausgabe\MAGI-erklaert-sich-motion.mp4` (63,5 s) — im Stil von Chefs
    drittem Vorbild: große Schrift im Takt der Stimme, ganze Flächen hell / dunkel / eine Akzentfarbe, Funken, Klänge.
- `beispiele\magi-fuer-die-welt\` — Werbevideo „MAGI für die Welt“ im Stil des zweiten Vorbilds (weicher Grund,
  Glaskarten, Mauszeiger, Buchstaben aus der Unschärfe), mit Untertiteln: `ausgabe\MAGI-fuer-die-Welt.mp4` (37,4 s).
  Gebaut mit `python ..\magi-erklaert-sich\motion.py --projekt . --film`. Nichts Privates im Bild.
- `Desktop\claude\videos\kollege-test\` — das Testvideo des Kollegen mit eigenem Stil (`stil-kollege.json`):
  `Kollege-Rente-geschnitten.mp4` (Schnitt, Untertitel, Schlagzeilen) und `Kollege-Rente-motion.mp4` (dazu Grafik über
  dem Bild aus `grafik\szenen.html`, Arbeitsordner `roh.motion.schnitt`).

## Was als Nächstes dran ist

Chefs Reihenfolge vom 2026-10-11 abends: erst das Werkzeug fertig in MAGI und auf dem Laptop, dann — wenn Limit übrig ist:

1. **Faktenbasierte Einblendungen.** Geht es im Video um ein Thema wie die Rentenlücke, soll MAGI eine kleine
   Einblendung mit einer belegten Zahl dazusetzen — „nicht übertrieben". Offen: woher die Zahl kommt (Quelle nennen,
   nichts erfinden) und wer sie freigibt.
2. **Die Grafik auf Zuruf.** `schnitt.py grafik` legt eine Szenen-Seite über das Video — die Seite schreibt aber
   bisher Claude von Hand je Video. Es fehlt: fertige Bausteine (Karte mit Stichpunkten, Zitat, Vergleich), aus denen
   MAGI wählt, und ein Weg, den freien Platz im Bild selbst zu finden.
