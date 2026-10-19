"""Umgebung — findet ffmpeg, bereitet die Grafikkarte vor und prüft, ob alles da ist.

Nichts hier lädt etwas aus dem Netz. Fehlt etwas, sagt ``pruefen`` es mit dem Befehl, der es behebt.
"""
from __future__ import annotations

import functools
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import ModulFehler

MODELL_ORDNER = Path.home() / ".cache" / "huggingface" / "hub"
MODELLE_IM_MODUL = Path(__file__).resolve().parent.parent / "modelle"
# Reihenfolge = Güte. „auto“ nimmt das erste, das schon auf dem Rechner liegt.
MODELL_VORLIEBE = ("large-v3-turbo", "large-v3", "medium", "small", "base", "tiny")
MODELL_GROESSE_MB = {"large-v3-turbo": 1600, "large-v3": 3100, "medium": 1500, "small": 480, "base": 145, "tiny": 75}


class UmgebungFehler(ModulFehler):
    pass


def _werkzeug(name: str) -> str:
    """ffmpeg/ffprobe finden: Umgebungsvariable, PATH, dann der Ordner, in den winget es legt."""
    gesetzt = os.environ.get(f"MAGI_{name.upper()}")
    if gesetzt and Path(gesetzt).is_file():
        return gesetzt
    gefunden = shutil.which(name)
    if gefunden:
        return gefunden
    lokal = os.environ.get("LOCALAPPDATA", "")
    treffer = sorted(glob.glob(os.path.join(lokal, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", f"{name}.exe")))
    if treffer:
        return treffer[-1]
    raise UmgebungFehler(f"{name} fehlt. Einmal installieren:  winget install --id Gyan.FFmpeg -e --scope user")


@functools.cache
def ffmpeg() -> str:
    return _werkzeug("ffmpeg")


@functools.cache
def ffprobe() -> str:
    return _werkzeug("ffprobe")


def _still(befehl: list[str], zeit: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=zeit)


@functools.cache
def ffmpeg_version() -> str:
    zeile = _still([ffmpeg(), "-hide_banner", "-version"]).stdout.splitlines()
    return zeile[0].split()[2] if zeile and len(zeile[0].split()) > 2 else "unbekannt"


@functools.cache
def _liste(art: str) -> str:
    return _still([ffmpeg(), "-hide_banner", f"-{art}"]).stdout


def hat_filter(name: str) -> bool:
    return any(len(z.split()) > 1 and z.split()[1] == name for z in _liste("filters").splitlines())


def hat_encoder(name: str) -> bool:
    return any(len(z.split()) > 1 and z.split()[1] == name for z in _liste("encoders").splitlines())


@functools.cache
def nvenc_geht() -> bool:
    """Kann die Grafikkarte wirklich kodieren? Dass ffmpeg den Encoder kennt, heißt das noch nicht
    (alter Treiber, keine NVIDIA-Karte) — also eine Zehntelsekunde echt kodieren."""
    # MAGI_OHNE_NVENC=1 stellt einen Rechner ohne kodierende Grafikkarte nach (Chefs Laptop) — zum Testen.
    if os.environ.get("MAGI_OHNE_NVENC") or not hat_encoder("h264_nvenc"):
        return False
    try:
        lauf = _still([ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=0.2",
                       "-c:v", "h264_nvenc", "-f", "null", "-"])
    except subprocess.TimeoutExpired:
        return False
    return lauf.returncode == 0


@functools.cache
def cuda_vorbereiten() -> tuple[str, ...]:
    """Die NVIDIA-Bibliotheken aus den pip-Paketen auffindbar machen.

    ``pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`` legt die DLLs in ``site-packages\\nvidia\\*\\bin``.
    Dort sucht Windows nicht von selbst; ohne diesen Schritt scheitert Whisper auf der Grafikkarte mit
    „cublas64_12.dll is not found“. Muss vor dem ersten Laden eines Modells laufen.
    """
    ordner: list[str] = []
    for paket in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            spec = importlib.util.find_spec(paket)
        except (ImportError, ValueError):
            spec = None
        for ort in (spec.submodule_search_locations or []) if spec else []:
            dlls = Path(ort) / "bin"
            if dlls.is_dir() and str(dlls) not in ordner:
                ordner.append(str(dlls))
    for o in ordner:
        try:
            os.add_dll_directory(o)
        except (OSError, AttributeError):
            pass
    if ordner:
        os.environ["PATH"] = os.pathsep.join(ordner) + os.pathsep + os.environ.get("PATH", "")
    return tuple(ordner)


def cuda_karten() -> int:
    """Wie viele Grafikkarten Whisper nutzen kann (0 = keine, dann rechnet der Prozessor)."""
    cuda_vorbereiten()
    try:
        import ctranslate2
        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def modell_ort(name: str) -> str | None:
    """Wo ein Whisper-Modell auf dem Rechner liegt — ohne Netz. None, wenn es fehlt."""
    if Path(name).is_dir():
        return str(Path(name).resolve())
    # Ein Modell kann auch im Modul selbst liegen (modelle\<name>\model.bin) — so reist es auf einem
    # Stick mit und braucht auf dem anderen Rechner weder Netz noch den Hugging-Face-Ordner.
    lokal = MODELLE_IM_MODUL / name
    if (lokal / "model.bin").is_file():
        return str(lokal)
    try:
        from faster_whisper.utils import download_model
        return download_model(name, local_files_only=True)
    except Exception:
        return None


def modelle_vorhanden() -> list[str]:
    return [m for m in MODELL_VORLIEBE if modell_ort(m)]


def pruefen() -> dict:
    """Alles nachsehen, was das Modul braucht. ``ok`` ist nur wahr, wenn ein Video wirklich durchliefe."""
    punkte: list[dict] = []

    def punkt(name: str, ok: bool, wert: str, hilfe: str = "", pflicht: bool = True) -> None:
        punkte.append({"name": name, "ok": bool(ok), "wert": wert, "hilfe": "" if ok else hilfe, "pflicht": pflicht})

    punkt("Python", sys.version_info >= (3, 10), sys.version.split()[0], "Python 3.10 oder neuer installieren")

    try:
        punkt("ffmpeg", True, f"{ffmpeg_version()}  ({ffmpeg()})")
        ffprobe()
        punkt("ffprobe", True, ffprobe())
        punkt("ffmpeg: Untertitel einbrennen (libass)", hat_filter("subtitles"), "Filter subtitles",
              "Ein ffmpeg mit libass nehmen, z. B. winget install --id Gyan.FFmpeg -e --scope user")
        punkt("ffmpeg: Lautheit angleichen", hat_filter("loudnorm"), "Filter loudnorm",
              "Ohne loudnorm im Stil ton.lautheit auf false stellen", pflicht=False)
        punkt("ffmpeg: H.264 (libx264)", hat_encoder("libx264"), "Encoder libx264",
              "Ein ffmpeg mit libx264 nehmen (die full-Fassung von gyan.dev hat es)", pflicht=not nvenc_geht())
        punkt("Grafikkarte kodiert (NVENC)", nvenc_geht(), "h264_nvenc",
              "Kein Fehler — dann kodiert der Prozessor mit libx264, nur langsamer", pflicht=False)
    except UmgebungFehler as e:
        punkt("ffmpeg", False, "fehlt", str(e))

    for paket, befehl in (("faster_whisper", "faster-whisper"), ("numpy", "numpy")):
        da = importlib.util.find_spec(paket) is not None
        punkt(f"Python-Paket {befehl}", da, "installiert" if da else "fehlt", f"python -m pip install {befehl}")

    if importlib.util.find_spec("faster_whisper") is not None:
        karten = cuda_karten()
        punkt("Whisper auf der Grafikkarte", karten > 0, f"{karten} Karte(n)" if karten else "nein",
              "Kein Fehler — dann rechnet der Prozessor (deutlich langsamer). Für die Grafikkarte: "
              "python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12", pflicht=False)
        da = modelle_vorhanden()
        punkt("Whisper-Modell auf dem Rechner", bool(da), ", ".join(da) if da else "keines",
              "Mit Chefs Ja laden:  python schnitt.py modell-holen small --ja   (ca. 480 MB)")
        if da and da[0] != MODELL_VORLIEBE[0]:
            bestes = MODELL_VORLIEBE[0]
            punkt(f"Bestes Modell ({bestes})", False, f"fehlt — es läuft mit {da[0]}",
                  f"Genauer bei Namen und Fachwörtern. Mit Chefs Ja laden:  python schnitt.py modell-holen {bestes} --ja   "
                  f"(ca. {MODELL_GROESSE_MB[bestes]} MB)", pflicht=False)

    return {"ok": all(p["ok"] for p in punkte if p["pflicht"]), "punkte": punkte}
