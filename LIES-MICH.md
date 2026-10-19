# Videoschnitt-Paket

Rohvideo rein, fertiges Video raus: Pausen, Füllwörter („ähm“) und Versprecher fliegen raus, Untertitel kommen
drauf, dazu Zoom-Wechsel, betonte Wörter, Schlagzeilen und ein Fortschrittsbalken. Alles läuft auf dem eigenen
Rechner — kein Ton und kein Bild geht ins Netz, und das Rohvideo wird nie verändert.

Dazu liegen die fünf ArtCraft-Programme bei (Videoschnitt, Effekte, Bild, Foto, Vektor), fertig zum Starten.

Gepackt am 2026-10-13. Der Ordner kann überall liegen (Desktop, Stick, D:\…) — nur als Ganzes kopieren.

## Von GitHub geholt?

Auf GitHub liegt nur das Werkzeug, die App und der Skill. Zwei Dinge sind für Git zu groß und fehlen deshalb:

- **das Sprachmodell** — nach dem Einrichten (unten) einmal laden:
  `python videoschnitt\schnitt.py modell-holen small --ja` (ca. 480 MB). `einrichten.cmd` erinnert daran.
- **die ArtCraft-Programme** (`artcraft\`) — wer sie will, holt sie unter https://getartcraft.com/apps. Das
  Schnitt-Werkzeug läuft ohne sie.

Auch das Testvideo für den Probelauf ist nicht dabei.

Die App zum Werkzeug startet mit Doppelklick auf `videocutter\starten.cmd` und öffnet sich im Browser. Für Skripte
braucht sie Claude Code auf dem Rechner. Ihr Regelwerk (`videocutter\regelwerk\`) ist hier eine neutrale Vorlage
für Finanz-Reels — in der App unter „Regelwerk“ an das eigene Thema anpassen.

## Was drin ist

| Ordner / Datei | Was | Größe |
|---|---|---|
| `videoschnitt\` | das Schnitt-Werkzeug (`schnitt.py`, Version 0.4) mit Stilen, Tests und dem Sprachmodell `small` | ca. 565 MB |
| `artcraft\` | FilmCraft 0.6, EffectCraft 0.8, PhotoCraft 0.7, LightCraft 0.6, VectorCraft 0.10 | ca. 870 MB |
| `.claude\skills\video-schnitt\` | der Skill, mit dem Claude das Werkzeug bedient | klein |
| `CLAUDE.md` | sagt Claude, was in diesem Ordner liegt | klein |
| `einrichten.cmd` / `einrichten.ps1` | prüft, was auf dem Rechner fehlt | klein |

## Einrichten (einmal)

1. **Doppelklick auf `einrichten.cmd`.** Es prüft den Rechner und installiert selbst nichts. Fehlt etwas, steht am
   Ende der Befehl dafür.
2. **Was fehlt, nachholen** — die Befehle in ein PowerShell-Fenster kopieren. Auf einem frischen Windows sind das meist:

   ```
   winget install --id Python.Python.3.12 -e --scope user
   winget install --id Gyan.FFmpeg -e --scope user
   ```

   dann ein **neues** Fenster öffnen und:

   ```
   python -m pip install faster-whisper numpy pillow
   ```

   (Kennt das Fenster `python` nicht, aber `py`: überall `py` statt `python` schreiben.)

3. **`einrichten.cmd` noch einmal starten.** Steht am Ende `BEREIT`, ist alles da.

Freiwillig:

- Mit einer NVIDIA-Grafikkarte geht das Erkennen der Sprache viel schneller:
  `python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`. Ohne rechnet der Prozessor — geht auch, dauert länger.
- Für „Grafik über dem Video“ (Karten, Einblendungen) braucht es zusätzlich Node ab Version 22
  (`winget install --id OpenJS.NodeJS.LTS -e`) und Edge oder Chrome.
- Probelauf mit dem beiliegenden Testvideo: `einrichten.cmd -Selbsttest` (1 bis 5 Minuten, am Ende „23 von 23“).

## Ein Video schneiden

**Mit Claude** (so ist es gedacht): Claude Code in diesem Ordner öffnen und einfach sagen:

> Schneid das Video "D:\Videos\mein-video.mp4" im Stil reel.

Claude transkribiert, liest den Schnittplan gegen (Versprecher, verhörte Namen), setzt Schlagzeilen und rendert.
Soll Claude den Skill in jedem Ordner kennen, nicht nur hier: `einrichten.cmd -SkillGlobal`.

**Ohne Claude** geht es auch — in einem PowerShell-Fenster in diesem Ordner:

```
python videoschnitt\schnitt.py alles "D:\Videos\mein-video.mp4" --stil reel
```

Das fertige Video liegt danach neben dem Rohvideo als `mein-video-geschnitten.mp4`; der genaue Pfad steht in der
Zeile `FERTIG`. Daneben entsteht ein Arbeitsordner `mein-video.schnitt\` mit Transkript, Schnittplan und Untertiteln.

Die Stile:

| Stil | Format | Kurz |
|---|---|---|
| `reel` | wie gefilmt | dicht geschnitten, Untertitel bauen sich Wort für Wort auf, Zahlen betont, Zoom-Wechsel, Balken |
| `schnell` | macht 9:16 | harte Schnitte, auch weiche Füllwörter raus, zwei Wörter groß im Bild |
| `standard` | wie gefilmt | Pausen und Füllwörter raus, große Untertitel mit gelbem Wort |
| `ruhig` | wie gefilmt | lässt Atempausen stehen, dezente Untertitel |
| `magi` | wie gefilmt | wie reel ohne Zoom und Balken — für Grafik-Videos |

Mehr Kontrolle (Plan lesen, Stellen von Hand rausnehmen, Schlagzeilen, eigener Stil):
`python videoschnitt\schnitt.py --help` und die ausführliche `videoschnitt\README.md`.

## Die ArtCraft-Programme

Freie Open-Source-Programme vom ArtCraft-Team (Lizenz MIT oder Apache 2.0, liegt jeweils im Ordner; signiert von
„Learning Machines Inc“). Nichts zu installieren: die `.exe` im jeweiligen Ordner starten — oder die Verknüpfungen,
die `einrichten.cmd` in `artcraft\` anlegt.

| Programm | Wofür | Starten |
|---|---|---|
| FilmCraft | Videoschnitt, Farbe, Ton (bedient sich wie Premiere) | `artcraft\filmcraft\filmcraft.exe` |
| EffectCraft | Bewegungsgrafik und Effekte | `artcraft\effectcraft\effectcraft.exe` |
| PhotoCraft | Bildbearbeitung mit Ebenen und Masken, liest PSD | `artcraft\photocraft\photocraft.exe` |
| LightCraft | Fotos verwalten und RAW entwickeln | `artcraft\lightcraft\lightcraft.exe` |
| VectorCraft | Vektorgrafik | `artcraft\vectorcraft\vectorcraft.exe` |

- Zu jedem Programm gibt es eine `…-cli.exe` für die Kommandozeile (`--help` zeigt die Befehle). Darüber kann auch
  Claude die Programme bedienen.
- FilmCraft und PhotoCraft sind „portabel“ eingestellt (`portable.txt` liegt bei): Einstellungen landen im Ordner
  neben der `.exe` und reisen mit.
- Die Programme sind jung (Alpha). Öffnet sich eines nicht: Hinweise stehen unter „Downloads“ in der jeweiligen
  `README.md`. Neuere Fassungen: https://getartcraft.com/apps
- Beim ersten Start fragt Windows eventuell nach, weil die Dateien von einem anderen Rechner kommen.

## Was nicht drin ist

- Keine Schlüssel, keine Anmeldungen, keine Chats, keine privaten Notizen, keine Kundenvideos.
- MAGI selbst (der Assistent, aus dem das Werkzeug stammt) — das Werkzeug läuft ohne ihn.
- Python, ffmpeg und Node — die kommen über die Befehle oben auf den Rechner.
- Das größere Sprachmodell. `small` liegt bei und reicht zum Arbeiten, verhört sich aber bei schnellem Sprechen
  und bei Namen. Besser: `python videoschnitt\schnitt.py modell-holen large-v3-turbo --ja` (lädt ca. 1,6 GB).

## Gut zu wissen

- Aufnahmen mit Kunden nicht von Claude ansehen lassen. Wenn es sein muss: `alles --vertraulich` und das Ergebnis
  selbst prüfen.
- Bei Selfies können Untertitel auf dem Gesicht liegen — die Lage stellt man je Video im Stil ein
  (`"untertitel": {"position": 0.8}`).
- Noch nicht geprüft: gedrehte Handyvideos, schwankende Bildrate, HDR. Einzelheiten unter „Was nicht geprüft ist“
  in `videoschnitt\README.md`.
- Die `videoschnitt\README.md` stammt vom Rechner, auf dem das Werkzeug gebaut wurde. Pfade wie `Desktop\claude\…`
  und das Skript `mitnehmen\paket_bauen.ps1` gibt es in diesem Paket nicht.

## Geprüft beim Packen (2026-10-13)

Aus genau diesem Ordner heraus gestartet, auf dem Rechner, auf dem gepackt wurde:

- `schnitt.py pruefen`: BEREIT.
- Logik-Tests: 38 von 38.
- Selbsttest (Testvideo schneiden, nachmessen, noch einmal anhören): 23 von 23 — nur mit dem Modell aus dem Paket.
- Alle fünf ArtCraft-Programme: Signatur gültig, die Kommandozeilen-Fassungen antworten.
- `einrichten.cmd`: läuft durch; ohne Python im Suchpfad nennt es die fehlenden Befehle.

**Auf einem zweiten Rechner ist das Paket noch nicht gelaufen.**
