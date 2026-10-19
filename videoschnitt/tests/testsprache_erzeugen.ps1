<#
  fixture-erzeugen.ps1 - Testaufnahme mit bekannter Wahrheit fuer den Video-Cutter.

  Spricht einen festen deutschen Text mit der SAPI-Stimme (Standard: Microsoft Hedda Desktop)
  und schreibt   <Name>.wav            16 kHz, mono, 16 Bit
                 <Name>.wahrheit.json  UTF-8 ohne BOM, alle Zeiten in Millisekunden ab Dateianfang

  Aufruf (PowerShell 5.1, kein Download, kein Netz, laeuft unter einer Sekunde):
    powershell -NoProfile -ExecutionPolicy Bypass -File fixture-erzeugen.ps1 -Zielordner C:\irgendwo
    optional: -Name fixture  -Stimme "Microsoft Hedda Desktop"  -Rate 16000  -Tempo 0  -Schwelle 60

  Diese Datei ist absichtlich reines ASCII. Umlaute stehen als {ae} {oe} {ue} {Ae} {Oe} {Ue} {ss}
  und werden zur Laufzeit aus Codepunkten gebaut. Damit ist egal, ob die Datei mit oder ohne BOM
  gespeichert wird (PowerShell 5.1 liest UTF-8 ohne BOM sonst als ANSI und zerstoert Umlaute).

  Wie die Wahrheit entsteht:
    1. Der ganze Text geht als EIN SSML-Dokument an SAPI, Pausen als <break time="...ms"/>,
       zwischen allen Teilen steht eine <mark/>. SAPI meldet die Stelle jeder Marke im Audiostrom.
    2. SAPI haengt an jedes Satzende von sich aus rund 0,86 s Stille an. Eine Pause nach einem Satz
       waere deshalb laenger als verlangt. Das Skript sucht jede Pause in den Proben und schneidet
       sie auf genau soll_ms zurecht (SAPI liefert digitale Stille, das geht auf die Probe genau).
    3. Kanten an einer Stille kommen aus den Proben (genau). Kanten mitten im Redefluss kommen aus den
       Wort-Ereignissen von SAPI (etwa +-15 ms). Die <mark/>-Stellen selbst liegen 50-90 ms zu frueh.
