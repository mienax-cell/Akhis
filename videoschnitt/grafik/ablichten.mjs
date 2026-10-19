// MAGI Videoschnitt · Grafik ablichten
//
// Eine Szene ist eine Webseite mit einer Funktion window.zeit(t): Sie stellt die Seite so hin, wie sie
// zur Sekunde t aussieht. Dieses Skript öffnet die Seite unsichtbar im Browser, der schon auf dem Rechner
// ist (Edge oder Chrome), ruft zeit(t) für jedes Bild auf und fotografiert das Ergebnis. Die Bilder gehen
// direkt an ffmpeg — heraus kommt ein Video, oder mit --durchsichtig eine Bildfolge mit durchsichtigem
// Grund zum Drüberlegen über ein gefilmtes Video.
//
// Warum so: Der Browser kann von Haus aus, was gute Bewegungsgrafik braucht — Unschärfe, Schatten,
// Farbverläufe, Raumtiefe, saubere Schrift. Und weil jedes Bild aus der Zeit gerechnet wird (nie aus
// „was gerade läuft“), kommt bei jedem Lauf dasselbe heraus, egal wie schnell der Rechner ist.
//
// Nichts wird installiert oder heruntergeladen: Node bringt alles mit (ab Version 22).
//
//   node ablichten.mjs szene.html --aus film.mp4 --dauer 12 [--breite 1080 --hoehe 1920 --fps 30]
//                                 [--daten werte.json] [--ton stimme.wav] [--durchsichtig] [--bild 3.5]
//                                 [--uhr stuecke.json] [--auskunft aus.json] [--motor motor.js]
//
//   --daten        JSON-Datei, die der Szene als window.DATEN vorliegt (Zahlen, Texte, Zeitpunkte)
//   --durchsichtig schreibt eine MOV-Datei mit durchsichtigem Grund (zum Überlagern)
//   --bild SEK     nur ein Standbild dieser Sekunde als PNG (zum Ansehen), kein Film
//   --uhr          JSON-Liste [[k, m], …] der Bilder, die ein späterer Schnitt behält. Dann zählt die Zeit der
//                  Szene nur in diesen Stücken weiter und steht dazwischen still: Nach dem Schnitt läuft die
//                  Grafik ohne Sprung durch. --dauer ist dabei die Länge der Rohfassung.
//   --auskunft     schreibt, was die Szene in window.AUSKUNFT ablegt (zum Beispiel ihre Klang-Zeitpunkte)
//   --motor        ein Skript, das vor der Seite geladen wird (grafik\motor.js: Karten und Schrift über gefilmten Videos)
//   --fps          auch als Bruch, zum Beispiel 30000/1001

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

function fehler(text) { console.error('FEHLER: ' + text); process.exit(1); }

const arg = process.argv.slice(2);
const szene = arg.find(a => !a.startsWith('--'));
const wert = (name, vorgabe) => { const i = arg.indexOf('--' + name); return i >= 0 && arg[i + 1] !== undefined ? arg[i + 1] : vorgabe; };
const schalter = name => arg.includes('--' + name);
if (!szene || !fs.existsSync(szene)) fehler('Die Szene (eine .html-Datei) fehlt oder ist nicht zu finden.');

const BREITE = +wert('breite', 1080), HOEHE = +wert('hoehe', 1920);
const FPS_TEXT = String(wert('fps', 30)), FPS = FPS_TEXT.includes('/') ? FPS_TEXT.split('/')[0] / FPS_TEXT.split('/')[1] : +FPS_TEXT;
const DAUER = +wert('dauer', 0), AUS = wert('aus', null), EINZEL = wert('bild', null);
const DURCHSICHTIG = schalter('durchsichtig'), TON = wert('ton', null), DATEN = wert('daten', null);
const AUSKUNFT = wert('auskunft', null), MOTOR = wert('motor', null);
const UHR = wert('uhr', null) ? JSON.parse(fs.readFileSync(wert('uhr', null), 'utf8')) : null;
// Wie viele behaltene Bilder vor Bild n liegen — das ist die Zeit, die die Szene zu Bild n zeigen soll.
const szenenzeit = n => UHR ? UHR.reduce((s, [k, m]) => s + Math.min(Math.max(n - k, 0), m - k), 0) / FPS : n / FPS;
if (EINZEL === null && (!AUS || !(DAUER > 0))) fehler('Es braucht --aus <datei> und --dauer <sekunden> (oder --bild <sekunde> für ein Standbild).');

const BROWSER = [
  process.env.MAGI_BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
].find(p => p && fs.existsSync(p));
if (!BROWSER) fehler('Weder Edge noch Chrome gefunden. Pfad in der Umgebungsvariable MAGI_BROWSER angeben.');

