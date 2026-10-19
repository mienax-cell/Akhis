'use strict';
// Videocutter · Oberfläche. Spricht nur mit dem eigenen Server (server.py) auf diesem Rechner.

// ===================================================================================== Helfer
const $ = (s, r = document) => r.querySelector(s);

function el(tag, attrs, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else if (k in e && typeof v !== 'string') e[k] = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kinder.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    e.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return e;
}

const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  funken: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4M17 5h4"/>',
  buch: '<path d="M2 4h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z"/>',
  kamera: '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="M16 10l6-3v10l-6-3"/>',
  mikro: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/>',
  schere: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M17 8h4M3 16h4M17 16h4M3 12h18"/>',
  hoch: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  ordner: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  runter: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  kopie: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  stift: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  play: '<path d="M7 4l13 8-13 8z" fill="currentColor"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  haken: '<path d="M5 12l5 5 9-10"/>',
  warn: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
  zurueck: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  auge: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  pfeil: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  neu: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
};
function icon(name) {
  const t = document.createElement('template');
  t.innerHTML = `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ''}</svg>`;
  return t.content.firstChild;
}

async function api(weg, { methode = 'GET', daten } = {}) {
  const antwort = await fetch('/api/' + weg, {
    method: methode,
    headers: daten !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: daten !== undefined ? JSON.stringify(daten) : undefined,
  });
  const text = await antwort.text();
  let d = null;
  try { d = text ? JSON.parse(text) : null; } catch { d = null; }
  if (!antwort.ok) throw new Error((d && d.fehler) || `Der Server antwortet mit ${antwort.status}.`);
  return d;
}

function hochladen(pid, zweck, datei, { name, nurTon = false, fortschritt } = {}) {
  return new Promise((ok, nein) => {
    const x = new XMLHttpRequest();
    const q = new URLSearchParams({ zweck, name: name || datei.name || 'aufnahme.webm', nur_ton: nurTon ? '1' : '0' });
    x.open('PUT', `/api/projekte/${pid}/hochladen?${q}`);
    x.upload.onprogress = e => { if (e.lengthComputable && fortschritt) fortschritt(e.loaded / e.total); };
    x.onload = () => {
      let d = null;
      try { d = JSON.parse(x.responseText); } catch { d = null; }
      if (x.status < 300) ok(d); else nein(new Error((d && d.fehler) || 'Das Hochladen ist gescheitert.'));
    };
    x.onerror = () => nein(new Error('Das Hochladen ist gescheitert (keine Verbindung zum Server).'));
    x.send(datei);
  });
}

