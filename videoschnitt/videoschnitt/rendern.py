"""Rendern — aus dem Schnittplan wird in einem einzigen ffmpeg-Lauf das fertige Video.

Der Filtergraph steht in einer Datei im Arbeitsordner, und ffmpeg läuft in diesem Ordner: Untertitel
und Schriften werden dann mit schlichten Namen angesprochen, und die berüchtigte Windows-Pfad-Maskierung
in ffmpeg-Filtern (Laufwerks-Doppelpunkt, Leerzeichen, Umlaute) kommt gar nicht erst vor.

Geschnitten wird in ganzen Zahlen: Bildnummern für das Bild, Abtastwerte für den Ton — beide aus
denselben Grenzen gerechnet. Gemessen an 600 Schnitten: kein Bild zu viel, Ton und Bild höchstens
3 ms auseinander. (Der naheliegende Weg über Sekunden mit halbem Bild Versatz liegt ein Bild daneben.)

Bild und Ton werden getrennt zusammengesetzt. So kann das Bild öfter wechseln als der Ton: Ein
Zoom-Wechsel mitten im Satz teilt nur das Bild, der Ton läuft ohne Naht durch.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import numpy as np

from . import klang as klangmodul
from . import ModulFehler, medien, plan as planmodul, schnittlogik as sl, stil as stilmodul, umgebung, untertitel as ut

TON_RATE = 48000
FESTE_GROESSEN = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
# HDR-Aufnahmen (iPhone: HLG, manche Android: PQ) sähen als normales H.264 flau und grau aus —
# erst in lineares Licht, Helligkeit zusammenstauchen, dann zurück nach BT.709.
HDR_KETTE = ("zscale=transfer=linear:npl=100,format=gbrpf32le,zscale=primaries=bt709,"
             "tonemap=tonemap=hable:desat=0,zscale=transfer=bt709:matrix=bt709:range=tv,format=yuv420p")
ZOOM_RUHE = 1.2      # Sekunden, die eine Einstellung mindestens steht, bevor das Bild wieder wechselt


class RenderFehler(ModulFehler):
    pass


def ziel_waehlen(video: Path, ausgabe: str | None, probe: bool, ueberschreiben: bool = False) -> Path:
    """Wohin das Ergebnis kommt. Das Rohvideo wird nie überschrieben, ein älteres Ergebnis nur auf Ansage."""
    if ausgabe:
        ziel = Path(ausgabe).expanduser().resolve()
        if ziel.suffix.lower() != ".mp4":
            ziel = ziel.with_suffix(".mp4")
        if ziel == video.resolve():
            raise RenderFehler("Das Ergebnis darf nicht das Rohvideo überschreiben.")
        if not ziel.parent.is_dir():
            raise RenderFehler(f"Den Zielordner gibt es nicht: {ziel.parent}")
        if ziel.exists() and not ueberschreiben:
            raise RenderFehler(f"Die Zieldatei gibt es schon: {ziel}. Anderen Namen nehmen oder --ueberschreiben dazusetzen.")
        return ziel
    if probe:
        return video.with_name(video.stem + "-probe.mp4")     # die Probe ist zum Wegwerfen und wird jedes Mal ersetzt
    ziel = video.with_name(video.stem + "-geschnitten.mp4")
    nr = 2
    while ziel.exists():
        ziel = video.with_name(f"{video.stem}-geschnitten-{nr}.mp4")
        nr += 1
    return ziel


def _gerade(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def bildgroesse(info: dict, opt: dict) -> tuple[int, int]:
    """Breite und Höhe des Ergebnisses."""
    if opt["format"] == "original":
        w, h = info["breite"], info["hoehe"]
    else:
        w, h = FESTE_GROESSEN[opt["format"]]
    lang = max(w, h)
    if lang > opt["kante_max"]:
        w, h = w * opt["kante_max"] / lang, h * opt["kante_max"] / lang
    return _gerade(w), _gerade(h)


def _bild_vorstufe(info: dict, opt: dict, fps: Fraction, w: int, h: int) -> list[str]:
    """Vom Rohbild zum fertigen Format: feste Bildrate, HDR, Zuschnitt, Größe. Ergebnis heißt [vbasis]."""
    kette = [f"fps={fps.numerator}/{fps.denominator}:start_time=0"]
    if info.get("hdr"):
        kette.append(HDR_KETTE)
    anfang = "[0:v:0]" + ",".join(kette)
    if opt["format"] != "original" and opt["anpassen"] == "einpassen":
        return [
            f"{anfang},split=2[vhin0][vvor0]",
            f"[vhin0]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"scale={_gerade(w / 4)}:{_gerade(h / 4)},gblur=sigma=10,scale={w}:{h}[vhin]",
            f"[vvor0]scale={w}:{h}:force_original_aspect_ratio=decrease[vvor]",
            "[vhin][vvor]overlay=(W-w)/2:(H-h)/2,setsar=1[vbasis]",
        ]
    # „increase“ füllt das Zielformat ganz, der Überstand wird mittig abgeschnitten.
    return [f"{anfang},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1[vbasis]"]


def bildstuecke(plan: dict, segmente: list[dict]) -> list[dict]:
    """Die Einstellungen des Bildes: jedes Stück mit ``nah`` (herangezoomt oder nicht).

    Ein fester Bildausschnitt über viele Sekunden lässt Zuschauer abspringen. Deshalb wechselt das Bild
    zwischen „normal“ und „etwas näher“ — an jedem Schnitt, und wenn lange keiner kommt (``zoom_takt``),
    am nächsten Satzanfang. Nie öfter als alle ``ZOOM_RUHE`` Sekunden, sonst wird es unruhig.
    """
    fps = Fraction(plan["bildrate"])
    b = plan["stil"]["bild"]
    faktor = float(b.get("zoom_bei_schnitt") or 0)
    if faktor <= 1:
        return [{"k": s["k"], "m": s["m"], "nah": False} for s in segmente]
    takt = round(float(b.get("zoom_takt") or 0) * fps)
    ruhe = round(ZOOM_RUHE * fps)
    bleibt = [w for w in plan["woerter"] if not w.get("weg")]
    wortanfang = sorted({round(w["von"] * fps) for w in bleibt})
    satzanfang = sorted({round(w["von"] * fps) for vor, w in zip([None] + bleibt, bleibt)
                         if vor is None or sl.satzende(vor["w"])})

    stuecke: list[dict] = []
    nah, seit = False, 0
    for nr, s in enumerate(segmente):
        if nr > 0 and seit >= ruhe:
            nah, seit = not nah, 0
        pos = s["k"]
        while takt:
            # Der nächste Satzanfang, an dem die Einstellung lange genug stand; notfalls ein Wortanfang,
            # wenn jemand sehr lange ohne Punkt redet.
            wechsel = next((f for f in satzanfang if pos < f < s["m"] and seit + f - pos >= takt), None) \
                or next((f for f in wortanfang if pos < f < s["m"] and seit + f - pos >= 1.6 * takt), None)
            if wechsel is None or s["m"] - wechsel < ruhe // 2:
                break
            stuecke.append({"k": pos, "m": wechsel, "nah": nah})
            nah, seit, pos = not nah, 0, wechsel
        stuecke.append({"k": pos, "m": s["m"], "nah": nah})
        seit += s["m"] - pos
    return stuecke


def raumklang_kette(staerke: float, huelle: medien.Huelle | None) -> str:
    """Filter, die den Raum aus der Stimme nehmen — so weit das ohne gelerntes Modell geht.

    Was sie tun: Rumpeln unter 90 Hz weg, gleichmäßiges Rauschen dämpfen, das Topfige um 300 Hz
    absenken, die Sprachverständlichkeit um 4 kHz anheben und alles, was zwischen den Wörtern nachklingt,
    leiser ziehen. Was sie nicht können: den Hall *unter* der laufenden Stimme entfernen — dafür braucht
    es ein gelerntes Modell (z. B. DeepFilterNet), das nur mit Chefs Ja geladen würde.
    """
    r = min(1.0, max(0.0, staerke))
    # Rauschboden und Sprach-Schwelle dieser Aufnahme (aus der Hüllkurve) statt fester Zahlen
    boden = min(-20.0, max(-80.0, float(np.percentile(huelle.db, 10)) if huelle is not None and huelle.db.size else -50.0))
    schwelle = 10 ** (((huelle.schwelle if huelle is not None else -45.0) + 4.0) / 20)
    return ",".join([
        "highpass=f=90",
        f"afftdn=nr={6 + 8 * r:.0f}:nf={boden:.0f}:tn=1",
        f"agate=threshold={schwelle:.5f}:ratio=2:range={10 ** (-(4 + 8 * r) / 20):.3f}:attack=3:release=120:knee=4:detection=rms",
        f"equalizer=f=320:t=q:w=1.1:g={-(1.5 + 2.5 * r):.1f}",
        f"equalizer=f=3800:t=q:w=1.4:g={1 + 2 * r:.1f}",
    ])


def _ton_zeilen(plan: dict, segmente: list[dict], huelle: medien.Huelle | None) -> list[str]:
    """Der Ton-Teil des Graphen bis [aroh]: schneiden, zusammensetzen, Raumklang dämpfen — noch ohne Lautheit."""
    fps = Fraction(plan["bildrate"])
    s = plan["stil"]
    blende = Fraction(int(s["ton"]["blende_ms"]), 1000)
    n = len(segmente)
    zeilen = [f"[0:a:0]aresample={TON_RATE}:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,"
              f"asplit={n}" + "".join(f"[a{i}]" for i in range(n))]
    for i, seg in enumerate(segmente):
        von, bis = round(Fraction(seg["k"]) / fps * TON_RATE), round(Fraction(seg["m"]) / fps * TON_RATE)
        dauer = Fraction(bis - von, TON_RATE)
        f = min(blende, dauer / 4)
        ton = f"[a{i}]atrim=start_pts={von}:end_pts={bis},asetpts=PTS-STARTPTS"
        if f > 0:
            ton += f",afade=t=in:st=0:d={float(f):.6f},afade=t=out:st={float(dauer - f):.6f}:d={float(f):.6f}"
        zeilen.append(ton + f"[at{i}]")
    raum = float(s["ton"].get("raumklang") or 0)
    zeilen.append("".join(f"[at{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1"
                  + ("," + raumklang_kette(raum, huelle) if raum > 0 else "") + "[aroh]")
    return zeilen


def lautheit_messen(plan: dict, segmente: list[dict], ordner: Path, huelle: medien.Huelle | None) -> dict | None:
    """Wie laut der geschnittene Ton ist (LUFS und Spitze) — ein schneller Lauf nur über den Ton.

    Damit wird danach fest angehoben. Die mitlaufende Regelung von ``loudnorm`` in einem Durchgang zieht
    leise Stellen hoch, also auch das Rauschen in den Pausen (gemessen: Abstand Sprache zu Pause von
    48 auf 32 dB) — genau das Gegenteil von dem, was der Raumklang-Filter soll.
    """
    graph = ";\n".join(_ton_zeilen(plan, segmente, huelle) + ["[aroh]loudnorm=print_format=json[amess]"]) + "\n"
    (ordner / "filter-ton.txt").write_text(graph, encoding="utf-8", newline="\n")
    lauf = subprocess.run([umgebung.ffmpeg(), "-hide_banner", "-v", "info", "-nostats", "-i", plan["quelle"],
                           "-/filter_complex", "filter-ton.txt", "-map", "[amess]", "-f", "null", "-"],
                          cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace")
    anfang = lauf.stderr.rfind('{\n\t"input_i"')
    if lauf.returncode != 0 or anfang < 0:
        return None
    try:
        werte = json.loads(lauf.stderr[anfang:lauf.stderr.index("}", anfang) + 1])
        return {"lufs": float(werte["input_i"]), "spitze": float(werte["input_tp"])}
    except (ValueError, KeyError):
        return None


def graph_bauen(plan: dict, segmente: list[dict], w: int, h: int, mit_ass: bool, schriften: bool,
                huelle: medien.Huelle | None = None, laut: dict | None = None,
                klaenge: bool = False, grafik: bool = False) -> tuple[str, list[dict]]:
    """Der ganze Filtergraph als Text, dazu die Bildstücke (fürs Protokoll).

    Mit ``klaenge`` ist die zweite Eingabe die Spur der Effekt-Klänge: Sie kommt *nach* dem Einpegeln der
    Stimme dazu und *vor* dem Begrenzer, damit die Summe nie übersteuert. Mit ``grafik`` ist die letzte Eingabe
    die abgelichtete Bewegungsgrafik (durchsichtig, so lang wie das Ergebnis): Sie liegt über dem Bild und
    unter den Untertiteln.
    """
    fps = Fraction(plan["bildrate"])
    s = plan["stil"]
    zoom = float(s["bild"].get("zoom_bei_schnitt") or 0)
    mitte_y = min(1.0, max(0.0, float(s["bild"].get("zoom_mitte_y", 0.5))))
    bild = bildstuecke(plan, segmente)

    zeilen = _bild_vorstufe(plan["auskunft"], s["bild"], fps, w, h)
    zeilen.append(f"[vbasis]split={len(bild)}" + "".join(f"[v{i}]" for i in range(len(bild))))
    for i, st in enumerate(bild):
        zeile = f"[v{i}]trim=start_pts={st['k']}:end_pts={st['m']},setpts=PTS-STARTPTS"
        if st["nah"]:
            # setsar: Beim Vergrößern auf gerade Zahlen verrutscht das Seitenverhältnis um ein Haar, und
            # concat verweigert Stücke, deren Pixelform nicht genau gleich ist.
            zeile += (f",scale={_gerade(w * zoom)}:{_gerade(h * zoom)}:flags=bicubic,"
                      f"crop={w}:{h}:(iw-{w})/2:(ih-{h})*{mitte_y:.3f},setsar=1")
        zeilen.append(zeile + f"[vt{i}]")
    zeilen.append("".join(f"[vt{i}]" for i in range(len(bild))) + f"concat=n={len(bild)}:v=1:a=0[vc]")

    zeilen += _ton_zeilen(plan, segmente, huelle)

    ende = []
    if mit_ass:
        ende.append("subtitles=f=untertitel.ass" + (":fontsdir=schriften" if schriften else ""))
    ende.append("format=yuv420p")
    bild_aus = "[vc]"
    if grafik:
        zeilen.append(f"[{2 if klaenge else 1}:v:0]scale={w}:{h}:flags=bicubic,format=argb[vgraf]")
        zeilen.append("[vc][vgraf]overlay=0:0:format=auto:eof_action=pass[vmit]")
        bild_aus = "[vmit]"
    zeilen.append(bild_aus + ",".join(ende) + "[vout]")

    if s["ton"]["lautheit"] and laut and laut["lufs"] > -70:
        # Fest anheben auf das Ziel. Reicht der Platz nach oben nicht, darf der Begrenzer die Spitzen um
        # höchstens 4 dB stauchen — mehr würde man hören; dann bleibt es lieber etwas leiser.
        hub = min(float(s["ton"]["ziel_lufs"]) - laut["lufs"], -1.0 - laut["spitze"] + 4.0)
        stimme, begrenzen = f"[aroh]volume={hub:.2f}dB", True
    else:
        stimme, begrenzen = "[aroh]anull", False
    if klaenge:
        zeilen.append(f"[1:a:0]aresample={TON_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo[aklang]")
        zeilen.append(stimme + "[astimme]")
        stimme, begrenzen = "[astimme][aklang]amix=inputs=2:normalize=0:duration=first:dropout_transition=0", True
    if begrenzen:
        stimme += f",alimiter=limit={10 ** (-1.0 / 20):.3f}:level=disabled,aresample={TON_RATE}"
    zeilen.append(stimme + "[aout]")
    return ";\n".join(zeilen) + "\n", bild


def _encoder(opt: dict) -> tuple[str, list[str]]:
    wahl = opt["encoder"]
    q = str(int(opt["qualitaet"]))
    if wahl == "nvenc" and not umgebung.nvenc_geht():
        raise RenderFehler("Der Stil verlangt ausgabe.encoder = nvenc, aber die Grafikkarte kodiert hier nicht. "
                           "Im Stil auf \"auto\" stellen.")
    if wahl == "nvenc" or (wahl == "auto" and umgebung.nvenc_geht()):
        return "h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", q, "-b:v", "0",
                              "-profile:v", "high", "-pix_fmt", "yuv420p"]
    return "libx264", ["-c:v", "libx264", "-preset", "medium", "-crf", q, "-profile:v", "high", "-pix_fmt", "yuv420p"]


def _kuerzen(segmente: list[dict], sekunden: float, fps: Fraction) -> list[dict]:
    """Für die Probe: nur so viele Stücke, bis die gewünschte Länge erreicht ist."""
    aus, rest = [], max(2, round(sekunden * fps))
    for s in segmente:
        if rest <= 0:
            break
        m = min(s["m"], s["k"] + rest)
        aus.append({"k": s["k"], "m": m, "von": float(s["k"] / fps), "bis": float(m / fps)})
        rest -= m - s["k"]
    return aus


def standbilder(ziel: Path, ordner: Path, zeiten: list[float]) -> list[dict]:
    """Ein paar Bilder aus dem Ergebnis in den Arbeitsordner legen — zum Ansehen mit Read."""
    aus = []
    for nr, t in enumerate(zeiten, 1):
        datei = ordner / f"blick-{nr}.png"
        lauf = subprocess.run([umgebung.ffmpeg(), "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(ziel), "-frames:v", "1",
                               "-update", "1", "-vf", "scale=-2:'min(960,ih)'", str(datei)], capture_output=True)
        if lauf.returncode == 0 and datei.is_file():
            aus.append({"datei": str(datei), "sekunde": round(t, 1)})
    return aus


def rendern(plan: dict, ordner: Path, ziel: Path, untertitel: bool = True, probe: float | None = None, melden=None,
            bilder: int = 0, klaenge: list[dict] | None = None, grafik: Path | None = None) -> dict:
    """Das Video bauen und danach nachmessen. Liefert die Zahlen; ``ok`` nur, wenn die Messung stimmt."""
    fps = Fraction(plan["bildrate"])
    s = plan["stil"]
    segmente = _kuerzen(plan["segmente"], probe, fps) if probe else plan["segmente"]
    if not segmente:
        raise RenderFehler("Der Schnittplan hat keine Stücke.")
    w, h = bildgroesse(plan["auskunft"], s["bild"])
    bilder_gesamt = sum(x["m"] - x["k"] for x in segmente)
    erwartet = float(Fraction(bilder_gesamt) / fps)
    quelle = Path(plan["quelle"])

    u, bindung = s["untertitel"], s.get("bindung", {})
    mit_ut = untertitel and bool(u["an"])
    schlagzeilen = plan.get("schlagzeilen", []) if untertitel else []
    balken = untertitel and bool(bindung.get("fortschritt"))
    mit_ass = mit_ut or bool(schlagzeilen) or balken
    ut_info: dict = {}
    schriften = False
    if mit_ass:
        hell = hell_oben = None
        if u.get("kontrast") == "auto":
            lage = u.get("position_quer") if w > h and u.get("position_quer") else u["position"]
            hell = medien.helligkeit_messen(quelle, float(lage)) if mit_ut else None
            hell_oben = medien.helligkeit_messen(quelle, 0.15) if schlagzeilen else None
        text, ut_info = ut.ass_bauen(plan["woerter"], segmente, {**u, "an": mit_ut}, w, h, fps, hell, hell_oben,
                                     schlagzeilen, bindung if balken else None)
        (ordner / "untertitel.ass").write_text(text, encoding="utf-8", newline="\n")
        (ordner / "untertitel.srt").write_text(ut.srt_bauen(plan["woerter"], segmente, u, fps), encoding="utf-8", newline="\n")
        eigene = u.get("schrift_datei")
        if eigene:
            datei = Path(eigene) if Path(eigene).is_absolute() else stilmodul.STILE_ORDNER / eigene
            if not datei.is_file():
                raise RenderFehler(f"Die Schriftdatei aus dem Stil gibt es nicht: {datei}")
            (ordner / "schriften").mkdir(exist_ok=True)
            shutil.copy2(datei, ordner / "schriften" / datei.name)
            schriften = True

    wav = ordner / "ton.wav"
    huelle = medien.Huelle.aus_wav(wav) if wav.is_file() else None
    laut = lautheit_messen(plan, segmente, ordner, huelle) if s["ton"]["lautheit"] else None
    # Klänge zu den Bildeffekten: die mitgegebenen (Zeiten im fertigen Video) und, wenn der Stil es will,
    # ein leiser Luftzug zu jeder Schlagzeile. Ohne Bildeffekt kein Klang.
    effekte = float(s["ton"].get("effekte") or 0)
    toene = [dict(k) for k in (klaenge or [])]
    if effekte > 0:
        toene += [{"zeit": max(0.0, b / float(fps) - 0.12), "art": "wusch", "staerke": 0.8}
                  for b in ut_info.get("schlagzeilen_bilder", [])]
    toene = sorted((k for k in toene if k["zeit"] < erwartet), key=lambda k: k["zeit"])
    if toene:
        klangmodul.schreiben(ordner / "klaenge.wav", klangmodul.spur(toene, erwartet, effekte if effekte > 0 else 1.0))
    graph, bild = graph_bauen(plan, segmente, w, h, mit_ass, schriften, huelle, laut, bool(toene), grafik is not None)
    (ordner / "filter.txt").write_text(graph, encoding="utf-8", newline="\n")

    teil = ziel.with_name(ziel.stem + ".teil.mp4")
    name, kodierung = _encoder(s["ausgabe"])
    versuche = [(name, kodierung)]
    if name == "h264_nvenc" and s["ausgabe"]["encoder"] == "auto" and umgebung.hat_encoder("libx264"):
        versuche.append(_encoder({**s["ausgabe"], "encoder": "x264"}))

    fehler = ""
    for name, kodierung in versuche:
        # Stufe „info“, weil libass nur dort sagt, welche Schrift es wirklich genommen hat.
        befehl = [umgebung.ffmpeg(), "-hide_banner", "-y", "-v", "info", "-nostats", "-progress", "pipe:1",
                  "-i", str(quelle), *(["-i", "klaenge.wav"] if toene else []), *(["-i", str(grafik)] if grafik else []),
                  "-/filter_complex", "filter.txt", "-map", "[vout]", "-map", "[aout]",
                  *kodierung, "-c:a", "aac", "-b:a", f"{int(s['ausgabe']['ton_kbit'])}k", "-ar", str(TON_RATE),
                  "-movflags", "+faststart", str(teil)]
        with open(ordner / "ffmpeg-log.txt", "w", encoding="utf-8", errors="replace") as log:
            log.write(" ".join(f'"{b}"' if " " in b else b for b in befehl) + "\n\n")
            log.flush()
            lauf = subprocess.Popen(befehl, cwd=ordner, stdout=subprocess.PIPE, stderr=log, text=True,
                                    encoding="utf-8", errors="replace")
            for zeile in lauf.stdout:
                schluessel, _, wert = zeile.strip().partition("=")
                if melden and schluessel in ("out_time_us", "out_time_ms") and wert.lstrip("-").isdigit() and erwartet > 0:
                    melden(min(1.0, int(wert) / 1_000_000 / erwartet))
            code = lauf.wait()
        if code == 0 and teil.is_file() and teil.stat().st_size > 0:
            fehler = ""
            break
        zeilen = (ordner / "ffmpeg-log.txt").read_text(encoding="utf-8", errors="replace").split("\n\n", 1)[-1].splitlines()
        wichtig = [z for z in zeilen if any(x in z.lower() for x in ("error", "invalid", "failed", "unable", "no such", "cannot"))]
        fehler = "\n".join((wichtig or zeilen)[-8:])[-900:]
        teil.unlink(missing_ok=True)
    if fehler or not teil.is_file():
        raise RenderFehler(f"ffmpeg ist gescheitert ({name}). Letzte Zeilen:\n{fehler}\nGanzes Protokoll: {ordner / 'ffmpeg-log.txt'}")

    teil.replace(ziel)
    if mit_ass:
        protokoll = (ordner / "ffmpeg-log.txt").read_text(encoding="utf-8", errors="replace")
        ut_info.update(ut.schrift_aus_protokoll(protokoll, u["schrift"]))
    ergebnis = nachmessen(ziel, erwartet, w, h, fps)
    ergebnis.update({
        "encoder": name, "untertitel": ut_info if mit_ass else None, "probe": bool(probe), "stuecke": len(segmente),
        "bildwechsel": sum(1 for a, b in zip(bild, bild[1:]) if a["nah"] != b["nah"]),
        "raumklang": float(s["ton"].get("raumklang") or 0),
        "lautheit_vorher": laut["lufs"] if laut else None,
        "klaenge": len(toene), "grafik": grafik is not None,
    })
    if bilder and ut_info:
        zeiten = [ut_info[k] / float(fps) + 0.25 for k in ("erste", "breiteste", "letzte") if ut_info.get(k) is not None]
        ergebnis["standbilder"] = standbilder(ziel, ordner, sorted(set(round(t, 1) for t in zeiten))[:bilder])
    elif bilder:
        ergebnis["standbilder"] = standbilder(ziel, ordner, [erwartet * (k + 0.5) / bilder for k in range(bilder)])
    return ergebnis


def nachmessen(ziel: Path, erwartet: float, w: int, h: int, fps: Fraction) -> dict:
    """Das Ergebnis ansehen — nicht der Erfolgsmeldung von ffmpeg glauben.

    Gezählt wird, was wirklich abgespielt wird: die Bilder der Bildspur und die dekodierten Abtastwerte
    des Tons. Die Dauer, die im Dateikopf steht, taugt dafür nicht — bei AAC neben B-Bildern nennt sie
    den Ton bis zu 70 ms länger, als er ist.
    """
    lauf = subprocess.run(
        [umgebung.ffprobe(), "-v", "error", "-count_packets", "-print_format", "json", "-show_streams", str(ziel)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if lauf.returncode != 0:
        raise RenderFehler(f"Das Ergebnis lässt sich nicht lesen: {lauf.stderr.strip()[:300]}")
    stroeme = json.loads(lauf.stdout).get("streams", [])
    bild = next((x for x in stroeme if x.get("codec_type") == "video"), {})
    ton = next((x for x in stroeme if x.get("codec_type") == "audio"), {})
    bilder = int(bild.get("nb_read_packets") or 0)
    dauer_bild = float(Fraction(bilder) / fps)

    proben = 0
    if ton:
        dekoder = subprocess.Popen([umgebung.ffmpeg(), "-v", "error", "-i", str(ziel), "-map", "0:a:0", "-ac", "1",
                                    "-ar", str(TON_RATE), "-f", "s16le", "-"], stdout=subprocess.PIPE)
        while True:
            stueck = dekoder.stdout.read(1 << 20)
            if not stueck:
                break
            proben += len(stueck) // 2
        dekoder.wait()
    dauer_ton = proben / TON_RATE

    pruefungen = {
        "bildspur_da": bool(bild),
        "tonspur_da": bool(ton),
        "groesse_stimmt": (bild.get("width"), bild.get("height")) == (w, h),
        "laenge_aufs_bild_genau": bilder == round(erwartet * fps),
        # Der Ton endet auf ein volles AAC-Paket (rund 21 ms) genau.
        "bild_und_ton_gleich_lang": abs(dauer_bild - dauer_ton) <= 0.03,
    }
    return {
        "ok": all(pruefungen.values()),
        "pruefungen": pruefungen,
        "datei": str(ziel),
        "bytes": ziel.stat().st_size,
        "breite": bild.get("width"),
        "hoehe": bild.get("height"),
        "bildrate": bild.get("avg_frame_rate"),
        "bilder": bilder,
        "dauer_erwartet": round(erwartet, 3),
        "dauer_bild": round(dauer_bild, 3),
        "dauer_ton": round(dauer_ton, 3),
        "bild_codec": bild.get("codec_name"),
        "ton_codec": ton.get("codec_name"),
    }


def meldung(plan: dict, e: dict) -> list[str]:
    """Das Ergebnis in wenigen Zeilen für den Chat — Zahlen, kein Wortlaut."""
    uhr = planmodul.uhr
    u = e.get("untertitel") or {}
    fassung = Path(e["datei"]).stem.rsplit("-geschnitten-", 1)
    zeilen = [
        f"{'PROBE ' if e['probe'] else 'FERTIG'}    {e['datei']}"
        + (f"   (Fassung {fassung[1]} — die älteren liegen daneben)" if len(fassung) == 2 and fassung[1].isdigit() else "")
        + ("   (die Probe wird jedes Mal ersetzt)" if e["probe"] else ""),
        f"GEMESSEN  {uhr(e['dauer_bild'])} (geplant {uhr(e['dauer_erwartet'])}) · {e['breite']}×{e['hoehe']} · "
        f"Bild/Ton-Länge {abs(e['dauer_bild'] - e['dauer_ton']) * 1000:.0f} ms auseinander · "
        f"{e['bytes'] / 1_048_576:.1f} MB".replace(".", ","),
        f"GERECHNET {e['sekunden']:.1f} s ({e['dauer_bild'] / max(e['sekunden'], 0.1):.1f}× Echtzeit) · {e['encoder']}"
        .replace(".", ",") + (f" · Untertitel: {u['gruppen']} Gruppen, Schrift {', '.join(u.get('genommen') or [u['schrift']])}"
                              + (f", {u['kleinste_groesse']} statt {u['groesse']} bei der längsten Zeile"
                                 if u["kleinste_groesse"] < u["groesse"] else "")
                              if u.get("gruppen") else " · ohne Untertitel"),
    ]
    bindung = []
    if e.get("bildwechsel"):
        bindung.append(f"{e['bildwechsel']} Zoom-Wechsel")
    if u.get("betonte_woerter"):
        bindung.append(f"{u['betonte_woerter']} betonte Wörter")
    if u.get("schlagzeilen"):
        bindung.append(f"{u['schlagzeilen']} Schlagzeile(n)")
    if u.get("fortschrittsbalken"):
        bindung.append("Fortschrittsbalken")
    if e.get("raumklang"):
        bindung.append(f"Raumklang gedämpft (Stärke {e['raumklang']:g})".replace(".", ","))
    if bindung:
        zeilen.append("DAZU      " + " · ".join(bindung))
    if e.get("standbilder"):
        zeilen.append(f"BILDER    {len(e['standbilder'])} im Arbeitsordner: "
                      + ", ".join(f"{Path(b['datei']).name} ({uhr(b['sekunde'])})" for b in e["standbilder"]))
    if u and not u.get("breite_gemessen", True):
        zeilen.append("HINWEIS   Die Schrift ließ sich nicht ausmessen — die Zeilenbreite ist geschätzt. Ein Bild ansehen.")
    if u.get("ersetzt"):
        zeilen.append(f"ACHTUNG   Die Schrift „{u['schrift']}“ wurde nicht gefunden — im Bild steht {', '.join(u['ersetzt'])}. "
                      "Im Stil den Familiennamen genau so schreiben, wie Windows ihn zeigt, oder schrift_datei setzen.")
    if u.get("zeichen_fehlen"):
        zeilen.append(f"ACHTUNG   {len(u['zeichen_fehlen'])} Zeichen fehlen in der Schrift und wurden aus einer anderen genommen "
                      f"({', '.join(u['zeichen_fehlen'][:5])}).")
    if not e["ok"]:
        zeilen.append("NICHT IN ORDNUNG: " + ", ".join(k for k, v in e["pruefungen"].items() if not v))
    return zeilen


def bericht_schreiben(plan: dict, e: dict, ordner: Path) -> None:
    """``bericht.md`` im Arbeitsordner: was gemacht wurde, mit allen Zahlen. Kein Wortlaut aus dem Video."""
    st = plan["statistik"]
    zeilen = [
        f"# Schnittbericht — {Path(plan['quelle']).name}",
        "",
        f"Erstellt am {datetime.now():%Y-%m-%d %H:%M} mit dem Stil **{plan['stil']['name']}**"
        + (" (Probe, nicht das ganze Video)" if e["probe"] else "") + ".",
        "",
        "| | |",
        "|---|---|",
        f"| Rohvideo | {planmodul.uhr(st['dauer_roh'])} · {plan['auskunft']['breite']}×{plan['auskunft']['hoehe']} |",
        f"| Ergebnis | {planmodul.uhr(e['dauer_bild'])} · {e['breite']}×{e['hoehe']} · {e['bytes'] / 1_048_576:.1f} MB |",
        f"| Gekürzt um | {st['gekuerzt']:.1f} s in {st['segmente']} Stücken |",
        f"| Erkannt | {st['woerter']} Wörter, davon bleiben {st['woerter_bleiben']} |",
        f"| Transkription | Modell {plan['transkription']['modell']} auf {plan['transkription']['geraet']}, "
        f"{plan['transkription']['sekunden_rechnen']} s |",
        f"| Rendern | {e['sekunden']} s mit {e['encoder']} |",
        "",
        "## Was rausgeflogen ist",
        "",
        "| Grund | Sekunden | Stellen | Wörter |",
        "|---|---|---|---|",
    ]
    for g, name in planmodul.GRUND_TEXT.items():
        sek, stk, stellen = st["sekunden"].get(g, 0), st["stueck"].get(g), st.get("stellen", {}).get(g)
        if sek >= 0.05 or stk:
            zeilen.append(f"| {name} | {sek:.1f} | {stellen if stellen is not None else (stk if g == 'pause' else '–')} | "
                          f"{stk if stk is not None and g != 'pause' else '–'} |")
    offen = [k for k in plan["kandidaten"] if not k["angewandt"] and not k.get("entschieden")]
    zeilen += ["", f"Unsichere Stellen, die niemand entschieden hat: {len(offen)}"
               + (" (siehe `schnittplan.txt`)" if offen and not plan.get("vertraulich") else ""), "", "## Nachgemessen", ""]
    zeilen += [f"- {'ja  ' if v else 'NEIN'} {k.replace('_', ' ')}" for k, v in e["pruefungen"].items()]
    zeilen += ["", f"Ergebnis: `{e['datei']}`", ""]
    (ordner / "bericht.md").write_text("\n".join(zeilen), encoding="utf-8", newline="\n")
