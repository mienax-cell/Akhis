"""MAGI-Modul Videoschnitt: Rohvideo → Transkript → Schnittplan → fertiges Video mit Untertiteln.

Alles läuft auf dem Rechner (faster-whisper, ffmpeg). Der Einstieg ist ``schnitt.py`` eine Ebene höher.
"""

VERSION = "0.4.0"


class ModulFehler(Exception):
    """Ein Fehler, den man beheben kann. ``schnitt.py`` meldet ihn als eine Zeile, ohne Python-Gestrüpp."""