const dateiUrl = (rel, frisch = false) => `/api/projekte/${S.p.id}/datei/${rel.split('/').map(encodeURIComponent).join('/')}${frisch ? '?v=' + Date.now() : ''}`;
const zahl = (x, stellen = 1) => Number(x || 0).toLocaleString('de-DE', { minimumFractionDigits: stellen, maximumFractionDigits: stellen });
const sek = x => zahl(x, 1) + ' s';
function uhrzeit(s) { s = Math.max(0, s || 0); return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`; }

function toast(text, art = 'fehler') {
  const t = el('div', { class: `toast ${art}` }, text);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), art === 'fehler' ? 7000 : 4000);
}

function schalter(titel, hilfe, an, beiAenderung, aus = false) {
  return el('label', { class: 'schalter', style: aus ? { opacity: .45, pointerEvents: 'none' } : null },
    el('input', { type: 'checkbox', checked: !!an, onchange: e => beiAenderung(e.target.checked) }),
    el('span', { class: 'bahn' }),
    el('span', {}, el('b', {}, titel), hilfe ? el('small', {}, hilfe) : null));
}

function wahl(optionen, aktuell, beiWahl) {
  return el('div', { class: 'wahl' }, optionen.map(([wert, text]) =>
    el('button', { type: 'button', class: wert === aktuell ? 'an' : '', onclick: () => beiWahl(wert) }, text)));
}

function leerKarte(zeichen, titel, text, ...knoepfe) {
  return el('div', { class: 'karte leer' }, el('div', { class: 'leer-zeichen' }, icon(zeichen)), el('h2', {}, titel), el('p', {}, text),
    el('div', { class: 'zeile', style: { justifyContent: 'center' } }, knoepfe));
}

// Sprechtext mit *Betonung* und „ / “ (Pause) als Knoten
function sprechtext(text) {
  const frag = document.createDocumentFragment();
  for (const teil of String(text || '').split(/(\*[^*]+\*|\s\/\s)/)) {
    if (!teil) continue;
    if (teil.startsWith('*') && teil.endsWith('*') && teil.length > 2) frag.append(el('span', { class: 'betont' }, teil.slice(1, -1)));
    else if (/^\s\/\s$/.test(teil)) frag.append(' ', el('span', { class: 'pause', title: 'kurze Pause' }, '‖'), ' ');
    else frag.append(teil);
  }
  return frag;
}

// ===================================================================================== Zustand
const S = {
  zustand: null, liste: [], p: null, tab: 'skript', plan: null, motionPlan: null, auftrag: null, planNeu: false,
  modus: 'ansehen', skriptBearbeiten: false, fassung: null, vorschau: null,
  vorgemerkt: { weg: new Set(), doch: new Set(), betonen: new Set(), unbetonen: new Set(), annehmen: new Set(), ablehnen: new Set() },
};

const TABS = [['skript', 'Skript', 'funken'], ['aufnahme', 'Aufnahme', 'kamera'], ['schnitt', 'Schnitt', 'schere'], ['motion', 'Motion-Video', 'film']];

const SCHRITTE = {
  skript: [['regeln', 'Regelwerk laden'], ['recherche', 'Zahlen an Originalquellen prüfen', true], ['schreiben', 'Skript schreiben und selbst prüfen']],
  schnitt: [['umwandeln', 'Aufnahme umwandeln', true], ['plan', 'Ton erkennen und Schnittplan bauen'], ['skript', 'Mit dem Skript abgleichen'], ['rendern', 'Video bauen']],
  aendern: [['plan', 'Schnittplan ändern'], ['rendern', 'Video bauen']],
  vorbild: [['messen', 'Vorbild auswerten']],
  motion: [['ton', 'Stimme vorbereiten'], ['plan', 'Stimme erkennen, Pausen raus'], ['schnitt', 'Ton schneiden und einpegeln'], ['ablichten', 'Szenen Bild für Bild ablichten']],
};

const SAEULEN = [
  { id: 'mythen', name: 'Mythen & Fehler', text: 'Viral-Garant: einen Fehler aufdecken, den fast jeder macht',
    ideen: ['3 Dinge, die du mit 20 tun musst, um mit 40 finanziell frei zu sein', 'Warum dein Sparbuch dich arm macht', 'Der größte Fehler bei der Altersvorsorge'] },
  { id: 'anleitung', name: 'Anleitung', text: 'Schritt für Schritt, wird gespeichert und geteilt',
    ideen: ['So legst du 100 € im Monat optimal an (Schritt für Schritt)', '3 Steuer-Tricks, die dir dein Chef verheimlicht', 'Deine Renteninfo richtig lesen'] },
  { id: 'klartext', name: 'Klartext & Meinung', text: 'News einordnen, schlechte Tipps entkräften',
    ideen: ['Warum 90 % der Deutschen ihre Rente falsch planen', 'Reaktion auf einen schlechten Finanz-Tipp', 'Was die Rentenanpassung wirklich bedeutet'] },
  { id: 'alltag', name: 'Alltagstipp', text: 'Praktisch, sofort umsetzbar (Freitag)',
    ideen: ['Fixkosten-Check in 10 Minuten', 'Notgroschen: wie viel ist genug?', 'Gehaltserhöhung: was davon sparen?'] },
];
const PLAN_TAG = {
  1: ['mythen', 'Montag laut Wochenplan: Reel zu einem Finanzfehler oder Mythos'],
  2: ['anleitung', 'Dienstag laut Wochenplan: Schritt-für-Schritt-Anleitung'],
  3: ['anleitung', 'Mittwoch ist laut Plan Karussell-Tag. Für ein Reel passt eine Anleitung.'],
  4: ['klartext', 'Donnerstag laut Wochenplan: Klartext und Meinung'],
  5: ['alltag', 'Freitag laut Wochenplan: praktischer Tipp für den Alltag'],
  6: ['klartext', 'Samstag ist laut Plan Story-Q&A. Ein Reel ist Bonus.'],
  0: ['mythen', 'Sonntag ist laut Plan Planungstag. Gut zum Vorproduzieren.'],
};
const STIL_INFO = [
  ['reel', 'Reel', 'Dicht geschnitten, Untertitel bauen sich auf, Zoom-Takt, Balken'],
  ['schnell', 'Schnell', 'Harte Schnitte, macht von selbst 9:16'],
  ['standard', 'Standard', 'Pausen raus, große Untertitel, gelbes Wort'],
  ['ruhig', 'Ruhig', 'Lässt Atempausen stehen, dezente Untertitel'],
];
const GRUND = { fuellwort: 'Füllwörter', wiederholung: 'Wiederholungen', neuansatz: 'Neuansätze', doppelter_satz: 'doppelte Sätze', manuell: 'von Hand' };

// ===================================================================================== Start
async function start() {
  $('#neu').append(icon('plus'), 'Neues Video');
  $('#neu').onclick = neuesProjekt;
  $('#regelwerk-knopf').append(icon('buch'), 'Regelwerk');
  $('#regelwerk-knopf').onclick = regelwerkOverlay;
  $('#titel').addEventListener('change', async e => {
    if (!S.p) return;
    try { S.p = await api(`projekte/${S.p.id}`, { methode: 'PATCH', daten: { titel: e.target.value } }); await listeLaden(); } catch (f) { toast(f.message); }
  });
  zeichneZustand();
  api('zustand').then(z => { S.zustand = z; zeichneZustand(); }).catch(() => {});
  await listeLaden();
  if (S.liste.length) await projektOeffnen(S.liste[0].id);
  else zeichne();
  document.addEventListener('keydown', tastatur);
  setInterval(() => { if (S.auftrag && !S.auftrag.fertig && !S.auftrag.fehler) planeTeil(); }, 1000);
}

async function listeLaden() {
  try { S.liste = await api('projekte'); } catch (f) { toast(f.message); }
  zeichneListe();
}

async function neuesProjekt() {
  try {
    const p = await api('projekte', { methode: 'POST', daten: { titel: '' } });
    await listeLaden();
    await projektOeffnen(p.id, 'skript');
    themaOverlay();
  } catch (f) { toast(f.message); }
}

async function projektOeffnen(id, tab) {
  kameraAus();
  vorschauStopp();
  try { S.p = await api(`projekte/${id}`); } catch (f) { toast(f.message); return; }
  if (S.auftrag && S.auftrag.quelle) S.auftrag.quelle.close();
  Object.assign(S, { auftrag: null, plan: null, motionPlan: null, vorschau: null, fassung: null, skriptBearbeiten: false, modus: 'ansehen' });
  vormerkungLeeren();
  if (S.p.arbeitsordner) api(`projekte/${id}/plan`).then(pl => { S.plan = pl; zeichne(); }).catch(() => {});
  if (S.p.motion && S.p.motion.daten) api(`projekte/${id}/motion-plan`).then(pl => { S.motionPlan = pl; }).catch(() => {});
  if (S.p.auftrag) auftragVerfolgen(S.p.auftrag.id, S.p.auftrag.art);
  S.tab = tab || (!S.p.skript ? 'skript' : !S.p.quelle ? 'aufnahme' : S.p.quelle.nur_ton ? 'motion' : 'schnitt');
  zeichne();
}

async function projektNeuLaden() {
  if (!S.p) return;
  try { S.p = await api(`projekte/${S.p.id}`); } catch (f) { toast(f.message); }
  listeLaden();
}

function vormerkungLeeren() { for (const s of Object.values(S.vorgemerkt)) s.clear(); }

function tastatur(e) {
  if (e.key === 'Escape' && !$('#overlay').hidden && !(S.auftrag && S.auftrag.art === 'skript' && !S.auftrag.fertig && !S.auftrag.fehler)) overlayZu();
}

// ===================================================================================== Zeichnen
function zeichne() {
  zeichneListe();
  const titel = $('#titel');
  titel.disabled = !S.p;
  titel.value = S.p ? S.p.titel : '';
  const tabs = $('#schritte');
  tabs.replaceChildren(...TABS.map(([id, name], n) => {
    const erledigt = S.p && { skript: !!S.p.skript, aufnahme: !!S.p.quelle, schnitt: S.p.ergebnisse.length > 0, motion: !!(S.p.motion && S.p.motion.ergebnis) }[id];
    return el('button', { class: `schritt-tab ${S.tab === id ? 'aktiv' : ''} ${erledigt ? 'erledigt' : ''}`, type: 'button', disabled: !S.p,
      onclick: () => tabWechseln(id) }, el('span', { class: 'schritt-nr' }, erledigt && S.tab !== id ? icon('haken') : n + 1), name);
  }));
  const f = $('#flaeche');
  f.replaceChildren();
  if (!S.p) {
    f.append(leerKarte('film', 'Willkommen im Videocutter', 'Thema reinwerfen, Skript nach dem Regelwerk bekommen, aufnehmen, schneiden lassen und zusehen, was passiert. Oder aus deiner Stimme ein Motion-Video bauen.',
      el('button', { class: 'knopf voll gross', onclick: neuesProjekt }, icon('plus'), 'Erstes Video anlegen')));
    return;
  }
  ({ skript: zeichneSkript, aufnahme: zeichneAufnahme, schnitt: zeichneSchnitt, motion: zeichneMotion })[S.tab](f);
}

function tabWechseln(id) {
  if (S.tab === 'aufnahme' && id !== 'aufnahme') {
    if (R.laeuft) { toast('Erst die Aufnahme stoppen.'); return; }
    kameraAus();
  }
  if (S.tab === 'motion' && id !== 'motion') vorschauStopp();
  S.tab = id;
  zeichne();
}

function zeichneListe() {
  const nav = $('#projekte');
  if (!S.liste.length) { nav.replaceChildren(el('div', { class: 'leer-seite' }, 'Noch keine Projekte.')); return; }
  nav.replaceChildren(...S.liste.map(p => el('button', { class: `projekt ${S.p && S.p.id === p.id ? 'aktiv' : ''}`, type: 'button', onclick: () => projektOeffnen(p.id) },
    el('span', { class: 'projekt-name' }, p.titel),
    el('span', { class: 'projekt-info' },
      el('span', { class: 'marken', title: 'Skript · Aufnahme · Schnitt · Motion' }, ['skript', 'quelle', 'ergebnis', 'motion'].map(k => el('i', { class: `marke-p ${p[k] ? 'da' : ''}` }))),
      p.geaendert.slice(5).replace('-', '.').replace(' ', ' · ')))));
}

function zeichneZustand() {
  const z = S.zustand;
  const punkt = (text, ok, titel) => el('span', { class: `punkt ${z ? (ok ? 'ok' : 'nein') : 'warte'}`, title: titel }, text);
  $('#zustand').replaceChildren(
    punkt('Schnitt', z && z.schnitt.ok, z ? z.schnitt.punkte.map(p => `${p.ok ? '✓' : '✗'} ${p.name}: ${p.wert}`).join('\n') : 'wird geprüft …'),
    punkt('Claude', z && z.claude, 'claude-Kommandozeile für das Skript-Schreiben'),
    punkt('Motion', z && z.node && z.browser, 'Node und Edge/Chrome für Motion-Videos'));
}

// ===================================================================================== Aufträge
function auftragVerfolgen(id, art) {
  if (S.auftrag && S.auftrag.quelle) S.auftrag.quelle.close();
  const a = { id, art, schritte: {}, log: [], fehler: null, fertig: false, quelle: null };
  S.auftrag = a;
  const q = new EventSource(`/api/auftraege/${id}/ereignisse`);
  a.quelle = q;
  q.onmessage = m => {
    if (S.auftrag !== a) { q.close(); return; }
    ereignis(a, JSON.parse(m.data));
  };
  q.onerror = () => { if (a.fertig || a.fehler || q.readyState === EventSource.CLOSED) q.close(); };
  return a;
}

function ereignis(a, e) {
  const frisch = Date.now() / 1000 - e.zeit < 15;
  if (e.typ === 'schritt') {
    const s = a.schritte[e.id] || (a.schritte[e.id] = { anteil: null });
    if (e.status === 'laeuft' && s.status !== 'laeuft') s.seit = e.zeit;
    s.status = e.status;
    if (e.text) s.text = e.text;
    if (e.status === 'fertig') s.anteil = null;
  } else if (e.typ === 'fortschritt') {
    const s = a.schritte[e.id] || (a.schritte[e.id] = { status: 'laeuft' });
    s.anteil = e.anteil;
  } else if (e.typ === 'log') {
    a.log.push(e.text);
    if (a.log.length > 500) a.log.splice(0, 150);
  } else if (e.typ === 'plan') {
    if (a.art === 'motion') S.motionPlan = e.plan; else S.plan = e.plan;
    S.planNeu = true;
  } else if (e.typ === 'vorschau') {
    S.vorschau = { daten: e.daten, ton: e.ton, neu: true };
  } else if (e.typ === 'fertig') {
    a.fertig = true;
    a.quelle.close();
    auftragFertig(a, e.ergebnis || {}, frisch);
    return;
  } else if (e.typ === 'fehler') {
    a.fehler = e.text;
    a.quelle.close();
    for (const s of Object.values(a.schritte)) if (s.status === 'laeuft') s.status = 'fehler';
    if (frisch) toast(e.text);
    if (a.art === 'skript' && !$('#overlay').hidden) skriptFehlerZeigen(a);
    zeichne();
    return;
  }
  planeTeil();
}

async function auftragFertig(a, ergebnis, frisch) {
  await projektNeuLaden();
  if (a.art === 'skript') {
    overlayZu();
    S.tab = 'skript';
    if (frisch) toast('Skript ist fertig.', 'gut');
  } else if (a.art === 'schnitt' || a.art === 'aendern') {
    vormerkungLeeren();
    S.fassung = null;
    S.modus = 'ansehen';
    if (frisch) toast(`Fertig geschnitten: ${sek(ergebnis.ergebnis && ergebnis.ergebnis.dauer)}`, 'gut');
  } else if (a.art === 'motion') {
    if (frisch) toast('Motion-Video ist fertig.', 'gut');
  } else if (a.art === 'vorbild') {
    if (frisch) toast('Vorbild ausgewertet.', 'gut');
  }
  zeichne();
}

let teilGeplant = 0;
function planeTeil() {
  if (teilGeplant) return;
  teilGeplant = requestAnimationFrame(() => {
    teilGeplant = 0;
    for (const ort of document.querySelectorAll('[data-ablauf]')) ort.replaceChildren(ablaufAnsicht(ort.dataset.ablauf.split(',')));
    if (S.planNeu) {
      S.planNeu = false;
      const po = $('#plan-ort');
      if (po) po.replaceChildren(planAnsicht());
      const mo = $('#motion-plan-ort');
      if (mo) mo.replaceChildren(motionPlanAnsicht());
    }
    if (S.vorschau && S.vorschau.neu && $('#vorschau-ort')) { S.vorschau.neu = false; $('#vorschau-ort').replaceChildren(vorschauAnsicht()); }
  });
}

function laeuftAuftrag(...arten) {
  const a = S.auftrag;
  return a && arten.includes(a.art) && !a.fertig && !a.fehler;
}

async function auftragStarten(weg, daten, art) {
  try {
    const { auftrag } = await api(`projekte/${S.p.id}/${weg}`, { methode: 'POST', daten });
    auftragVerfolgen(auftrag, art);
    zeichne();
    return true;
  } catch (f) { toast(f.message); return false; }
}

async function auftragAbbrechen() {
  if (!S.auftrag) return;
  try { await api(`auftraege/${S.auftrag.id}/abbrechen`, { methode: 'POST' }); } catch (f) { toast(f.message); }
}

// Die Schritte eines Auftrags mit Status, Text, Fortschritt und Protokoll
function ablaufAnsicht(arten) {
  const a = S.auftrag;
  if (!a || !arten.includes(a.art)) return el('div');
  const jetzt = Date.now() / 1000;
  const liste = SCHRITTE[a.art].filter(([id, , freiwillig]) => !freiwillig || a.schritte[id]);
  const kasten = el('div', { class: 'ablauf' }, liste.map(([id, name]) => {
    const s = a.schritte[id] || { status: 'offen' };
    const zeichen = { fertig: icon('haken'), fehler: icon('x'), uebersprungen: '–' }[s.status] || '';
    const dauer = s.status === 'laeuft' && s.seit ? ` · ${Math.max(0, Math.round(jetzt - s.seit))} s` : '';
    return el('div', { class: `schritt ${s.status}` },
      el('span', { class: 'schritt-zeichen' }, zeichen),
      el('span', { class: 'schritt-name' }, name, el('span', { class: 'sehr-leise' }, dauer)),
      s.text ? el('div', { class: 'schritt-text' }, s.text) : null,
      s.status === 'laeuft' ? el('div', { class: `balken ${s.anteil === null || s.anteil === undefined ? 'unbestimmt' : ''}` },
        el('i', { style: { width: `${Math.round((s.anteil || 0) * 100)}%` } })) : null);
  }));
  const teile = [kasten];
  if (a.fehler) teile.push(el('div', { class: 'fehler-kasten' }, a.fehler));
  if (a.log.length) {
    const d = el('details', {}, el('summary', {}, `Protokoll (${a.log.length} Zeilen)`), el('div', { class: 'protokoll' }, a.log.slice(-80).join('\n')));
    d.open = !!(S.protokollOffen && S.protokollOffen[a.id]);
    d.addEventListener('toggle', () => { S.protokollOffen = { ...(S.protokollOffen || {}), [a.id]: d.open }; });
    teile.push(d);
  }
  if (!a.fertig && !a.fehler) teile.push(el('div', { class: 'zeile ende', style: { marginTop: '10px' } },
    el('button', { class: 'knopf klein leise', onclick: auftragAbbrechen }, icon('x'), 'Abbrechen')));
  return el('div', {}, teile);
}

// ===================================================================================== Overlay
function overlayAuf(inhalt) {
  const o = $('#overlay');
  o.replaceChildren(inhalt);
  o.hidden = false;
  o.onclick = e => { if (e.target === o && !laeuftAuftrag('skript')) overlayZu(); };
}
function overlayZu() { $('#overlay').hidden = true; $('#overlay').replaceChildren(); }

// ---- Thema reinwerfen
function themaOverlay(vorgabe = {}) {
  const tag = PLAN_TAG[new Date().getDay()];
  const alt = (S.p.skript && S.p.skript.eingabe) || {};
  const e = { thema: '', saeule: tag[0], laenge: 45, faktencheck: true, dm: false, hinweis_sprechen: true, wunsch: '',
    ...(vorgabe.ueberarbeiten ? alt : {}), ...vorgabe };

  const dialog = el('div', { class: 'dialog' });
  const zeichneDialog = () => {
    const saeule = SAEULEN.find(s => s.id === e.saeule) || SAEULEN[0];
    const feld = el('textarea', { class: 'feld thema-feld', placeholder: 'Worum geht es? Zum Beispiel: Rentenlücke bei Berufseinsteigern', rows: 2,
      oninput: ev => { e.thema = ev.target.value; }, onkeydown: ev => { if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) abschicken(); } });
    feld.value = e.thema;
    dialog.replaceChildren(
      el('div', { class: 'dialog-kopf' }, el('div', { class: 'leer-zeichen', style: { width: '42px', height: '42px', borderRadius: '12px' } }, icon('funken')),
        el('div', {}, el('h2', {}, vorgabe.ueberarbeiten ? 'Skript überarbeiten' : 'Thema reinwerfen'),
          el('div', { class: 'sehr-leise' }, 'Claude schreibt nach dem Regelwerk deines Kollegen und dem Gemini-Plan.')),
        el('span', { class: 'abstand' }), el('button', { class: 'knopf leise', onclick: overlayZu, title: 'Schließen (Esc)' }, icon('x'))),
      feld,
      el('div', { class: 'ideen' }, saeule.ideen.map(t => el('button', { class: 'idee', type: 'button', onclick: () => { e.thema = t; zeichneDialog(); } }, t))),
      el('div', { class: 'hinweis-plan' }, icon('buch'), tag[1]),
      el('div', { class: 'dialog-abschnitt' }, el('label', {}, 'Content-Säule'),
        el('div', { class: 'saeulen' }, SAEULEN.map(s => el('button', { class: `saeule ${s.id === e.saeule ? 'an' : ''}`, type: 'button', onclick: () => { e.saeule = s.id; zeichneDialog(); } },
          el('b', {}, s.name), el('small', {}, s.text))))),
      el('div', { class: 'dialog-abschnitt zeile' },
        el('div', {}, el('span', { class: 'feld-titel' }, 'Länge'), wahl([[30, '30 s'], [45, '45 s'], [60, '60 s'], [90, '90 s']], e.laenge, w => { e.laenge = w; zeichneDialog(); })),
        el('span', { class: 'sehr-leise', style: { alignSelf: 'flex-end', paddingBottom: '8px' } }, `≈ ${Math.round(e.laenge * 2.5)} Wörter`)),
      el('div', { class: 'dialog-abschnitt schalter-raster' },
        schalter('Zahlen online prüfen', 'Jede Zahl an DRV, Destatis & Co. belegen (dauert 1–2 Minuten)', e.faktencheck, v => { e.faktencheck = v; }),
        schalter('DM-Trigger „STRATEGIE“', 'Schreib mir STRATEGIE per DM … (Gemini-Plan, Phase 4)', e.dm, v => { e.dm = v; }),
        schalter('„Keine individuelle Beratung“ sprechen', 'Sonst steht der Hinweis nur in der Caption', e.hinweis_sprechen, v => { e.hinweis_sprechen = v; })),
      el('div', { class: 'dialog-abschnitt' }, el('label', {}, vorgabe.ueberarbeiten ? 'Was soll anders werden?' : 'Zusätzlich beachten (freiwillig)'),
        (() => { const t = el('textarea', { class: 'feld', rows: 2, placeholder: vorgabe.ueberarbeiten ? 'Zum Beispiel: Hook frecher, Mehrwert mit Rechenbeispiel, kürzer' : 'Zum Beispiel: Zielgruppe Azubis, ohne Fachbegriffe', oninput: ev => { e.wunsch = ev.target.value; } }); t.value = e.wunsch || ''; return t; })()),
      el('div', { class: 'zeile ende', style: { marginTop: '22px' } },
        el('span', { class: 'sehr-leise' }, 'Strg + Enter'),
        el('button', { class: 'knopf', onclick: overlayZu }, 'Abbrechen'),
        el('button', { class: 'knopf voll gross', onclick: abschicken, disabled: !(S.zustand ? S.zustand.claude : true) }, icon('funken'), vorgabe.ueberarbeiten ? 'Überarbeiten' : 'Skript schreiben')));
    setTimeout(() => feld.focus(), 30);
  };
  const abschicken = async () => {
    if (!e.thema.trim()) { toast('Erst ein Thema eingeben.'); return; }
    if (vorgabe.ueberarbeiten && !(e.wunsch || '').trim()) { toast('Schreib kurz, was anders werden soll.'); return; }
    S.letzteEingabe = { ...e };
    const ok = await auftragStarten('skript-schreiben', { ...e, ueberarbeiten: !!vorgabe.ueberarbeiten }, 'skript');
    if (ok) skriptLaeuftZeigen(e);
  };
  zeichneDialog();
  overlayAuf(dialog);
}

function skriptLaeuftZeigen(e) {
  overlayAuf(el('div', { class: 'dialog' },
    el('div', { class: 'dialog-kopf' }, el('div', { class: 'leer-zeichen', style: { width: '42px', height: '42px', borderRadius: '12px' } }, icon('funken')),
      el('div', {}, el('h2', {}, 'Claude schreibt dein Skript'), el('div', { class: 'sehr-leise' }, `„${e.thema}“ · ${e.laenge} s · ${(SAEULEN.find(s => s.id === e.saeule) || {}).name}`))),
    el('div', { 'data-ablauf': 'skript' }, ablaufAnsicht(['skript']))));
}

function skriptFehlerZeigen(a) {
  overlayAuf(el('div', { class: 'dialog' },
    el('div', { class: 'dialog-kopf' }, el('h2', {}, 'Das hat nicht geklappt'), el('span', { class: 'abstand' }), el('button', { class: 'knopf leise', onclick: overlayZu }, icon('x'))),
    el('div', { 'data-ablauf': 'skript' }, ablaufAnsicht(['skript'])),
    el('div', { class: 'zeile ende', style: { marginTop: '16px' } },
      el('button', { class: 'knopf', onclick: overlayZu }, 'Schließen'),
      el('button', { class: 'knopf voll', onclick: () => themaOverlay(S.letzteEingabe || {}) }, icon('neu'), 'Nochmal versuchen'))));
}

// ---- Regelwerk ansehen und bearbeiten
async function regelwerkOverlay() {
  let texte;
  try { texte = await api('regelwerk'); } catch (f) { toast(f.message); return; }
  let welches = 'kollege';
  const dialog = el('div', { class: 'dialog breit' });
  const feld = el('textarea', { class: 'feld regel-text', spellcheck: false });
  const zeichneR = () => {
    feld.value = texte[welches];
    dialog.replaceChildren(
      el('div', { class: 'dialog-kopf' }, el('div', { class: 'leer-zeichen', style: { width: '42px', height: '42px', borderRadius: '12px' } }, icon('buch')),
        el('div', {}, el('h2', {}, 'Regelwerk'), el('div', { class: 'sehr-leise' }, 'Beide Texte gehen bei jedem Skript an Claude. Bei einem Widerspruch gilt das Regelwerk des Kollegen.')),
        el('span', { class: 'abstand' }), el('button', { class: 'knopf leise', onclick: overlayZu }, icon('x'))),
      el('div', { class: 'tabs-klein' }, wahl([['kollege', 'Regelwerk des Kollegen'], ['gemini', 'Gemini-Plan']], welches, w => { texte[welches] = feld.value; welches = w; zeichneR(); })),
      feld,
      el('div', { class: 'zeile ende', style: { marginTop: '14px' } },
        el('span', { class: 'sehr-leise' }, 'Gespeichert in videocutter\\regelwerk\\'),
        el('span', { class: 'abstand' }),
        el('button', { class: 'knopf', onclick: overlayZu }, 'Schließen'),
        el('button', { class: 'knopf voll', onclick: async () => {
          texte[welches] = feld.value;
          try { texte = await api('regelwerk', { methode: 'PUT', daten: texte }); toast('Regelwerk gespeichert.', 'gut'); } catch (f) { toast(f.message); }
        } }, icon('haken'), 'Speichern')));
  };
  zeichneR();
  overlayAuf(dialog);
}

// ===================================================================================== 1 · Skript
function zeichneSkript(f) {
  const sk = S.p.skript;
  if (!sk) {
    f.append(leerKarte('funken', 'Wirf ein Thema rein',
      'Claude schreibt ein Reel-Skript nach dem Regelwerk deines Kollegen und dem Gemini-Plan: Hook in den ersten 3 Sekunden, Mehrwert, Frage in die Kommentare. Betonte Wörter sind markiert, jede Zahl hat eine Quelle.',
      el('button', { class: 'knopf voll gross', onclick: () => themaOverlay() }, icon('funken'), 'Thema reinwerfen')));
    return;
  }
  const eingabe = sk.eingabe || {};
  const saeule = SAEULEN.find(s => s.id === eingabe.saeule);
  const offen = (sk.pruefung || []).filter(p => p.urteil === 'bitte_pruefen').length;
  const entwurf = S.skriptBearbeiten ? JSON.parse(JSON.stringify(sk)) : null;

  const links = el('div', { class: 'karte' },
    el('div', { class: 'skript-kopf' },
      el('div', { style: { flex: 1, minWidth: '260px' } },
        el('h1', {}, sk.titel || 'Skript'),
        el('div', { class: 'zeile' },
          saeule ? el('span', { class: 'chip gold' }, saeule.name) : null,
          el('span', { class: 'chip' }, `≈ ${Math.round((sk.woerter || 0) / 2.5)} s · ${sk.woerter || 0} Wörter`),
          el('span', { class: `chip ${eingabe.faktencheck ? 'gruen' : 'gelb'}` }, eingabe.faktencheck ? 'Zahlen online geprüft' : 'Zahlen nicht online geprüft'),
          offen ? el('span', { class: 'chip gelb' }, icon('warn'), `${offen} bitte prüfen`) : null)),
      el('div', { class: 'zeile' },
        S.skriptBearbeiten ? null : el('button', { class: 'knopf klein', onclick: () => { S.skriptBearbeiten = true; zeichne(); } }, icon('stift'), 'Bearbeiten'),
        S.skriptBearbeiten ? null : el('button', { class: 'knopf klein', onclick: () => themaOverlay({ ueberarbeiten: true, wunsch: '' }) }, icon('neu'), 'Überarbeiten'),
        S.skriptBearbeiten ? null : el('button', { class: 'knopf klein', onclick: () => themaOverlay() }, icon('funken'), 'Neues Thema'))),
    el('div', { class: 'legende', style: { marginBottom: '12px' } },
      el('span', {}, el('span', { class: 'betont' }, 'Wort'), ' = betonen'), el('span', {}, el('span', { class: 'pause' }, '‖'), ' = kurze Pause'),
      el('span', {}, 'Die Betonung landet beim Schnitt automatisch in den Untertiteln.')),
    (S.skriptBearbeiten ? entwurf : sk).abschnitte.map((ab, n) => {
      const rolle = { hook: 'Hook · erste 3 Sekunden', mehrwert: 'Mehrwert', action: 'Action' }[ab.rolle] || ab.rolle;
      if (S.skriptBearbeiten) {
        const t = el('textarea', { class: 'feld', rows: 3, oninput: e => { ab.text = e.target.value; } });
        t.value = ab.text;
        const q = el('input', { class: 'feld', placeholder: 'Quelle zum Einblenden (wenn eine Zahl vorkommt)', style: { marginTop: '6px', padding: '6px 10px', fontSize: '12.5px' }, oninput: e => { ab.quelle = e.target.value; } });
        q.value = ab.quelle || '';
        return el('div', { class: `abschnitt ${ab.rolle}` }, el('div', { class: 'abschnitt-kopf' }, el('span', { class: 'rolle' }, rolle)), t, q);
      }
      return el('div', { class: `abschnitt ${ab.rolle}` },
        el('div', { class: 'abschnitt-kopf' }, el('span', { class: 'rolle' }, rolle),
          ab.quelle ? el('span', { class: 'chip quelle-chip', title: 'Wird im Motion-Video eingeblendet' }, 'Quelle: ' + ab.quelle) : null),
        el('div', { class: 'sprechtext' }, sprechtext(ab.text)));
    }),
    el('div', { class: 'zeile ende', style: { marginTop: '16px' } },
      S.skriptBearbeiten ? [
        el('span', { class: 'sehr-leise' }, '*Wort* betont · „ / “ kurze Pause'),
        el('span', { class: 'abstand' }),
        el('button', { class: 'knopf', onclick: () => { S.skriptBearbeiten = false; zeichne(); } }, 'Verwerfen'),
        el('button', { class: 'knopf voll', onclick: async () => {
          try { S.p = await api(`projekte/${S.p.id}/skript`, { methode: 'PUT', daten: { skript: entwurf } }); S.skriptBearbeiten = false; zeichne(); toast('Skript gespeichert.', 'gut'); } catch (e) { toast(e.message); }
        } }, icon('haken'), 'Speichern'),
      ] : el('button', { class: 'knopf voll', onclick: () => tabWechseln('aufnahme') }, 'Weiter zur Aufnahme', icon('pfeil'))));

  const rechts = el('div', {});
  if ((sk.pruefung || []).length) {
    rechts.append(el('div', { class: 'karte' },
      el('div', { class: 'karte-kopf' }, el('h3', {}, 'Selbstprüfung nach dem Regelwerk')),
      el('ul', { class: 'liste' }, sk.pruefung.map(p => el('li', { class: `pruef ${p.urteil}` },
        el('span', { class: 'pruef-zeichen' }, { ok: '✓', umformuliert: '↻', bitte_pruefen: '!' }[p.urteil] || '?'),
        el('div', {}, el('b', {}, p.aussage), p.hinweis ? el('span', {}, p.hinweis) : null))))));
  }
  if ((sk.quellen || []).length) {
    rechts.append(el('div', { class: 'karte' }, el('div', { class: 'karte-kopf' }, el('h3', {}, 'Quellen')),
      el('div', { class: 'liste' }, sk.quellen.map(q => el('div', { class: 'quelle' },
        el('b', {}, q.aussage), q.quelle, q.stand ? ` · Stand ${q.stand}` : '',
        q.link ? el('div', {}, el('a', { href: q.link, target: '_blank', rel: 'noopener' }, q.link)) : null)))));
  }
  if ((sk.annahmen || []).length) {
    rechts.append(el('div', { class: 'karte' }, el('div', { class: 'karte-kopf' }, el('h3', {}, 'Annahmen der Rechenbeispiele')),
      el('ul', { style: { margin: 0, paddingLeft: '18px', color: 'var(--text-2)' } }, sk.annahmen.map(a => el('li', {}, a)))));
  }
  if ((sk.hook_alternativen || []).length && !S.skriptBearbeiten) {
    rechts.append(el('div', { class: 'karte' }, el('div', { class: 'karte-kopf' }, el('h3', {}, 'Andere Hooks'), el('span', { class: 'sehr-leise' }, 'Klick tauscht')),
      el('div', { class: 'liste' }, sk.hook_alternativen.map((h, n) => el('button', { class: 'hook-alt', onclick: () => hookTauschen(n) }, h)))));
  }
  const sz = sk.schlagzeile || {};
  if (sz.gross) {
    const gross = sz.akzent && sz.gross.includes(sz.akzent)
      ? [sz.gross.split(sz.akzent)[0], el('em', {}, sz.akzent), sz.gross.split(sz.akzent).slice(1).join(sz.akzent)] : [sz.gross];
    rechts.append(el('div', { class: 'karte' }, el('div', { class: 'karte-kopf' }, el('h3', {}, 'Schlagzeile zur Hook')),
      el('div', { class: 'schlagzeile-vorschau' }, sz.klein ? el('small', {}, sz.klein) : null, el('strong', {}, gross))));
  }
  rechts.append(el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, el('h3', {}, 'Caption'), el('span', { class: 'abstand' }),
      el('button', { class: 'knopf klein', onclick: () => { navigator.clipboard.writeText(sk.caption || ''); toast('Caption kopiert.', 'gut'); } }, icon('kopie'), 'Kopieren')),
    el('div', { class: 'caption' }, sk.caption || ''),
    (sk.keywords || []).length ? el('div', { class: 'zeile', style: { marginTop: '10px' } }, sk.keywords.map(k => el('span', { class: 'chip' }, k))) : null,
    el('div', { class: 'sehr-leise', style: { marginTop: '10px' } }, 'Posten laut Plan zwischen 17 und 20 Uhr.')));

  f.append(el('div', { class: 'raster zwei' }, links, rechts));
}

async function hookTauschen(n) {
  const sk = JSON.parse(JSON.stringify(S.p.skript));
  const hook = sk.abschnitte.find(a => a.rolle === 'hook') || sk.abschnitte[0];
  const neu = sk.hook_alternativen[n];
  sk.hook_alternativen[n] = hook.text.replace(/\*/g, '').replace(/\s\/\s/g, ' ');
  hook.text = neu;
  try { S.p = await api(`projekte/${S.p.id}/skript`, { methode: 'PUT', daten: { skript: sk } }); zeichne(); toast('Hook getauscht.', 'gut'); } catch (e) { toast(e.message); }
}

// ===================================================================================== 2 · Aufnahme
const R = {
  modus: 'video', stream: null, rec: null, teile: [], blob: null, blobUrl: null, laeuft: false, start: 0, kamera: '', mikro: '',
  geraete: [], rahmen916: true, spiegel: true, tempo: 42, groesse: 30, prompterAn: true, prompterLaeuft: false, pos: 0,
  ctx: null, analyser: null, schleife: 0, zaehlt: false, fehler: null, hochladen: null, live: null,
};

function zeichneAufnahme(f) {
  const sk = S.p.skript;
  const kopf = el('div', { class: 'zeile', style: { marginBottom: '14px' } },
    wahl([['video', 'Video (Kamera + Mikro)'], ['ton', 'Nur Stimme (für Motion)']], R.modus, w => {
      if (R.laeuft) return;
      R.modus = w; verwerfen(); kameraAus(); zeichne();
    }),
    el('span', { class: 'abstand' }),
    geraeteWahl());

  const buehne = el('div', { class: `buehne ${R.modus === 'ton' ? 'ton' : ''}` });
  const leiste = el('div', { class: 'aufnahme-leiste' });

  if (R.blob) {
    // Ein Take ist im Kasten: ansehen, dann verwenden oder verwerfen
    const spieler = R.modus === 'video' ? el('video', { src: R.blobUrl, controls: true, playsinline: true }) : el('audio', { src: R.blobUrl, controls: true, style: { width: '86%', margin: '180px auto 0', display: 'block' } });
    buehne.append(spieler);
    if (R.modus === 'ton') buehne.append(el('div', { class: 'buehne-nachricht', style: { inset: '0 0 auto 0', paddingTop: '80px', placeItems: 'start center' } }, el('h2', {}, 'Probehören')));
  } else {
    if (R.fehler) buehne.append(el('div', { class: 'buehne-nachricht' }, el('div', {}, el('p', {}, R.fehler), el('button', { class: 'knopf voll', onclick: kameraAn }, 'Nochmal versuchen'))));
    if (R.modus === 'video') {
      if (!R.live) R.live = el('video', { muted: true, playsinline: true, autoplay: true });
      R.live.muted = true;
      R.live.className = R.spiegel ? 'spiegel' : '';
      buehne.append(R.live);
      if (R.stream) { R.live.srcObject = R.stream; R.live.play().catch(() => {}); }
      if (R.rahmen916) buehne.append(el('div', { class: 'rahmen-916' }, el('i')));
    } else {
      R.welle = el('div', { class: 'ton-welle' }, Array.from({ length: 28 }, () => el('i')));
      buehne.append(R.welle);
    }
    if (sk && R.prompterAn) buehne.append(prompterAnsicht(sk));
    if (!R.stream && !R.fehler) buehne.append(el('div', { class: 'buehne-nachricht' }, el('div', {}, el('p', {}, 'Kamera und Mikrofon werden eingeschaltet …'))));
    R.zaehler = el('div', { class: 'zaehler', hidden: true });
    buehne.append(R.zaehler);
  }

  if (R.blob) {
    leiste.append(
      el('button', { class: 'knopf', onclick: () => { verwerfen(); zeichne(); kameraAn(); } }, icon('neu'), 'Neu aufnehmen'),
      el('span', { class: 'abstand' }),
      R.hochladen !== null ? el('div', { class: 'balken', style: { width: '200px' } }, el('i', { style: { width: `${Math.round(R.hochladen * 100)}%` } })) : null,
      el('button', { class: 'knopf voll gross', onclick: takeVerwenden, disabled: R.hochladen !== null }, icon('haken'), 'Diesen Take verwenden'));
  } else {
    R.recKnopf = el('button', { class: `rec ${R.laeuft ? 'laeuft' : ''}`, title: R.laeuft ? 'Stopp' : 'Aufnahme starten', disabled: !R.stream, onclick: () => (R.laeuft ? aufnahmeStopp() : aufnahmeStart()) }, el('i'));
    R.uhrEl = el('span', { class: `uhr ${R.laeuft ? 'laeuft' : ''}` }, uhrzeit(R.laeuft ? (performance.now() - R.start) / 1000 : 0));
    R.pegelEl = el('i');
    leiste.append(R.recKnopf, R.uhrEl, el('div', { class: 'pegel', title: 'Pegel' }, R.pegelEl), el('span', { class: 'abstand' }),
      sk ? el('span', { class: 'sehr-leise', style: { color: '#ccc' } }, `Ziel ≈ ${uhrzeit((sk.woerter || 0) / 2.5)}`) : null);
  }
  buehne.append(leiste);

  const seite = el('div', { class: 'seitenleiste' });
  if (sk) {
    seite.append(el('div', { class: 'karte' },
      el('div', { class: 'karte-kopf' }, el('h3', {}, 'Teleprompter'), el('span', { class: 'abstand' }),
        el('button', { class: `knopf klein ${R.prompterAn ? 'an' : ''}`, onclick: () => { R.prompterAn = !R.prompterAn; zeichne(); } }, R.prompterAn ? 'An' : 'Aus')),
      el('div', { class: 'regler' }, el('div', { class: 'regler-kopf' }, el('span', {}, 'Tempo'), el('span', {}, `${R.tempo} px/s`)),
        el('input', { type: 'range', min: 10, max: 120, value: R.tempo, oninput: e => { R.tempo = +e.target.value; e.target.previousSibling.lastChild.textContent = `${R.tempo} px/s`; } })),
      el('div', { class: 'regler', style: { marginTop: '8px' } }, el('div', { class: 'regler-kopf' }, el('span', {}, 'Schriftgröße'), el('span', {}, `${R.groesse} px`)),
        el('input', { type: 'range', min: 20, max: 54, value: R.groesse, oninput: e => { R.groesse = +e.target.value; e.target.previousSibling.lastChild.textContent = `${R.groesse} px`; if (R.prompterText) R.prompterText.style.fontSize = R.groesse + 'px'; } })),
      el('div', { class: 'zeile', style: { marginTop: '10px' } },
        el('button', { class: 'knopf klein', onclick: () => { R.prompterLaeuft = !R.prompterLaeuft; } }, icon('play'), 'Lauf an/aus'),
        el('button', { class: 'knopf klein leise', onclick: () => { R.pos = 0; } }, icon('zurueck'), 'Von vorn')),
      el('div', { class: 'sehr-leise', style: { marginTop: '8px' } }, 'Läuft mit der Aufnahme los. Mausrad schiebt von Hand. Gold = betonen.')));
  } else {
    seite.append(el('div', { class: 'karte' }, el('h3', { style: { marginTop: 0 } }, 'Kein Skript'),
      el('p', { class: 'leise-text', style: { margin: '0 0 12px' } }, 'Mit Skript läuft hier ein Teleprompter mit den betonten Wörtern mit.'),
      el('button', { class: 'knopf klein', onclick: () => { tabWechseln('skript'); themaOverlay(); } }, icon('funken'), 'Thema reinwerfen')));
  }
  if (R.modus === 'video') {
    seite.append(el('div', { class: 'karte' }, el('h3', { style: { marginTop: 0 } }, 'Bild'),
      schalter('Reel-Rahmen 9:16', 'Zeigt, was im Hochformat bleibt', R.rahmen916, v => { R.rahmen916 = v; zeichne(); }),
      schalter('Vorschau spiegeln', 'Nur die Ansicht, die Aufnahme bleibt richtig herum', R.spiegel, v => { R.spiegel = v; if (R.live) R.live.className = v ? 'spiegel' : ''; })));
  }
  seite.append(ablage({
    titel: R.modus === 'video' ? 'Oder fertige Datei hineinziehen' : 'Oder Tondatei hineinziehen',
    text: R.modus === 'video' ? 'Handy-Video, MP4, MOV …' : 'WAV, MP3, M4A, OGG …',
    klein: true, annehmen: R.modus === 'video' ? 'video/*,audio/*' : 'audio/*,video/webm',
    beiDatei: async (datei, melden) => {
      const zweck = R.modus === 'video' && datei.type.startsWith('video') ? 'import' : 'ton';
      const antwort = await hochladen(S.p.id, zweck === 'ton' && R.modus === 'video' ? 'aufnahme' : zweck, datei, { fortschritt: melden, nurTon: zweck === 'ton' });
      S.p = antwort.projekt;
      toast('Datei ist im Projekt.', 'gut');
      kameraAus();
      tabWechseln(S.p.quelle && !S.p.quelle.nur_ton && zweck === 'import' ? 'schnitt' : 'motion');
    },
  }));
  if (S.p.quelle && !R.blob) {
    const q = S.p.quelle;
    seite.append(el('div', { class: 'karte' }, el('h3', { style: { marginTop: 0 } }, 'Im Projekt'),
      el('div', { class: 'sehr-leise' }, `${q.nur_ton ? 'Stimme' : 'Video'} · ${q.name || q.datei}${q.dauer ? ' · ' + sek(q.dauer) : ''}`),
      el('div', { class: 'zeile', style: { marginTop: '10px' } },
        el('button', { class: 'knopf klein voll', onclick: () => tabWechseln(q.nur_ton ? 'motion' : 'schnitt') }, q.nur_ton ? 'Zum Motion-Video' : 'Zum Schnitt', icon('pfeil')))));
  }

  f.append(kopf, el('div', { class: 'studio' }, buehne, seite));
  if (!R.stream && !R.blob && !R.fehler) kameraAn();
}

function geraeteWahl() {
  const art = R.modus === 'video' ? ['videoinput', 'audioinput'] : ['audioinput'];
  const listen = art.map(a => {
    const geraete = R.geraete.filter(g => g.kind === a);
    if (!geraete.length) return null;
    const wert = a === 'videoinput' ? R.kamera : R.mikro;
    return el('select', { class: 'feld', style: { width: 'auto', maxWidth: '240px' }, title: a === 'videoinput' ? 'Kamera' : 'Mikrofon', disabled: R.laeuft,
      onchange: e => { if (a === 'videoinput') R.kamera = e.target.value; else R.mikro = e.target.value; kameraAus(); kameraAn(); } },
    geraete.map((g, n) => el('option', { value: g.deviceId, selected: g.deviceId === wert }, (a === 'videoinput' ? '🎥 ' : '🎙 ') + (g.label || `Gerät ${n + 1}`))));
  });
  return el('div', { class: 'zeile' }, listen);
}

function prompterAnsicht(sk) {
  const box = el('div', { class: 'prompter' });
  const text = el('div', { class: 'prompter-text', style: { fontSize: R.groesse + 'px' } });
  for (const ab of sk.abschnitte) {
    text.append(el('span', { class: 'rolle-marke' }, { hook: 'HOOK', mehrwert: 'MEHRWERT', action: 'ACTION' }[ab.rolle] || ''), sprechtext(ab.text), ' ');
  }
  text.append(el('div', { style: { height: '60%' } }));
  box.append(text, el('div', { class: 'prompter-linie' }));
  box.addEventListener('wheel', e => { e.preventDefault(); R.pos = Math.max(0, R.pos + e.deltaY * 0.6); }, { passive: false });
  R.prompterBox = box;
  R.prompterText = text;
  return box;
}

async function kameraAn() {
  if (R.stream || R.startet || !navigator.mediaDevices) return;
  R.startet = true;
  try { await kameraHolen(); } finally { R.startet = false; }
}

async function kameraHolen() {
  R.fehler = null;
  const ton = { deviceId: R.mikro ? { exact: R.mikro } : undefined, echoCancellation: false, autoGainControl: false, noiseSuppression: true, channelCount: 1 };
  const wunsch = R.modus === 'video'
    ? { audio: ton, video: { deviceId: R.kamera ? { exact: R.kamera } : undefined, width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 } } }
    : { audio: ton };
  try {
    R.stream = await navigator.mediaDevices.getUserMedia(wunsch);
  } catch (e) {
    R.fehler = e.name === 'NotAllowedError' ? 'Der Browser darf Kamera oder Mikrofon nicht benutzen. Oben in der Adresszeile freigeben.'
      : e.name === 'NotFoundError' ? 'Keine Kamera oder kein Mikrofon gefunden.' : `Kamera/Mikrofon gehen nicht: ${e.message}`;
    if (S.tab === 'aufnahme') zeichne();
    return;
  }
  if (S.tab !== 'aufnahme') { kameraAus(); return; }
  try { R.geraete = await navigator.mediaDevices.enumerateDevices(); } catch { R.geraete = []; }
  const spur = id => R.stream.getTracks().find(t => t.kind === id);
  if (spur('video')) R.kamera = spur('video').getSettings().deviceId || R.kamera;
  if (spur('audio')) R.mikro = spur('audio').getSettings().deviceId || R.mikro;
  try {
    R.ctx = new AudioContext();
    R.analyser = R.ctx.createAnalyser();
    R.analyser.fftSize = 1024;
    R.ctx.createMediaStreamSource(R.stream).connect(R.analyser);
  } catch { R.analyser = null; }
  zeichne();
  schleife();
}

function kameraAus() {
  if (R.laeuft) aufnahmeStopp();
  cancelAnimationFrame(R.schleife);
  if (R.stream) R.stream.getTracks().forEach(t => t.stop());
  R.stream = null;
  if (R.live) R.live.srcObject = null;
  if (R.ctx) R.ctx.close().catch(() => {});
  R.ctx = null; R.analyser = null;
}

// Pegel, Wellenform, Uhr und Teleprompter in einem Takt
function schleife() {
  let zuletzt = performance.now();
  const daten = new Float32Array(1024);
  const freq = new Uint8Array(512);
  const takt = jetzt => {
    const dt = Math.min(0.1, (jetzt - zuletzt) / 1000);
    zuletzt = jetzt;
    if (R.analyser) {
      R.analyser.getFloatTimeDomainData(daten);
      let summe = 0;
      for (const x of daten) summe += x * x;
      const pegel = Math.min(1, Math.sqrt(summe / daten.length) * 4.5);
      if (R.pegelEl) R.pegelEl.style.width = `${Math.round(pegel * 100)}%`;
      if (R.welle && R.welle.isConnected) {
        R.analyser.getByteFrequencyData(freq);
        [...R.welle.children].forEach((b, n) => { b.style.height = `${6 + (freq[3 + n * 6] / 255) * 74}px`; });
      }
    }
    if (R.laeuft && R.uhrEl) R.uhrEl.textContent = uhrzeit((performance.now() - R.start) / 1000);
    if (R.prompterText && R.prompterText.isConnected) {
      if (R.prompterLaeuft) R.pos += R.tempo * dt;
      const h = R.prompterBox.clientHeight;
      R.prompterText.style.transform = `translateY(${(h / 2 - 20 - R.pos).toFixed(1)}px)`;
    }
    R.schleife = requestAnimationFrame(takt);
  };
  cancelAnimationFrame(R.schleife);
  R.schleife = requestAnimationFrame(takt);
}

function aufnahmeTyp() {
  const liste = R.modus === 'video'
    ? ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
    : ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
  return liste.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
}

async function aufnahmeStart() {
  if (!R.stream || R.laeuft || R.zaehlt) return;
  R.zaehlt = true;
  R.pos = 0;
  R.recKnopf.disabled = true;
  for (const n of [3, 2, 1]) {
    R.zaehler.hidden = false;
    R.zaehler.replaceChildren(el('span', {}, n));
    await new Promise(r => setTimeout(r, 900));
  }
  R.zaehler.hidden = true;
  R.zaehlt = false;
  const typ = aufnahmeTyp();
  R.teile = [];
  try {
    R.rec = new MediaRecorder(R.stream, { mimeType: typ, videoBitsPerSecond: 8_000_000, audioBitsPerSecond: 192_000 });
  } catch (e) { toast(`Aufnehmen geht nicht: ${e.message}`); R.recKnopf.disabled = false; return; }
  R.rec.ondataavailable = e => { if (e.data && e.data.size) R.teile.push(e.data); };
  R.rec.onstop = () => {
    R.laeuft = false;
    R.prompterLaeuft = false;
    R.blob = new Blob(R.teile, { type: (typ || 'video/webm').split(';')[0] });
    R.blobUrl = URL.createObjectURL(R.blob);
    kameraAus();
    zeichne();
  };
  R.rec.start(1000);
  R.laeuft = true;
  R.start = performance.now();
  R.prompterLaeuft = true;
  R.recKnopf.disabled = false;
  R.recKnopf.classList.add('laeuft');
  R.uhrEl.classList.add('laeuft');
}

function aufnahmeStopp() {
  if (R.rec && R.rec.state === 'recording') R.rec.stop();
}

function verwerfen() {
  if (R.blobUrl) URL.revokeObjectURL(R.blobUrl);
  R.blob = null; R.blobUrl = null; R.hochladen = null;
}

async function takeVerwenden() {
  if (!R.blob) return;
  R.hochladen = 0;
  zeichne();
  try {
    const nurTon = R.modus === 'ton';
    const antwort = await hochladen(S.p.id, 'aufnahme', R.blob, {
      name: nurTon ? 'stimme.webm' : 'aufnahme.webm', nurTon,
      fortschritt: x => { R.hochladen = x; const b = document.querySelector('.aufnahme-leiste .balken i'); if (b) b.style.width = `${Math.round(x * 100)}%`; },
    });
    S.p = antwort.projekt;
    verwerfen();
    listeLaden();
    toast(nurTon ? 'Stimme ist im Projekt.' : 'Aufnahme ist im Projekt.', 'gut');
    tabWechseln(nurTon ? 'motion' : 'schnitt');
  } catch (e) {
    R.hochladen = null;
    toast(e.message);
    zeichne();
  }
}

// ---- Ablagefläche (Ziehen und Ablegen oder Klicken)
function ablage({ titel, text, annehmen, beiDatei, klein = false }) {
  const eingabe = el('input', { type: 'file', accept: annehmen || '', hidden: true });
  const balken = el('div', { class: 'balken', hidden: true }, el('i', { style: { width: '0%' } }));
  const box = el('div', { class: `ablage ${klein ? 'klein' : ''}`, tabindex: 0 },
    el('div', { class: 'ablage-zeichen' }, icon('hoch')), el('b', {}, titel), el('span', {}, text), balken, eingabe);
  let beschaeftigt = false;
  const nehmen = async datei => {
    if (!datei || beschaeftigt) return;
    beschaeftigt = true;
    balken.hidden = false;
    try {
      await beiDatei(datei, x => { balken.firstChild.style.width = `${Math.round(x * 100)}%`; });
    } catch (e) { toast(e.message); }
    beschaeftigt = false;
    balken.hidden = true;
  };
  box.addEventListener('click', () => eingabe.click());
  box.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') eingabe.click(); });
  eingabe.addEventListener('change', () => nehmen(eingabe.files[0]));
  box.addEventListener('dragover', e => { e.preventDefault(); box.classList.add('drueber'); });
  box.addEventListener('dragleave', () => box.classList.remove('drueber'));
  box.addEventListener('drop', e => { e.preventDefault(); box.classList.remove('drueber'); nehmen(e.dataTransfer.files[0]); });
  return box;
}

// ===================================================================================== 3 · Schnitt
function zeichneSchnitt(f) {
  const p = S.p;
  if (!p.quelle || p.quelle.nur_ton) {
    f.append(el('div', { class: 'karte', style: { maxWidth: '760px', margin: '30px auto' } },
      p.quelle && p.quelle.nur_ton ? el('div', { class: 'warn-kasten', style: { marginTop: 0, marginBottom: '14px' } },
        'Im Projekt liegt nur eine Stimme. Daraus wird ein Motion-Video (Schritt 4). Zum Schneiden hier ein Video hineinziehen.') : null,
      ablage({
        titel: 'Video hier hineinziehen', text: 'Das Video wird geschnitten, und du siehst jeden Schritt. Oder in Schritt 2 direkt aufnehmen.',
        annehmen: 'video/*',
        beiDatei: async (datei, melden) => {
          const antwort = await hochladen(p.id, 'import', datei, { fortschritt: melden });
          S.p = antwort.projekt;
          listeLaden();
          zeichne();
        },
      }),
      el('div', { class: 'zeile', style: { justifyContent: 'center', marginTop: '14px' } },
        el('button', { class: 'knopf', onclick: () => tabWechseln('aufnahme') }, icon('kamera'), 'Lieber aufnehmen'))));
    return;
  }
  const laeuft = laeuftAuftrag('schnitt', 'aendern');
  const links = el('div', {});
  const zeigeAblauf = S.auftrag && ['schnitt', 'aendern'].includes(S.auftrag.art) && (!S.auftrag.fertig || !p.ergebnisse.length);
  if (zeigeAblauf || laeuft) {
    links.append(el('div', { class: 'karte' }, el('div', { class: 'karte-kopf' }, el('h2', {}, laeuft ? 'Wird geschnitten …' : 'Ablauf')),
      el('div', { 'data-ablauf': 'schnitt,aendern' }, ablaufAnsicht(['schnitt', 'aendern']))));
  }
  if (p.ergebnisse.length && !laeuft) links.append(ergebnisKarte());
  if (S.plan) links.append(el('div', { class: 'karte' }, el('div', { id: 'plan-ort' }, planAnsicht())));
  if (!links.children.length) {
    links.append(leerKarte('schere', 'Bereit zum Schneiden',
      'Pausen, Füllwörter und Versprecher fliegen raus, Untertitel kommen drauf. Die Betonung aus dem Skript landet in den Untertiteln, die Hook als Schlagzeile. Du siehst jeden Schritt mit.',
      el('button', { class: 'knopf voll gross', onclick: schneiden, disabled: laeuft }, icon('schere'), 'Jetzt schneiden')));
  }

  const rechts = el('div', {});
  const q = p.quelle;
  rechts.append(el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, el('h3', {}, 'Rohvideo'), el('span', { class: 'abstand' }),
      el('span', { class: 'sehr-leise' }, q.dauer ? sek(q.dauer) : '')),
    q.datei.endsWith('.webm') || q.datei.endsWith('.mp4') || q.datei.endsWith('.mov') || q.datei.endsWith('.m4v')
      ? el('video', { src: dateiUrl(q.datei), controls: true, preload: 'metadata', style: { width: '100%', maxHeight: '260px', background: '#000', borderRadius: '10px' } }) : null,
    el('div', { class: 'sehr-leise', style: { margin: '6px 0 10px' } }, q.name || q.datei),
    ablage({ titel: 'Anderes Video', text: 'hineinziehen oder klicken', klein: true, annehmen: 'video/*',
      beiDatei: async (datei, melden) => { const a = await hochladen(p.id, 'import', datei, { fortschritt: melden }); S.p = a.projekt; S.plan = null; listeLaden(); zeichne(); } })));

  const e = p.einstellungen;
  const setzen = async (k, v) => {
    e[k] = v;
    try { S.p = await api(`projekte/${p.id}/einstellungen`, { methode: 'PUT', daten: { [k]: v } }); } catch (f) { toast(f.message); }
    zeichne();
  };
  rechts.append(el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, el('h3', {}, 'So wird geschnitten')),
    el('div', { class: 'stile', style: { gridTemplateColumns: '1fr 1fr' } }, STIL_INFO.map(([id, name, text]) =>
      el('button', { class: `stil ${e.stil === id ? 'an' : ''}`, type: 'button', onclick: () => setzen('stil', id) }, el('b', {}, name), el('small', {}, text)))),
    el('div', { style: { marginTop: '14px' } }, el('span', { class: 'feld-titel' }, 'Format'),
      wahl([['original', 'Wie aufgenommen'], ['9:16', '9:16 Reel'], ['4:5', '4:5']], e.format, w => setzen('format', w))),
    el('div', { style: { marginTop: '12px' } },
      schalter('Betonung aus dem Skript', 'Die markierten Wörter leuchten im Untertitel', e.skript_betonung, v => setzen('skript_betonung', v), !p.skript),
      schalter('Hook als Schlagzeile', 'Große Zeile oben, solange die Hook läuft', e.schlagzeile, v => setzen('schlagzeile', v), !p.skript),
      p.vorbild && p.vorbild.vorschlag ? schalter('Takt vom Vorbild übernehmen', 'Pausenlänge, Format und Zoom wie im Vorbild', e.vorbild, v => setzen('vorbild', v)) : null),
    el('button', { class: 'knopf voll gross breit', style: { marginTop: '14px' }, onclick: schneiden, disabled: laeuft || !!(S.auftrag && !S.auftrag.fertig && !S.auftrag.fehler) },
      icon('schere'), p.ergebnisse.length ? 'Neu schneiden' : 'Schneiden'),
    !p.skript ? el('div', { class: 'sehr-leise', style: { marginTop: '8px' } }, 'Ohne Skript werden nur Zahlen betont.') : null));

  rechts.append(vorbildKarte());
  f.append(el('div', { class: 'raster zwei' }, links, rechts));
}

async function schneiden() {
  vormerkungLeeren();
  S.plan = null;
  await auftragStarten('schneiden', S.p.einstellungen, 'schnitt');
}

function ergebnisKarte() {
  const p = S.p;
  const liste = p.ergebnisse;
  const aktuell = liste.find(x => x.datei === S.fassung) || liste[liste.length - 1];
  const gespart = aktuell.vorher ? Math.round((1 - aktuell.dauer / aktuell.vorher) * 100) : 0;
  return el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, el('h2', {}, 'Fertiges Video'),
      el('span', { class: 'chip gruen' }, `${sek(aktuell.vorher)} → ${sek(aktuell.dauer)}`), gespart > 0 ? el('span', { class: 'chip' }, `−${gespart} %`) : null,
      el('span', { class: 'abstand' }),
      el('a', { class: 'knopf klein', href: dateiUrl(aktuell.datei), download: aktuell.datei.split('/').pop() }, icon('runter'), 'Herunterladen'),
      el('button', { class: 'knopf klein', onclick: () => api(`projekte/${p.id}/zeigen?datei=${encodeURIComponent(aktuell.datei)}`, { methode: 'POST' }).catch(e => toast(e.message)) }, icon('ordner'), 'Im Ordner')),
    el('video', { class: 'ergebnis-video', src: dateiUrl(aktuell.datei), controls: true, preload: 'metadata' }),
    (aktuell.warnungen || []).map(w => el('div', { class: 'warn-kasten' }, w)),
    aktuell.bilder && aktuell.bilder.length ? el('div', { class: 'standbilder' }, aktuell.bilder.map(b => el('img', { src: dateiUrl(b, true), alt: 'Standbild', loading: 'lazy' }))) : null,
    liste.length > 1 ? el('div', { class: 'fassungen' }, el('div', { class: 'klein-titel', style: { marginTop: '12px' } }, 'Fassungen'),
      [...liste].reverse().map((x, n) => el('button', { class: `fassung ${x === aktuell ? 'an' : ''}`, onclick: () => { S.fassung = x.datei; zeichne(); } },
        icon('film'), x.datei.split('/').pop(), el('span', { class: 'abstand' }), `${sek(x.dauer)} · ${x.wann.slice(11)}`, n === 0 ? el('span', { class: 'chip gold' }, 'neu') : null))) : null);
}

// Zeitleiste, Zahlen und Wortlaut des Schnittplans — mit Bearbeiten
function planAnsicht() {
  const pl = S.plan;
  if (!pl) return el('div');
  const v = S.vorgemerkt;
  const D = pl.dauer_roh || 1;
  const woerter = pl.woerter;

  // Gründe zählen: zusammenhängende Wörter gleichen Grundes sind eine Stelle (Füllwörter einzeln)
  const zaehlung = {};
  let vorher = null;
  for (const w of woerter) {
    if (w.weg && w.weg in GRUND && (w.weg === 'fuellwort' || w.weg !== vorher)) zaehlung[w.weg] = (zaehlung[w.weg] || 0) + 1;
    vorher = w.weg;
  }
  const imSegment = (a, b) => pl.segmente.reduce((s, x) => s + Math.max(0, Math.min(b, x.bis) - Math.max(a, x.von)), 0);
  let pausen = 0, pausenZeit = 0;
  for (let n = 1; n < woerter.length; n++) {
    const a = woerter[n - 1].bis, b = woerter[n].von;
    if (b - a > 0.3) { const weg = (b - a) - imSegment(a, b); if (weg > 0.15) { pausen++; pausenZeit += weg; } }
  }

  const zeitleiste = el('div', { class: 'zeitleiste', title: 'Gold bleibt, rot schraffiert fliegt raus' },
    pl.segmente.map((s, n) => el('i', { style: { left: `${(s.von / D) * 100}%`, width: `${Math.max(0.15, ((s.bis - s.von) / D) * 100)}%`, animationDelay: `${Math.min(n * 12, 600)}ms` } })));
  const skala = el('div', { class: 'zeitleiste-skala' }, [0, .25, .5, .75, 1].map(x => el('span', {}, uhrzeit(D * x))));

  const offen = pl.kandidaten.filter(k => !k.angewandt && !k.entschieden);
  const bearbeiten = S.modus !== 'ansehen';
  const transkript = el('div', { class: `transkript ${bearbeiten ? 'bearbeiten' : ''}` });
  const offenWoerter = new Set(offen.flatMap(k => Array.from({ length: k.bis - k.von + 1 }, (_, n) => k.von + n)));
  for (let n = 0; n < woerter.length; n++) {
    const w = woerter[n];
    if (n > 0) {
      const a = woerter[n - 1].bis, b = w.von;
      if (b - a > 0.3) {
        const weg = (b - a) - imSegment(a, b);
        if (weg > 0.15) transkript.append(el('span', { class: 'lueke', title: 'Pause, gekürzt' }, `✂ ${zahl(weg, 1)} s`));
        else if (b - a > 0.6) transkript.append(el('span', { class: 'lueke bleibt', title: 'Pause, bleibt' }, `‖ ${zahl(b - a, 1)} s`));
      }
    }
    let weg = w.weg, betont = w.betont, vorgemerkt = false;
    if (v.weg.has(w.i)) { weg = 'manuell'; vorgemerkt = true; }
    if (v.doch.has(w.i)) { weg = null; vorgemerkt = true; }
    if (v.betonen.has(w.i)) { betont = true; vorgemerkt = true; }
    if (v.unbetonen.has(w.i)) { betont = false; vorgemerkt = true; }
    const knoten = el('span', {
      class: `wort ${weg ? 'weg ' + weg : ''} ${betont && !weg ? 'betont' : ''} ${offenWoerter.has(w.i) ? 'offen' : ''} ${vorgemerkt ? 'vorgemerkt' : ''}`,
      title: `${w.i} · ${zahl(w.von, 2)} s${w.weg ? ' · ' + (GRUND[w.weg] || w.weg) : ''}`,
      onclick: bearbeiten ? () => wortKlick(w) : null,
    }, w.w);
    transkript.append(knoten, ' ');
  }

  const anzahl = Object.values(v).reduce((s, x) => s + x.size, 0);
  return el('div', {},
    el('div', { class: 'karte-kopf' }, el('h2', {}, 'Schnittplan'), el('span', { class: 'abstand' }),
      wahl([['ansehen', 'Ansehen'], ['schneiden', 'Schneiden'], ['betonen', 'Betonen']], S.modus, m => { S.modus = m; $('#plan-ort').replaceChildren(planAnsicht()); })),
    zeitleiste, skala,
    el('div', { class: 'zahlen' },
      el('div', { class: 'zahl-kachel' }, el('b', {}, sek(pl.dauer_roh)), el('span', {}, 'Rohvideo')),
      el('div', { class: 'zahl-kachel gold' }, el('b', {}, sek(pl.dauer_ergebnis)), el('span', {}, 'fertig')),
      el('div', { class: 'zahl-kachel' }, el('b', {}, `−${Math.max(0, Math.round((1 - pl.dauer_ergebnis / D) * 100))} %`), el('span', {}, `${sek(D - pl.dauer_ergebnis)} gekürzt`)),
      el('div', { class: 'zahl-kachel' }, el('b', {}, woerter.filter(w => w.betont && !w.weg).length), el('span', {}, 'betonte Wörter'))),
    el('div', { class: 'gruende', style: { marginBottom: '12px' } },
      pausen ? el('span', { class: 'chip rot' }, `${pausen} Pausen gekürzt · ${sek(pausenZeit)}`) : null,
      Object.entries(zaehlung).map(([g, n]) => el('span', { class: `chip ${g === 'fuellwort' ? 'rot' : g === 'manuell' ? 'gelb' : 'blau'}` }, `${n} ${GRUND[g]}`)),
      (pl.schlagzeilen || []).length ? el('span', { class: 'chip gold' }, `${pl.schlagzeilen.length} Schlagzeile`) : null),
    offen.length ? el('div', { class: 'liste', style: { marginBottom: '12px' } },
      el('div', { class: 'klein-titel' }, 'Unsicher, nicht geschnitten. Du entscheidest:'),
      offen.map(k => {
        const text = woerter.slice(k.von, k.bis + 1).map(w => w.w).join(' ');
        const an = v.annehmen.has(k.id), ab = v.ablehnen.has(k.id);
        return el('div', { class: 'kandidat' }, el('span', { class: 'chip gelb' }, GRUND[k.art] || k.art), el('q', {}, text),
          el('button', { class: `knopf klein ${an ? 'an' : ''}`, onclick: () => { ab && v.ablehnen.delete(k.id); an ? v.annehmen.delete(k.id) : v.annehmen.add(k.id); $('#plan-ort').replaceChildren(planAnsicht()); } }, 'Raus'),
          el('button', { class: `knopf klein ${ab ? 'an' : ''}`, onclick: () => { an && v.annehmen.delete(k.id); ab ? v.ablehnen.delete(k.id) : v.ablehnen.add(k.id); $('#plan-ort').replaceChildren(planAnsicht()); } }, 'Drin lassen'));
      })) : null,
    el('div', { class: 'legende', style: { marginBottom: '6px' } },
      el('span', {}, el('span', { class: 'wort weg fuellwort' }, 'äh'), ' Füllwort'),
      el('span', {}, el('span', { class: 'wort weg wiederholung' }, 'so so'), ' Wiederholung/Anlauf'),
      el('span', {}, el('span', { class: 'lueke' }, '✂ 0,8 s'), ' Pause gekürzt'),
      el('span', {}, el('span', { class: 'wort betont' }, 'Wort'), ' betont'),
      bearbeiten ? el('span', { style: { color: 'var(--gold-2)' } }, S.modus === 'schneiden' ? 'Klick: Wort raus / wieder rein' : 'Klick: Betonung an / aus') : null),
    transkript,
    anzahl ? el('div', { class: 'aenderungs-leiste' }, icon('stift'), el('b', {}, `${anzahl} Änderung${anzahl === 1 ? '' : 'en'} vorgemerkt`),
      el('span', { class: 'abstand' }),
      el('button', { class: 'knopf klein', onclick: () => { vormerkungLeeren(); $('#plan-ort').replaceChildren(planAnsicht()); } }, 'Verwerfen'),
      el('button', { class: 'knopf voll', onclick: aenderungenAnwenden, disabled: !!(S.auftrag && !S.auftrag.fertig && !S.auftrag.fehler) }, icon('schere'), 'Anwenden und neu rendern')) : null);
}

function wortKlick(w) {
  const v = S.vorgemerkt;
  const umschalten = (menge, wert) => (menge.has(wert) ? menge.delete(wert) : menge.add(wert));
  if (S.modus === 'schneiden') umschalten(w.weg ? v.doch : v.weg, w.i);
  else if (S.modus === 'betonen') umschalten(w.betont ? v.unbetonen : v.betonen, w.i);
  const ort = $('#plan-ort');
  const scroll = ort.querySelector('.transkript').scrollTop;
  ort.replaceChildren(planAnsicht());
  ort.querySelector('.transkript').scrollTop = scroll;
}

async function aenderungenAnwenden() {
  const v = S.vorgemerkt;
  const daten = Object.fromEntries(Object.entries(v).map(([k, s]) => [k, [...s]]));
  if (await auftragStarten('aendern', daten, 'aendern')) vormerkungLeeren();
}

function vorbildKarte() {
  const p = S.p;
  const vb = p.vorbild;
  const laeuft = laeuftAuftrag('vorbild');
  const karte = el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, icon('auge'), el('h3', {}, 'Vorbild'), el('span', { class: 'sehr-leise' }, 'So soll es aussehen')));
  if (laeuft || (S.auftrag && S.auftrag.art === 'vorbild' && S.auftrag.fehler)) karte.append(el('div', { 'data-ablauf': 'vorbild' }, ablaufAnsicht(['vorbild'])));
  if (vb && vb.messung && !laeuft) {
    const m = vb.messung, s = m.sprache || {}, vs = vb.vorschlag || {};
    karte.append(
      el('div', { class: 'vorbild-bilder', style: { gridTemplateColumns: `repeat(${Math.min(6, vb.bilder.length)}, 1fr)` } }, vb.bilder.map(b => el('img', { src: dateiUrl(b, true), alt: 'Standbild des Vorbilds', loading: 'lazy' }))),
      el('dl', { class: 'werte' },
        el('dt', {}, 'Format'), el('dd', {}, `${m.breite}×${m.hoehe}${vs.bild && vs.bild.format ? ' → ' + vs.bild.format : ''}`),
        el('dt', {}, 'Schnitt-Takt'), el('dd', {}, `${zahl(m.bildwechsel_je_minute, 1)} Bildwechsel je Minute`),
        s.woerter_je_minute ? [el('dt', {}, 'Sprechtempo'), el('dd', {}, `${s.woerter_je_minute} Wörter je Minute`)] : null,
        vs.schnitt ? [el('dt', {}, 'Pausen'), el('dd', {}, `ab ${zahl(vs.schnitt.pause_ab, 2)} s auf ${zahl(vs.schnitt.pause_ziel, 2)} s kürzen`)] : null,
        m.lautheit_lufs !== null && m.lautheit_lufs !== undefined ? [el('dt', {}, 'Lautheit'), el('dd', {}, `${zahl(m.lautheit_lufs, 1)} LUFS`)] : null),
      el('div', { class: 'sehr-leise', style: { margin: '8px 0' } }, 'Gemessen werden Takt, Pausen und Format. Schrift und Farben der Untertitel kommen aus dem gewählten Stil.'));
  }
  if (!laeuft) {
    karte.append(ablage({
      titel: vb ? 'Anderes Vorbild' : 'Vorbild-Video hineinziehen', text: 'Ein Reel, das dir gefällt', klein: true, annehmen: 'video/*',
      beiDatei: async (datei, melden) => {
        const a = await hochladen(p.id, 'vorbild', datei, { fortschritt: melden });
        S.p = a.projekt;
        await auftragStarten('vorbild', {}, 'vorbild');
      },
    }));
  }
  return karte;
}

// ===================================================================================== 4 · Motion
const THEMEN = [
  ['nacht', 'Nachtblau & Gold', ['#0B1020', '#F3EEE3', '#E8B44C']],
  ['papier', 'Papier & Grün', ['#F4F1EA', '#14201A', '#1F8A5B']],
  ['kontrast', 'Schwarz & Orange', ['#0A0A0A', '#F5F5F0', '#FF5A1F']],
];

function zeichneMotion(f) {
  const p = S.p;
  const m = p.motion || {};
  const einst = { thema: 'nacht', handle: '', ton_aus_aufnahme: false, ...(m.einstellungen || {}) };
  if (!m.ton_roh && p.quelle) einst.ton_aus_aufnahme = true;
  const laeuft = laeuftAuftrag('motion');
  const tonDa = !!(m.ton_roh || p.quelle);

  const rechts = el('div', {});
  rechts.append(el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, icon('mikro'), el('h3', {}, 'Deine Stimme'), el('span', { class: 'sehr-leise' }, 'keine KI-Stimme')),
    m.ton_roh ? el('div', {}, el('audio', { src: dateiUrl(m.ton_roh), controls: true, preload: 'metadata', style: { width: '100%' } }),
      el('div', { class: 'sehr-leise' }, m.ton_roh.split('/').pop())) : null,
    p.quelle && !p.quelle.nur_ton ? schalter('Ton aus der Video-Aufnahme nehmen', p.quelle.name || p.quelle.datei, einst.ton_aus_aufnahme || !m.ton_roh, v => { einst.ton_aus_aufnahme = v; m.einstellungen = einst; }, !m.ton_roh) : null,
    !tonDa ? el('p', { class: 'leise-text', style: { margin: '0 0 10px' } }, 'Sprich das Skript ein. Pausen und Versprecher schneidet das Werkzeug raus.') : null,
    el('div', { class: 'zeile', style: { margin: '10px 0' } },
      el('button', { class: 'knopf klein', onclick: () => { R.modus = 'ton'; verwerfen(); tabWechseln('aufnahme'); } }, icon('mikro'), m.ton_roh ? 'Neu einsprechen' : 'Stimme aufnehmen')),
    ablage({ titel: 'Oder Tondatei hineinziehen', text: 'WAV, MP3, M4A …', klein: true, annehmen: 'audio/*,video/*',
      beiDatei: async (datei, melden) => { const a = await hochladen(p.id, 'ton', datei, { fortschritt: melden }); S.p = a.projekt; listeLaden(); zeichne(); } })));

  const themaWahl = el('div', { class: 'themen' }, THEMEN.map(([id, name, farben]) =>
    el('button', { class: `thema-knopf ${einst.thema === id ? 'an' : ''}`, type: 'button', onclick: () => { einst.thema = id; m.einstellungen = einst; S.p.motion = m; zeichne(); } },
      el('i', {}, farben.map(c => el('b', { style: { background: c } }))), name)));
  const handle = el('input', { class: 'feld', placeholder: '@dein.handle (freiwillig)', oninput: e => { einst.handle = e.target.value; m.einstellungen = einst; S.p.motion = m; } });
  handle.value = einst.handle || '';
  rechts.append(el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, el('h3', {}, 'Aussehen')),
    themaWahl,
    el('div', { style: { marginTop: '12px' } }, el('span', { class: 'feld-titel' }, 'Name im Bild'), handle),
    el('div', { class: 'sehr-leise', style: { marginTop: '10px' } },
      p.skript ? `Abschnitte, Betonung und Quellen kommen aus dem Skript „${p.skript.titel}“. Am Ende: Kommentar-Frage${(p.skript.eingabe || {}).dm ? ' bzw. DM-Trigger' : ''} und „Keine individuelle Beratung“.`
        : 'Ohne Skript gibt es keine Abschnitte und keine Quellen-Einblendung, betont werden nur Zahlen.'),
    el('button', { class: 'knopf voll gross breit', style: { marginTop: '14px' }, disabled: laeuft || !tonDa || !!(S.auftrag && !S.auftrag.fertig && !S.auftrag.fehler),
      onclick: () => { S.vorschau = null; auftragStarten('motion', einst, 'motion'); } }, icon('film'), m.ergebnis ? 'Neu bauen' : 'Motion-Video bauen'),
    S.zustand && !(S.zustand.node && S.zustand.browser) ? el('div', { class: 'warn-kasten' }, 'Für Motion-Videos fehlen Node oder Edge/Chrome.') : null));
  if (S.auftrag && S.auftrag.art === 'motion') {
    rechts.append(el('div', { class: 'karte' }, el('div', { class: 'karte-kopf' }, el('h3', {}, laeuft ? 'Wird gebaut …' : 'Ablauf')),
      el('div', { 'data-ablauf': 'motion' }, ablaufAnsicht(['motion']))));
  }

  const links = el('div', {});
  if (!S.vorschau && m.daten && m.ton) S.vorschau = { daten: m.daten, ton: m.ton };
  links.append(el('div', { class: 'karte' },
    el('div', { class: 'karte-kopf' }, el('h2', {}, 'Vorschau'), el('span', { class: 'sehr-leise' }, 'live im Browser, vor dem Ablichten')),
    el('div', { id: 'vorschau-ort' }, vorschauAnsicht())));
  if (m.ergebnis && !laeuft) {
    links.append(el('div', { class: 'karte' },
      el('div', { class: 'karte-kopf' }, el('h2', {}, 'Fertiges Motion-Video'), el('span', { class: 'chip gruen' }, sek(m.ergebnis.dauer)),
        el('span', { class: 'abstand' }),
        el('a', { class: 'knopf klein', href: dateiUrl(m.ergebnis.datei), download: m.ergebnis.datei.split('/').pop() }, icon('runter'), 'Herunterladen'),
        el('button', { class: 'knopf klein', onclick: () => api(`projekte/${p.id}/zeigen?datei=${encodeURIComponent(m.ergebnis.datei)}`, { methode: 'POST' }).catch(e => toast(e.message)) }, icon('ordner'), 'Im Ordner')),
      el('video', { class: 'ergebnis-video', src: dateiUrl(m.ergebnis.datei, true), controls: true, preload: 'metadata', style: { maxHeight: '620px' } })));
  }
  if (S.motionPlan) links.append(el('div', { class: 'karte' }, el('div', { id: 'motion-plan-ort' }, motionPlanAnsicht())));
  f.append(el('div', { class: 'motion-raster' }, links, rechts));
}

function motionPlanAnsicht() {
  const pl = S.motionPlan;
  if (!pl) return el('div');
  const D = pl.dauer_roh || 1;
  return el('div', {},
    el('div', { class: 'karte-kopf' }, el('h3', {}, 'Stimme geschnitten'), el('span', { class: 'chip gruen' }, `${sek(pl.dauer_roh)} → ${sek(pl.dauer_ergebnis)}`)),
    el('div', { class: 'zeitleiste' }, pl.segmente.map(s => el('i', { style: { left: `${(s.von / D) * 100}%`, width: `${Math.max(0.15, ((s.bis - s.von) / D) * 100)}%` } }))),
    el('div', { class: 'transkript', style: { maxHeight: '160px', fontSize: '14px', marginTop: '10px' } },
      pl.woerter.map(w => [el('span', { class: `wort ${w.weg ? 'weg ' + w.weg : ''} ${w.betont && !w.weg ? 'betont' : ''}` }, w.w), ' '])));
}

// ---- Live-Vorschau: die Szenen-Seite im iframe, angetrieben vom geschnittenen Ton
const V = { ton: null, iframe: null, raf: 0, regler: null, zeit: null, knopf: null };

function vorschauAnsicht() {
  vorschauStopp();
  if (!S.vorschau) {
    return el('div', { class: 'leer', style: { padding: '40px 10px' } },
      el('div', { class: 'leer-zeichen' }, icon('film')),
      el('p', { style: { marginTop: '14px' } }, laeuftAuftrag('motion') ? 'Die Vorschau erscheint, sobald die Stimme geschnitten ist.' : 'Hier läuft die Grafik im Takt deiner Stimme, sobald du auf „Motion-Video bauen“ klickst.'));
  }
  const breite = 300, massstab = breite / 1080;
  const rahmen = el('div', { class: 'vorschau-rahmen', style: { width: `${breite}px`, height: `${1920 * massstab}px` } });
  const iframe = el('iframe', { title: 'Vorschau des Motion-Videos', style: { transform: `scale(${massstab})` } });
  rahmen.append(iframe);
  const ton = el('audio', { src: dateiUrl(S.vorschau.ton, true), preload: 'auto' });
  V.ton = ton; V.iframe = iframe;
  V.knopf = el('button', { class: 'knopf klein', onclick: () => (ton.paused ? ton.play() : ton.pause()) }, icon('play'));
  V.regler = el('input', { type: 'range', min: 0, max: 1000, value: 0, oninput: e => { if (ton.duration) { ton.currentTime = (e.target.value / 1000) * ton.duration; vorschauBild(); } } });
  V.zeit = el('span', { class: 'sehr-leise', style: { fontFamily: 'var(--mono)' } }, '0:00');
  ton.addEventListener('play', () => { V.knopf.replaceChildren(icon('pause')); vorschauTakt(); });
  ton.addEventListener('pause', () => { V.knopf.replaceChildren(icon('play')); cancelAnimationFrame(V.raf); });
  ton.addEventListener('ended', () => { V.knopf.replaceChildren(icon('play')); });
  fetch(dateiUrl(S.vorschau.daten, true)).then(r => r.json()).then(d => {
    window.MOTION_DATEN = d;
    iframe.addEventListener('load', () => vorschauBild(), { once: true });
    iframe.src = '/motion.html?vorschau=' + Date.now();
  }).catch(() => toast('Die Vorschau-Daten fehlen.'));
  return el('div', {}, rahmen, el('div', { class: 'vorschau-leiste', style: { width: '300px', margin: '12px auto 0' } }, V.knopf, V.regler, V.zeit), ton);
}

function vorschauBild() {
  const w = V.iframe && V.iframe.contentWindow;
  if (!w || typeof w.zeit !== 'function' || !V.ton) return;
  const t = V.ton.currentTime || 0;
  try { w.zeit(t); } catch (e) { console.error(e); }
  if (V.ton.duration) V.regler.value = Math.round((t / V.ton.duration) * 1000);
  V.zeit.textContent = uhrzeit(t);
}

function vorschauTakt() {
  cancelAnimationFrame(V.raf);
  const takt = () => { vorschauBild(); if (V.ton && !V.ton.paused) V.raf = requestAnimationFrame(takt); };
  V.raf = requestAnimationFrame(takt);
}

function vorschauStopp() {
  cancelAnimationFrame(V.raf);
  if (V.ton) { V.ton.pause(); V.ton = null; }
}

start();
