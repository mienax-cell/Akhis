// MAGI Videoschnitt · Grafik-Motor
//
// Bewegungsgrafik, die ÜBER ein gefilmtes Video gelegt wird: Karten, Schrift im Takt der Stimme, Zähler,
// kleine Zeichnungen. Eine Szenen-Seite beschreibt nur, WAS wann zu sehen ist — in HTML mit ein paar
// data-Angaben. Dieser Motor macht daraus window.zeit(t): das Bild zur Sekunde t des FERTIGEN Videos.
// Er wird beim Ablichten vor der Seite geladen („schnitt.py grafik“ sorgt dafür); die Seite bindet nichts ein.
//
// Wann etwas passiert, hängt an den Wörtern des Schnittplans (window.DATEN.woerter, Zeiten im fertigen Video):
//   w:41        wenn Wort Nummer 41 beginnt (die Nummern aus „schnitt.py zeigen“; ist es geschnitten: das nächste)
//   e:41        wenn Wort 41 endet
//   t:12.5      feste Sekunde          anfang / ende      Anfang und Ende des Videos
//   dahinter +0.2 oder -0.1 (Sekunden)
//
// Bausteine:
//   <section class="szene" data-von="w:13-0.2" data-bis="e:30+0.4" data-fn="name">   ein Auftritt; kommt und geht weich
//   <div data-ab="w:25" data-art="feder">       ein Teil mit eigenem Zeitpunkt.  Arten: hoch, pop, feder, auf,
//                                               wachs (wächst von links), buchstaben (Buchstabe für Buchstabe)
//   <div data-um="0.3">                         Zeitpunkt in Sekunden ab Beginn der Szene
//   <div class="zeile" data-ab="w:72">Text</div> erscheint Wort für Wort mit den gesprochenen Wörtern ab Wort 72
//   data-weg="e:30"  verschwindet dann    data-zaehl="42" (data-stellen, data-zd)  zählt hoch
//   data-klang="pop:0.6"                        ein leiser Klang zu diesem Teil (wusch, pop, tick, klick, glocke, tiefe)
//   MOTOR.zeichne('name', (t, szene) => …)      eigene Zeichnung für eine Szene mit data-fn="name"
//
// Aussehen: .glas (dunkle Karte), .glas.hell, .pille, .mono, .zahl, .a (Akzentfarbe aus dem Stil), .leise.
(() => {
  'use strict';
  const D = window.DATEN;
  if (!D || !Array.isArray(D.woerter)) throw new Error('window.DATEN fehlt (die Seite über „schnitt.py grafik“ ablichten).');

  const kl = x => Math.min(1, Math.max(0, x));
  const aus3 = x => 1 - Math.pow(1 - kl(x), 3);
  const aus5 = x => 1 - Math.pow(1 - kl(x), 5);
  const einaus = x => { x = kl(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const rueck = x => { x = kl(x); const c = 2.1; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };   // schießt kurz über
  const misch = (a, b, x) => a + (b - a) * x;
  const zufall = (i, k = 0) => { const x = Math.sin(i * 127.1 + k * 311.7 + 13.37) * 43758.5453; return x - Math.floor(x); };
  const zahl = (x, stellen = 0) => Number(x).toLocaleString('de-DE', { minimumFractionDigits: stellen, maximumFractionDigits: stellen }).replace(/\./g, ' ');

  // Ein Anker → Sekunde im fertigen Video
  const stelle = nr => { const k = D.woerter.findIndex(w => w.i >= nr); return k < 0 ? D.woerter.length - 1 : k; };
  function wann(s) {
    const m = /^(?:(w|e|t):(\d+(?:\.\d+)?)|(anfang|ende))([+-]\d*\.?\d+)?$/.exec(String(s).trim());
    if (!m) throw new Error('Zeitpunkt nicht verstanden: ' + s);
    const mehr = +(m[4] || 0);
    if (m[3]) return (m[3] === 'ende' ? D.dauer : 0) + mehr;
    if (m[1] === 't') return +m[2] + mehr;
    const w = D.woerter[stelle(+m[2])];
    return (m[1] === 'w' ? w.t : w.e) + mehr;
  }

  const KLAENGE = [];
  const klang = (zeit, art, staerke = 1) => KLAENGE.push({ zeit: Math.max(0, +(+zeit).toFixed(3)), art, staerke });
  const ZEICHNER = {};
  window.MOTOR = { D, kl, aus3, aus5, einaus, rueck, misch, zufall, zahl, wann, klang, zeichne: (name, fn) => { ZEICHNER[name] = fn; } };
  window.AUSKUNFT = { klaenge: KLAENGE };

  const CSS = `
    * { box-sizing:border-box; margin:0; padding:0; }
    html, body { width:100%; height:100%; overflow:hidden; background:transparent; }
    body { font-family:"Segoe UI Variable Display","Segoe UI",sans-serif; font-weight:700; letter-spacing:-.03em; line-height:1.05;
           color:#fff; --akzent:${D.akzent || '#FF5A1F'}; --tinte:#12101C; }
    .szene { position:absolute; inset:0; visibility:hidden; transform-origin:50% 16%; }
    .szene > *, .glas > * { position:absolute; }
    .glas { background:rgba(18,16,28,.86); border:2px solid rgba(255,255,255,.16); border-radius:44px; color:#fff;
            box-shadow:0 28px 64px rgba(0,0,0,.38), 0 4px 12px rgba(0,0,0,.2); }
    .glas.hell { background:rgba(255,255,255,.92); border-color:#fff; color:var(--tinte); }
    .pille { padding:.2em .62em .27em; border-radius:999px; white-space:nowrap; }
    .zeile { white-space:nowrap; }
    .w, .l, .zahl { display:inline-block; }
    .l { white-space:pre; }
    .a { color:var(--akzent); }
    .leise { opacity:.62; }
    .mono { font-family:"Cascadia Mono","Cascadia Code",Consolas,monospace; font-weight:500; letter-spacing:.04em; font-size:24px;
            text-transform:uppercase; opacity:.62; white-space:nowrap; }
    .zahl { font-variant-numeric:tabular-nums; letter-spacing:-.05em; white-space:nowrap; }
  `;

  const VORAUS = 0.06, EIN = 0.42, AUS = 0.32;
  const DAUER = { hoch: .34, pop: .40, feder: .58, hauch: .46, auf: .30, wachs: .5 };
  const SZENEN = [];

  function teil(sz, el, t0, art) {
    const d = el.dataset;
    sz.teile.push({ el, t0, art, d: d.dauer !== undefined ? +d.dauer : (DAUER[art] || .34), weg: d.weg ? wann(d.weg) : null,
                    zaehl: d.zaehl !== undefined ? { bis: +d.zaehl, von: +(d.von || 0), stellen: +(d.stellen || 0), d: +(d.zd || .7) } : null });
    if (d.klang) { const [art2, st] = d.klang.split(':'); klang(t0, art2, st === undefined ? 1 : +st); }
  }
  const passend = el => {                                             // zu breite Zeilen kleiner setzen
    let fs = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollWidth > el.clientWidth + 1 && fs > 24) el.style.fontSize = (fs -= 2) + 'px';
  };

  function einlesen() {
    document.head.appendChild(Object.assign(document.createElement('style'), { textContent: CSS }));   // erst jetzt gibt es die Seite
    for (const el of document.querySelectorAll('.szene')) {
      const sz = { el, teile: [], fn: el.dataset.fn || '', von: wann(el.dataset.von || 'anfang'), bis: wann(el.dataset.bis || 'ende') };
      SZENEN.push(sz);
      if (el.dataset.klang) { const [art, st] = el.dataset.klang.split(':'); klang(sz.von, art, st === undefined ? 1 : +st); }
      for (const z of el.querySelectorAll('.zeile')) {                 // Wort für Wort an den gesprochenen Wörtern
        const m = /^w:(\d+)/.exec(z.dataset.ab || '');
        if (!m) throw new Error('Eine .zeile braucht data-ab="w:NUMMER".');
        let k = stelle(+m[1]);
        const lauf = knoten => {
          for (const kind of [...knoten.childNodes]) {
            if (kind.nodeType === 3) {
              const neu = document.createDocumentFragment();
              for (const s of kind.textContent.split(/(\s+)/)) {
                if (!s) continue;
                if (/^\s+$/.test(s)) { neu.append(' '); continue; }
                const w = Object.assign(document.createElement('span'), { className: 'w', textContent: s });
                const wort = D.woerter[Math.min(k, D.woerter.length - 1)];
                teil(sz, w, wort.t + 0.15 * Math.max(0, k - D.woerter.length + 1) - VORAUS, 'hoch');
                k++;
                neu.append(w);
              }
              kind.replaceWith(neu);
            } else if (kind.nodeType === 1 && kind.tagName !== 'BR') {
              if (kind.dataset.ab) { const n = /^w:(\d+)/.exec(kind.dataset.ab); if (n) k = stelle(+n[1]); delete kind.dataset.ab; }   // neu ansetzen
              lauf(kind);
            }
          }
        };
        lauf(z);
        delete z.dataset.ab;
        passend(z);
      }
      for (const t of el.querySelectorAll('[data-ab], [data-um]')) {
        const t0 = t.dataset.um !== undefined ? sz.von + +t.dataset.um : wann(t.dataset.ab) - VORAUS;
        const art = t.dataset.art || 'hoch';
        if (art === 'buchstaben') {
          const text = t.textContent;
          t.textContent = '';
          [...text].forEach((z, n) => {
            const l = Object.assign(document.createElement('span'), { className: 'l', textContent: z });
            t.append(l);
            sz.teile.push({ el: l, t0: t0 + n * 0.03, art: 'hauch', d: DAUER.hauch });
          });
          if (t.dataset.klang) { const [a2, st] = t.dataset.klang.split(':'); klang(t0, a2, st === undefined ? 1 : +st); }
          passend(t);
        } else teil(sz, t, t0, art);
      }
    }
    KLAENGE.sort((a, b) => a.zeit - b.zeit);
  }

  function stelleHin(it, t) {
    const p = kl((t - it.t0) / it.d), s = it.el.style;
    if (p <= 0) { s.opacity = 0; return; }
    let o = 1, tr = '', f = 0;
    if (it.art === 'hoch') { const e = aus3(p); tr = `translateY(${((1 - e) * .45).toFixed(4)}em)`; f = (1 - e) * 12; o = kl(p * 2.4); }
    else if (it.art === 'hauch') { const e = aus3(p); tr = `translateY(${((1 - e) * .22).toFixed(4)}em)`; f = (1 - e) * 18; o = e; }
    else if (it.art === 'pop') { tr = `scale(${(0.4 + 0.6 * rueck(p)).toFixed(4)})`; f = (1 - aus3(p)) * 8; o = kl(p * 3.5); }
    else if (it.art === 'feder') { const e = aus3(p); tr = `translateY(${((1 - e) * -70).toFixed(2)}px) scale(${(0.74 + 0.26 * rueck(p)).toFixed(4)})`; f = (1 - e) * 14; o = kl(p * 3); }
    else if (it.art === 'auf') o = aus3(p);
    else if (it.art === 'wachs') tr = `scaleX(${aus5(p).toFixed(5)})`;
    if (it.weg !== null && it.weg !== undefined && t > it.weg) { const q = kl((t - it.weg) / .3); o *= 1 - q * q; f += q * 12; tr += ` scale(${(1 - .08 * q).toFixed(4)})`; }
    s.opacity = o.toFixed(3);
    s.transform = tr || 'none';
    s.filter = f > 0.3 ? `blur(${f.toFixed(2)}px)` : 'none';
    if (it.zaehl) {
      const z = it.zaehl, jetzt = misch(z.von, z.bis, aus3((t - it.t0) / z.d)), text = zahl(z.stellen ? jetzt : Math.round(jetzt), z.stellen);
      if (it.el.textContent !== text) it.el.textContent = text;
    }
  }

  window.zeit = t => {
    for (const sz of SZENEN) {
      const s = sz.el.style, da = t >= sz.von - 0.001 && t < sz.bis + AUS;
      s.visibility = da ? 'visible' : 'hidden';
      if (!da) continue;
      const ein = aus3((t - sz.von) / EIN), raus = aus3((t - sz.bis) / AUS);
      s.opacity = (ein * (1 - raus)).toFixed(3);
      s.transform = `translateY(${((1 - ein) * -40 - raus * 30).toFixed(2)}px) scale(${((.95 + .05 * ein) * (1 - .04 * raus)).toFixed(5)})`;
      s.filter = ein < 1 ? `blur(${((1 - ein) * 14).toFixed(2)}px)` : raus > 0 ? `blur(${(raus * 14).toFixed(2)}px)` : 'none';
      for (const it of sz.teile) stelleHin(it, t);
      if (sz.fn) { if (!ZEICHNER[sz.fn]) throw new Error('Zeichnung fehlt: ' + sz.fn); ZEICHNER[sz.fn](t, sz); }
    }
    return true;
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', einlesen); else einlesen();
})();