const profil = fs.mkdtempSync(path.join(os.tmpdir(), 'magi-grafik-'));
const browser = spawn(BROWSER, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profil}`,
  '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars', '--mute-audio',
  '--disable-background-networking', '--force-device-scale-factor=1', '--force-color-profile=srgb',
  `--window-size=${BREITE},${HOEHE}`, 'about:blank'], { stdio: 'ignore' });

function aufraeumen() {
  try { browser.kill(); } catch {}
  setTimeout(() => { try { fs.rmSync(profil, { recursive: true, force: true }); } catch {} }, 300);
}
process.on('exit', () => { try { browser.kill(); } catch {} });

// Der Browser schreibt die Nummer seines Steuer-Anschlusses in eine Datei im Profil (nur von diesem Rechner erreichbar).
async function anschluss() {
  const datei = path.join(profil, 'DevToolsActivePort');
  for (let i = 0; i < 200; i++) {
    if (fs.existsSync(datei)) { const zeilen = fs.readFileSync(datei, 'utf8').split('\n'); if (zeilen[0]) return +zeilen[0]; }
    await new Promise(r => setTimeout(r, 50));
  }
  fehler('Der Browser ist nicht gestartet.');
}

const port = await anschluss();
const seiten = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const seite = seiten.find(s => s.type === 'page');
const ws = new WebSocket(seite.webSocketDebuggerUrl);
await new Promise((ok, nein) => { ws.onopen = ok; ws.onerror = () => nein(new Error('keine Verbindung zum Browser')); });

let laufend = 0;
const offen = new Map(), ereignisse = new Map();
ws.onmessage = m => {
  const d = JSON.parse(m.data);
  if (d.id && offen.has(d.id)) { const [ok, nein] = offen.get(d.id); offen.delete(d.id); d.error ? nein(new Error(d.error.message)) : ok(d.result); }
  else if (d.method && ereignisse.has(d.method)) { ereignisse.get(d.method)(d.params); ereignisse.delete(d.method); }
};
const sende = (method, params = {}) => new Promise((ok, nein) => { const id = ++laufend; offen.set(id, [ok, nein]); ws.send(JSON.stringify({ id, method, params })); });
const warte = method => new Promise(ok => ereignisse.set(method, ok));
async function rechne(ausdruck) {
  const r = await sende('Runtime.evaluate', { expression: ausdruck, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error('Fehler in der Szene: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}

try {
  await sende('Page.enable');
  await sende('Emulation.setDeviceMetricsOverride', { width: BREITE, height: HOEHE, deviceScaleFactor: 1, mobile: false });
  if (DURCHSICHTIG) await sende('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
  if (DATEN) await sende('Page.addScriptToEvaluateOnNewDocument', { source: 'window.DATEN = ' + fs.readFileSync(DATEN, 'utf8') + ';' });
  if (MOTOR) await sende('Page.addScriptToEvaluateOnNewDocument', { source: fs.readFileSync(MOTOR, 'utf8') });
  const geladen = warte('Page.loadEventFired');
  await sende('Page.navigate', { url: pathToFileURL(path.resolve(szene)).href });
  await geladen;
  await rechne('document.fonts.ready.then(() => typeof window.zeit === "function")')
    .then(da => { if (!da) throw new Error('Die Szene hat keine Funktion window.zeit(t).'); });

  if (AUSKUNFT) fs.writeFileSync(AUSKUNFT, await rechne('JSON.stringify(window.AUSKUNFT ?? null)'));

  const foto = async (t, format) => {
    await rechne(`window.zeit(${t})`);
    return Buffer.from((await sende('Page.captureScreenshot', { format, quality: 96, optimizeForSpeed: true })).data, 'base64');
  };

  if (EINZEL !== null) {
    const ziel = AUS || szene.replace(/\.html?$/i, '') + `-${(+EINZEL).toFixed(2)}.png`;
    fs.writeFileSync(ziel, await foto(+EINZEL, 'png'));
    console.log('BILD ' + ziel);
  } else {
    const bilder = Math.round(DAUER * FPS - 1e-6);
    // Für den fertigen Film reicht JPEG in hoher Güte (schnell). Durchsichtig geht nur mit PNG.
    const format = DURCHSICHTIG ? 'png' : 'jpeg';
    const ffmpeg = spawn('ffmpeg', ['-hide_banner', '-y', '-v', 'error', '-f', 'image2pipe', '-framerate', FPS_TEXT,
      '-c:v', DURCHSICHTIG ? 'png' : 'mjpeg', '-i', '-', ...(TON ? ['-i', TON] : []),
      ...(DURCHSICHTIG ? ['-c:v', 'qtrle'] : ['-c:v', 'libx264', '-preset', 'medium', '-crf', '15', '-pix_fmt', 'yuv420p', '-movflags', '+faststart']),
      ...(TON ? ['-c:a', 'aac', '-b:a', '192k', '-shortest'] : []), AUS], { stdio: ['pipe', 'inherit', 'inherit'] });
    const fertig = new Promise(ok => ffmpeg.on('close', ok));
    const t0 = Date.now();
    let zuletzt = null, bild = null, eigene = 0;
    for (let n = 0; n < bilder; n++) {
      const t = szenenzeit(n);
      if (t !== zuletzt) { bild = await foto(t, format); zuletzt = t; eigene++; }   // steht die Uhr, steht das Bild
      const voll = !ffmpeg.stdin.write(bild);
      if (voll) await new Promise(r => ffmpeg.stdin.once('drain', r));
      if (n % 150 === 149) console.error(`  abgelichtet ${n + 1} von ${bilder}`);
    }
    ffmpeg.stdin.end();
    const code = await fertig;
    if (code !== 0) throw new Error('ffmpeg ist gescheitert (Code ' + code + ')');
    const sek = (Date.now() - t0) / 1000;
    console.log(`FILM ${AUS} · ${bilder} Bilder (${eigene} verschiedene) in ${sek.toFixed(1)} s (${(eigene / sek).toFixed(1)} je Sekunde)`);
  }
} catch (e) {
  console.error('FEHLER: ' + e.message);
  process.exitCode = 1;
} finally {
  try { ws.close(); } catch {}
  aufraeumen();
}
