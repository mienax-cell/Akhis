"""Baut das Testvideo für den Selbsttest — kostenlos, ohne Netz, in ein paar Sekunden.

Die Windows-Stimme „Hedda“ spricht einen festen Text mit Füllwörtern, langen Pausen, einer Wiederholung,
einem abgebrochenen Anlauf, einem doppelten Satz und einer gewollten Anapher. Was davon wann gesagt wird,
steht auf die Millisekunde in ``testsprache.wahrheit.json`` — daran misst der Selbsttest das Ergebnis.

Das Bild ist ein Hochkant-Testbild mit laufender Zeit.

Aufruf:  python tests\\testvideo_bauen.py [Zielordner]      (Vorgabe: tests\\daten)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from videoschnitt import umgebung  # noqa: E402


def bauen(ziel: Path, breite: int = 1080, hoehe: int = 1920, fps: int = 30) -> tuple[Path, Path]:
    ziel.mkdir(parents=True, exist_ok=True)
    lauf = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(HIER / "testsprache_erzeugen.ps1"), "-Zielordner", str(ziel), "-Name", "testsprache"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    wav, wahrheit = ziel / "testsprache.wav", ziel / "testsprache.wahrheit.json"
    if lauf.returncode != 0 or not wav.is_file():
        raise SystemExit("Die Testsprache ließ sich nicht erzeugen (fehlt die Stimme „Microsoft Hedda Desktop“?):\n"
                         + (lauf.stderr or lauf.stdout)[-600:])
    video = ziel / "testvideo.mp4"
    # testsrc2 zeigt selbst eine laufende Zeit; drawtext bräuchte unter Windows eine Schriftdatei mit Pfad.
    bild = f"testsrc2=size={breite}x{hoehe}:rate={fps}"
    lauf = subprocess.run([umgebung.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", bild, "-i", str(wav),
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(video)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if lauf.returncode != 0 or not video.is_file():
        raise SystemExit("Das Testvideo ließ sich nicht bauen:\n" + lauf.stderr[-600:])
    return video, wahrheit


if __name__ == "__main__":
    v, w = bauen(Path(sys.argv[1]) if len(sys.argv) > 1 else HIER / "daten")
    print(f"Testvideo: {v}\nWahrheit:  {w}")