#>
param(
  [Parameter(Mandatory = $true)][string]$Zielordner,
  [string]$Name = 'fixture',
  [string]$Stimme = 'Microsoft Hedda Desktop',
  [int]$Rate = 16000,
  [int]$Tempo = 0,
  [int]$Schwelle = 60
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech

# ---------- Umlaute aus Codepunkten ----------
function Uml([string]$s) {
  $s = $s.Replace('{ae}', [string][char]0x00E4).Replace('{oe}', [string][char]0x00F6).Replace('{ue}', [string][char]0x00FC)
  $s = $s.Replace('{Ae}', [string][char]0x00C4).Replace('{Oe}', [string][char]0x00D6).Replace('{Ue}', [string][char]0x00DC)
  $s = $s.Replace('{ss}', [string][char]0x00DF)
  return $s
}

# ---------- Bausteine ----------
# Teil = gesprochener Teil, Stille = Pause. entfernen = soll ein perfekter Cutter das herausschneiden?
# Achtung bei Namen: 'R' ist in PowerShell ein Alias (Invoke-History) und gewinnt gegen Funktionen,
# 'Pause' ist eine eingebaute Funktion. Deshalb heissen die Helfer Uml, Teil, Stille, Rund.
function Teil([string]$art, [string]$text, [bool]$entfernen, [string]$hinweis = '') {
  return [ordered]@{ art = $art; text = (Uml $text); entfernen = $entfernen; hinweis = (Uml $hinweis) }
}
function Stille([int]$ms, [bool]$entfernen, [string]$hinweis = '') {
  return [ordered]@{ art = 'pause'; soll_ms = $ms; entfernen = $entfernen; hinweis = (Uml $hinweis) }
}

$teile = @(
  # (a) zwei normale Saetze
  (Teil 'normal' 'Hallo und willkommen zu diesem Video.' $false 'a: normaler Satz 1'),
  (Teil 'normal' 'Heute sprechen wir {ue}ber ein wichtiges Thema.' $false 'a: normaler Satz 2'),
  (Stille 2000 $true 'c: lange Pause 1 zwischen S{ae}tzen'),

  # (b) Fuellwoerter als Woerter im Satz (2x aehm, 3x aeh)
  (Teil 'normal' 'Also,' $false 'b'),
  (Teil 'fuellwort' '{ae}hm,' $true 'b: F{ue}llwort 1'),
  (Teil 'normal' 'ich m{oe}chte euch heute zeigen, wie man' $false 'b'),
  (Teil 'fuellwort' '{ae}h,' $true 'b: F{ue}llwort 2'),
  (Teil 'normal' 'richtig Geld spart.' $false 'b'),
  (Teil 'normal' 'Das ist' $false 'b'),
  (Teil 'fuellwort' '{ae}hm,' $true 'b: F{ue}llwort 3'),
  (Teil 'normal' 'eigentlich ganz einfach, aber' $false 'b'),
  (Teil 'fuellwort' '{ae}h,' $true 'b: F{ue}llwort 4'),
  (Teil 'normal' 'viele machen es falsch.' $false 'b'),
  (Teil 'fuellwort' '{Ae}h,' $true 'b: F{ue}llwort 5 am Satzanfang'),
  (Teil 'normal' 'fangen wir also an.' $false 'b'),
  (Stille 1500 $true 'c: lange Pause 2 zwischen S{ae}tzen'),

  # (c) lange Pause mitten im Satz
  (Teil 'normal' 'Der erste Schritt ist' $false 'c: Satz mit Pause in der Mitte, Teil 1'),
  (Stille 2200 $true 'c: lange Pause mitten im Satz'),
  (Teil 'normal' 'ein Haushaltsbuch zu f{ue}hren.' $false 'c: Satz mit Pause in der Mitte, Teil 2'),

  # (d) direkte Wiederholung / Stotter-Neustart
  (Teil 'wiederholung' 'Wir haben' $true 'd: erstes "wir haben" ist doppelt'),
  (Teil 'normal' 'wir haben heute ein neues Thema.' $false 'd'),
  (Stille 2500 $true 'c: lange Pause 3 zwischen S{ae}tzen'),

  # (e) abgebrochener Anlauf, mit denselben Anfangsworten neu begonnen
  (Teil 'neuansatz' 'Der wichtigste Punkt ist, dass man' $true 'e: abgebrochener Anlauf'),
  (Stille 700 $true 'e: kurze Denkpause nach dem Abbruch (geh{oe}rt zum Abbruch)'),
  (Teil 'normal' 'Der wichtigste Punkt ist, dass man jeden Tag {ue}bt.' $false 'e: vollst{ae}ndiger Satz'),

  # (f) ganzer Satz zweimal fast gleich (Retake) - die erste Fassung faellt weg
  (Teil 'doppelter_satz' 'Am Ende z{ae}hlt nur, was {ue}brig bleibt.' $true 'f: erste Fassung'),
  (Stille 900 $true 'f: Pause zwischen den beiden Fassungen'),
  (Teil 'doppelter_satz' 'Am Ende z{ae}hlt nur, was wirklich {ue}brig bleibt.' $false 'f: zweite Fassung bleibt'),

  # (g) gewollte Anapher - darf NICHT geschnitten werden
  (Teil 'anapher' 'Ich will mehr Zeit.' $false 'g: gewollt, bleibt'),
  (Teil 'anapher' 'Ich will mehr Geld.' $false 'g: gewollt, bleibt'),

  # (h) langes zusammengesetztes Wort
  (Teil 'normal' 'Deshalb ist eine' $false 'h'),
  (Teil 'langes_wort' 'Berufsunf{ae}higkeitsversicherung' $false 'h'),
  (Teil 'normal' 'so wichtig.' $false 'h'),
  (Stille 1800 $true 'c: lange Pause 4 zwischen S{ae}tzen'),

  # (i) Schlusssatz
  (Teil 'normal' 'Vielen Dank und bis zum n{ae}chsten Mal.' $false 'i: Schlusssatz')
)

# Selbstpruefung: stehen wirklich Umlaute im Text?
$alles = ($teile | Where-Object { $_.art -ne 'pause' } | ForEach-Object { $_.text }) -join ' '
foreach ($cp in 0x00E4, 0x00F6, 0x00FC, 0x00C4) {
  if ($alles.IndexOf([char]$cp) -lt 0) { throw ("Umlaut U+{0:X4} fehlt im Text - Kodierung kaputt?" -f $cp) }
}

# ---------- SSML bauen: Marke m0 | Teil 0 | Marke m1 | Teil 1 | ... | Marke mN ----------
$sb = New-Object System.Text.StringBuilder
[void]$sb.Append('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="de-DE">')
$ssmlVon = @(); $ssmlBis = @()
for ($i = 0; $i -lt $teile.Count; $i++) {
  [void]$sb.Append(('<mark name="m{0}"/>' -f $i))
  $t = $teile[$i]
  $ssmlVon += $sb.Length
  # Wichtig: Pausen nur in Millisekunden angeben. time="2.2s" wird auf deutschem Windows zu 22 Sekunden.
  if ($t.art -eq 'pause') { [void]$sb.Append(('<break time="{0}ms"/>' -f $t.soll_ms)) }
  else { [void]$sb.Append([System.Security.SecurityElement]::Escape($t.text)).Append(' ') }
  $ssmlBis += $sb.Length
}
[void]$sb.Append(('<mark name="m{0}"/>' -f $teile.Count))
[void]$sb.Append('</speak>')
$ssml = $sb.ToString()

# ---------- Helfer in C# (Ereignisse einsammeln, Proben messen, WAV schreiben) ----------
if (-not ('CutterFixtureHelfer3' -as [type])) {
  Add-Type -ReferencedAssemblies 'System.Speech' -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Generic;
using System.Speech.Synthesis;

public class CutterFixtureHelfer3
{
    public List<string> Marken = new List<string>();
    public List<double> MarkenMs = new List<double>();
    public List<string> Woerter = new List<string>();
    public List<double> WoerterMs = new List<double>();
    public List<int> WoerterPos = new List<int>();
    public int Rate;
    public short[] Proben;

    public void Anhaengen(SpeechSynthesizer s)
    {
        s.BookmarkReached += delegate(object o, BookmarkReachedEventArgs e)
        { Marken.Add(e.Bookmark); MarkenMs.Add(e.AudioPosition.TotalMilliseconds); };
        s.SpeakProgress += delegate(object o, SpeakProgressEventArgs e)
        { Woerter.Add(e.Text); WoerterMs.Add(e.AudioPosition.TotalMilliseconds); WoerterPos.Add(e.CharacterPosition); };
    }

    public void SetzeRohdaten(byte[] pcm, int rate)
    {
        Rate = rate;
        Proben = new short[pcm.Length / 2];
        Buffer.BlockCopy(pcm, 0, Proben, 0, Proben.Length * 2);
    }

    public double DauerMs() { return Proben.Length * 1000.0 / Rate; }
    public double Ms(long probe) { return probe * 1000.0 / Rate; }
    public int Idx(double ms) { long i = (long)Math.Round(ms * Rate / 1000.0); if (i < 0) i = 0; if (i > Proben.Length) i = Proben.Length; return (int)i; }
    bool Laut(int i, int schwelle) { return Proben[i] > schwelle || Proben[i] < -schwelle; }

    // erste laute Probe in [vonMs, bisMs) als ms, -1 wenn keine
    public double ErsteLaute(double vonMs, double bisMs, int schwelle)
    {
        int a = Idx(vonMs), e = Idx(bisMs);
        for (int i = a; i < e; i++) if (Laut(i, schwelle)) return Ms(i);
        return -1;
    }

    // Ende der letzten lauten Probe in [vonMs, bisMs) als ms, -1 wenn keine
    public double LetzteLaute(double vonMs, double bisMs, int schwelle)
    {
        int a = Idx(vonMs), e = Idx(bisMs);
        for (int i = e - 1; i >= a; i--) if (Laut(i, schwelle)) return Ms(i + 1);
        return -1;
    }

    // Erste Stille von mindestens minMs, die bei abMs laeuft oder danach beginnt.
    // Laeuft sie bei abMs schon, wird ihr Anfang rueckwaerts gesucht. Rueckgabe {startProbe, endeProbe} oder null.
    public int[] StilleAb(double abMs, double minMs, int schwelle)
    {
        int n = Proben.Length;
        int i = Idx(abMs); if (i >= n) i = n - 1;
        int min = (int)(minMs * Rate / 1000.0);
        int start = -1;
        if (!Laut(i, schwelle)) { start = i; while (start > 0 && !Laut(start - 1, schwelle)) start--; }
        for (; i < n; i++)
        {
            if (Laut(i, schwelle))
            {
                if (start >= 0 && i - start >= min) return new int[] { start, i };
                start = -1;
            }
            else if (start < 0) start = i;
        }
        if (start >= 0 && n - start >= min) return new int[] { start, n };
        return null;
    }

    // Sucht im Fenster [ms - fenster, ms + fenster] das Ende der letzten Stille von mindestens minStille ms.
    // Rueckgabe: Zeit der ersten lauten Probe danach in ms, oder -1 wenn dort keine Stille liegt (Redefluss).
    public double StilleEndeNahe(double ms, double fenster, double minStille, int schwelle)
    {
        int a = Idx(ms - fenster), e = Idx(ms + fenster);
        int min = (int)(minStille * Rate / 1000.0);
        int lauf = 0; int gefunden = -1;
        int j = a; while (j > 0 && lauf < min && !Laut(j - 1, schwelle)) { j--; lauf++; }
        for (int i = a; i < e && i < Proben.Length; i++)
        {
            if (Laut(i, schwelle)) { if (lauf >= min) gefunden = i; lauf = 0; }
            else lauf++;
        }
        return gefunden < 0 ? -1 : Ms(gefunden);
    }

    // Alle Stillen ab minMs Laenge als flache Liste start,ende,start,ende (Proben)
    public List<int> AlleStillen(double minMs, int schwelle)
    {
        List<int> r = new List<int>();
        int n = Proben.Length; int min = (int)(minMs * Rate / 1000.0); int start = -1;
        for (int i = 0; i < n; i++)
        {
            if (Laut(i, schwelle)) { if (start >= 0 && i - start >= min) { r.Add(start); r.Add(i); } start = -1; }
            else if (start < 0) start = i;
        }
        if (start >= 0 && n - start >= min) { r.Add(start); r.Add(n); }
        return r;
    }

    // Ersetzt jede Stille [von[k], bis[k]) durch genau laenge[k] Nullproben.
    public void SetzePausen(int[] von, int[] bis, int[] laenge)
    {
        List<short> neu = new List<short>(Proben.Length);
        int pos = 0;
        for (int k = 0; k < von.Length; k++)
        {
            for (int i = pos; i < von[k]; i++) neu.Add(Proben[i]);
            for (int i = 0; i < laenge[k]; i++) neu.Add(0);
            pos = bis[k];
        }
        for (int i = pos; i < Proben.Length; i++) neu.Add(Proben[i]);
        Proben = neu.ToArray();
    }

    public void SchreibWav(string pfad)
    {
        int bytes = Proben.Length * 2;
        using (FileStream f = new FileStream(pfad, FileMode.Create, FileAccess.Write))
        using (BinaryWriter w = new BinaryWriter(f))
        {
            w.Write(System.Text.Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + bytes);
            w.Write(System.Text.Encoding.ASCII.GetBytes("WAVE"));
            w.Write(System.Text.Encoding.ASCII.GetBytes("fmt ")); w.Write(16);
            w.Write((short)1); w.Write((short)1); w.Write(Rate); w.Write(Rate * 2); w.Write((short)2); w.Write((short)16);
            w.Write(System.Text.Encoding.ASCII.GetBytes("data")); w.Write(bytes);
            byte[] b = new byte[bytes]; Buffer.BlockCopy(Proben, 0, b, 0, bytes); w.Write(b);
        }
    }

    public int Spitze()
    {
        int m = 0;
        for (int i = 0; i < Proben.Length; i++) { int v = Proben[i]; if (v < 0) v = -v; if (v > m) m = v; }
        return m;
    }
}
'@
}

# ---------- sprechen (in den Speicher) ----------
if (-not (Test-Path -LiteralPath $Zielordner)) { New-Item -ItemType Directory -Force -Path $Zielordner | Out-Null }
$Zielordner = (Resolve-Path -LiteralPath $Zielordner).Path
$wav = Join-Path $Zielordner ($Name + '.wav')
$json = Join-Path $Zielordner ($Name + '.wahrheit.json')

$helfer = New-Object CutterFixtureHelfer3
$strom = New-Object System.IO.MemoryStream
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $synth.SelectVoice($Stimme)
  $synth.Rate = $Tempo
  $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo($Rate, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
  $synth.SetOutputToAudioStream($strom, $format)
  $helfer.Anhaengen($synth)
  $synth.SpeakSsml($ssml)
  $synth.SetOutputToNull()
}
finally { $synth.Dispose() }
$helfer.SetzeRohdaten($strom.ToArray(), $Rate)
$dauerRoh = $helfer.DauerMs()

if ($helfer.Marken.Count -ne ($teile.Count + 1)) {
  throw ("Erwartet {0} Marken, bekommen {1} - SAPI hat nicht alle Marken gemeldet." -f ($teile.Count + 1), $helfer.Marken.Count)
}
$marke = @{}
for ($i = 0; $i -lt $helfer.Marken.Count; $i++) { $marke[$helfer.Marken[$i]] = [double]$helfer.MarkenMs[$i] }

# ---------- Pausen in den Rohproben finden ----------
# Die Marke VOR einem <break> stimmt ungefaehr, die Marke DANACH meldet SAPI zu frueh (noch vor der Stille).
# Deshalb: ab der Marke davor die erste Stille suchen, die mindestens 60 % der verlangten Dauer hat.
$pIdx = @(); $pVon = @(); $pBis = @(); $pLen = @()
for ($i = 0; $i -lt $teile.Count; $i++) {
  if ($teile[$i].art -ne 'pause') { continue }
  $ab = $marke[('m{0}' -f $i)] - 150
  if ($ab -lt 0) { $ab = 0 }
  $s = $helfer.StilleAb($ab, $teile[$i].soll_ms * 0.6, $Schwelle)
  if ($null -eq $s) { throw ("Pause Nr. {0} ({1} ms) wurde im Ton nicht gefunden - SAPI hat sie nicht erzeugt." -f $i, $teile[$i].soll_ms) }
  $pIdx += $i; $pVon += $s[0]; $pBis += $s[1]; $pLen += [int][math]::Round($teile[$i].soll_ms * $Rate / 1000.0)
  $teile[$i].roh_ms = [math]::Round($helfer.Ms($s[1] - $s[0]), 1)
}
for ($k = 1; $k -lt $pIdx.Count; $k++) {
  if ($pVon[$k] -lt $pBis[$k - 1]) { throw ("Pausen Nr. {0} und {1} wurden auf dieselbe Stille gelegt." -f $pIdx[$k - 1], $pIdx[$k]) }
}

# Rohzeit (ms) -> Zeit nach dem Zurechtschneiden der Pausen
function Neu([double]$ms) {
  $verschub = 0.0
  for ($k = 0; $k -lt $pIdx.Count; $k++) {
    $von = $helfer.Ms($pVon[$k]); $bis = $helfer.Ms($pBis[$k]); $soll = $helfer.Ms($pLen[$k])
    if ($ms -ge $bis) { $verschub += ($bis - $von) - $soll }
    elseif ($ms -gt $von) { $in = $ms - $von; if ($in -gt $soll) { $in = $soll }; return ($von - $verschub + $in) }
    else { break }
  }
  return ($ms - $verschub)
}

# neue Pausenkanten merken, dann die Proben umbauen
$pNeuVon = @{}; $pNeuBis = @{}
for ($k = 0; $k -lt $pIdx.Count; $k++) {
  $a = Neu ($helfer.Ms($pVon[$k]))
  $pNeuVon[$pIdx[$k]] = $a
  $pNeuBis[$pIdx[$k]] = $a + $helfer.Ms($pLen[$k])
}
$markeNeu = @{}
foreach ($k in @($marke.Keys)) { $markeNeu[$k] = Neu $marke[$k] }
$wortNeu = @()
for ($i = 0; $i -lt $helfer.Woerter.Count; $i++) { $wortNeu += (Neu ([double]$helfer.WoerterMs[$i])) }

$helfer.SetzePausen([int[]]$pVon, [int[]]$pBis, [int[]]$pLen)
$helfer.SchreibWav($wav)
$dauer = $helfer.DauerMs()

function Rund([double]$x) { return [math]::Round($x, 1) }

# ---------- Woerter den Teilen zuordnen (ueber die Zeichenstelle im SSML) ----------
$wortTeil = @()
$erstesWort = @{}
for ($i = 0; $i -lt $helfer.Woerter.Count; $i++) {
  $pos = $helfer.WoerterPos[$i]
  $nr = -1
  for ($j = 0; $j -lt $teile.Count; $j++) { if ($pos -ge $ssmlVon[$j] -and $pos -lt $ssmlBis[$j]) { $nr = $j; break } }
  $wortTeil += $nr
  if ($nr -ge 0 -and -not $erstesWort.ContainsKey($nr)) { $erstesWort[$nr] = $i }
}

# ---------- Anfang jedes gesprochenen Teils ----------
# Gemessen an dieser Stimme: die <mark/>-Stellen liegen im fliessenden Satz 50 bis 90 ms VOR der
# wirklichen Wortgrenze, die Wort-Ereignisse (SpeakProgress) treffen sie auf etwa 15 ms. Deshalb:
#   nach einer Pause            -> Ende der Pause (auf die Probe genau)
#   nach einer natuerlichen Stille (Komma, Satzende) -> erste laute Probe nach dieser Stille
#   mitten im Redefluss         -> Wort-Ereignis des ersten Worts
$anfang = @{}
for ($i = 0; $i -lt $teile.Count; $i++) {
  if ($teile[$i].art -eq 'pause') { continue }
  if (-not $erstesWort.ContainsKey($i)) { throw ("Teil Nr. {0} hat kein Wort-Ereignis von SAPI bekommen." -f $i) }
  if ($i -gt 0 -and $teile[$i - 1].art -eq 'pause') { $anfang[$i] = $pNeuBis[$i - 1]; continue }
  $w0 = $wortNeu[$erstesWort[$i]]
  $nach = $helfer.StilleEndeNahe($w0, 60, 100, $Schwelle)
  if ($nach -ge 0) { $anfang[$i] = $nach } else { $anfang[$i] = $w0 }
}

# ---------- Teile mit Zeiten ----------
$liste = @()
for ($i = 0; $i -lt $teile.Count; $i++) {
  $t = $teile[$i]
  $o = [ordered]@{ nr = $i; art = $t.art }
  if ($t.art -eq 'pause') {
    $o.text = ''
    $o.entfernen = $t.entfernen
    $o.start_ms = Rund $pNeuVon[$i]
    $o.ende_ms = Rund $pNeuBis[$i]
    $o.soll_ms = $t.soll_ms
    $o.lang = ($t.soll_ms -ge 1500)
    $o.sapi_roh_ms = $t.roh_ms
  }
  else {
    # Ende = letzte laute Probe vor dem Anfang des naechsten Teils (bei Stille dazwischen also deren Beginn)
    if ($i + 1 -ge $teile.Count) { $grenze = $dauer }
    elseif ($teile[$i + 1].art -eq 'pause') { $grenze = $pNeuVon[$i + 1] }
    else { $grenze = $anfang[$i + 1] }
    $s2 = $helfer.LetzteLaute($anfang[$i], $grenze, $Schwelle)
    if ($s2 -lt 0) { throw ("Teil Nr. {0} ('{1}') enthaelt keinen Ton." -f $i, $t.text) }
    $o.text = $t.text
    $o.entfernen = $t.entfernen
    $o.start_ms = Rund $anfang[$i]
    $o.ende_ms = Rund $s2
  }
  $o.hinweis = $t.hinweis
  $liste += $o
}

# ---------- SAPI-Wortanfaenge (das erste Wort nach einer Pause meldet SAPI manchmal zu frueh -> auf den Teilanfang ziehen) ----------
$woerter = @()
for ($i = 0; $i -lt $helfer.Woerter.Count; $i++) {
  $nr = $wortTeil[$i]
  $ms = $wortNeu[$i]
  if ($nr -ge 0 -and $ms -lt $anfang[$nr]) { $ms = $anfang[$nr] }
  if ($nr -ge 0 -and $erstesWort[$nr] -eq $i) { $ms = $anfang[$nr] }
  $woerter += [ordered]@{ wort = $helfer.Woerter[$i]; start_ms = (Rund $ms); teil = $nr }
}

# ---------- alle Stillen ab 150 ms in der fertigen Datei ----------
$st = $helfer.AlleStillen(150, $Schwelle)
$stillen = @()
for ($i = 0; $i -lt $st.Count; $i += 2) {
  $stillen += [ordered]@{ start_ms = (Rund $helfer.Ms($st[$i])); ende_ms = (Rund $helfer.Ms($st[$i + 1])); dauer_ms = (Rund $helfer.Ms($st[$i + 1] - $st[$i])) }
}

$wahrheit = [ordered]@{
  beschreibung  = (Uml 'Testaufnahme f{ue}r den Video-Cutter. Alle Zeiten in Millisekunden ab Dateianfang. Kanten an einer Stille sind auf die Probe genau, Kanten mitten im Redefluss stammen aus den Wort-Ereignissen von SAPI (etwa +-15 ms).')
  wav           = [System.IO.Path]::GetFileName($wav)
  stimme        = $Stimme
  abtastrate    = $helfer.Rate
  dauer_ms      = Rund $dauer
  spitze_16bit  = $helfer.Spitze()
  schwelle      = $Schwelle
  text_komplett = $alles
  text_sauber   = (($teile | Where-Object { $_.art -ne 'pause' -and -not $_.entfernen } | ForEach-Object { $_.text }) -join ' ')
  zaehler       = [ordered]@{
    teile           = $teile.Count
    fuellwoerter    = @($teile | Where-Object { $_.art -eq 'fuellwort' }).Count
    lange_pausen    = @($teile | Where-Object { $_.art -eq 'pause' -and $_.soll_ms -ge 1500 }).Count
    teile_entfernen = @($teile | Where-Object { $_.entfernen }).Count
  }
  teile         = $liste
  stillen       = $stillen
  sapi_woerter  = $woerter
}

$text = $wahrheit | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($json, $text, (New-Object System.Text.UTF8Encoding($false)))

Write-Output ("WAV:      {0}" -f $wav)
Write-Output ("Wahrheit: {0}" -f $json)
Write-Output ("Dauer:    {0:N2} s (roh von SAPI {1:N2} s), {2} Hz, Spitze {3}, {4} Teile, {5} Pausen, {6} SAPI-Woerter" -f ($dauer / 1000), ($dauerRoh / 1000), $helfer.Rate, $helfer.Spitze(), $teile.Count, $pIdx.Count, $helfer.Woerter.Count)
