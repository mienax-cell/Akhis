# Videoschnitt-Paket

Dieser Ordner ist ein weitergegebenes, fertiges Paket: ein Schnitt-Werkzeug für gesprochene Videos (Reels, Shorts,
Erklärvideos) und die fünf ArtCraft-Programme. Werkzeug-Stand 0.4 vom 2026-10-12, gepackt am 2026-10-13.
Für Menschen steht alles in `LIES-MICH.md`.

## Was wo liegt

- `videoschnitt\` — das Werkzeug (`schnitt.py`). Läuft ganz auf dem Rechner (faster-whisper, ffmpeg), nichts geht ins
  Netz. Das Whisper-Modell `small` liegt in `videoschnitt\modelle\`. Technische Doku: `videoschnitt\README.md`.
- `.claude\skills\video-schnitt\` — der Skill dazu. Bei „schneid das Video …“, „Untertitel drauf“, „mach ein Reel
  daraus“ diesen Skill nehmen.
- `artcraft\` — FilmCraft (Videoschnitt), EffectCraft (Bewegungsgrafik, Effekte), PhotoCraft (Bildbearbeitung),
  LightCraft (Fotos entwickeln), VectorCraft (Vektorgrafik). Portable Programme; zu jedem gibt es `<name>-cli.exe`
  für die Kommandozeile (`--help` zeigt, was es kann).
- `einrichten.ps1` / `einrichten.cmd` — prüft, was auf dem Rechner fehlt, und nennt die Befehle dafür.
- `videocutter\` — die App zum Werkzeug (`starten.cmd`, läuft im Browser). Ihr Regelwerk liegt in
  `videocutter\regelwerk\` und ist hier eine neutrale Vorlage.

Aus GitHub geklont? Dann fehlen `videoschnitt\modelle\` und `artcraft\` (zu groß für Git). Das Modell holt
`python videoschnitt\schnitt.py modell-holen small --ja` (ca. 480 MB, nur mit Ja des Nutzers), ArtCraft gibt es unter
https://getartcraft.com/apps.

## Regeln

- Auf einem neuen Rechner zuerst `python videoschnitt\schnitt.py pruefen` (oder `einrichten.cmd`).
- Nichts installieren und nichts herunterladen ohne das Ja des Nutzers — den Befehl zeigen, er entscheidet.
- Rohvideos nie überschreiben oder löschen. Ergebnisse landen neben dem Video.
- Aufnahmen mit Kunden nicht ansehen und nicht transkribiert lesen (siehe „Grenzen“ im Skill).
- `videoschnitt\` nicht umbauen, ohne dass der Nutzer es will: Nach Änderungen müssen
  `python videoschnitt\tests\test_schnittlogik.py` (38 Prüfungen) und `python videoschnitt\tests\selbsttest.py`
  (23 Prüfungen) wieder durchlaufen.
- Die README im Modul stammt vom Ursprungsrechner. Pfade wie `Desktop\claude\…`, das Skript
  `mitnehmen\paket_bauen.ps1` und das Beispiel `videos\kollege-test\` gibt es in diesem Paket nicht.
