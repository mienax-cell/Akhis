<#
  einrichten.ps1 - prueft, ob auf diesem Rechner alles fuer das Videoschnitt-Paket da ist.

  Es installiert und laedt NICHTS. Fehlt etwas, nennt es den Befehl dafuer.
  Es legt nur an: Verknuepfungen zu den ArtCraft-Programmen im Ordner artcraft\ und - nur mit
  -SkillGlobal - den Claude-Skill im eigenen Benutzerordner (ein vorhandener wird nicht ueberschrieben).

  Aufruf:  Doppelklick auf einrichten.cmd
     oder  powershell -NoProfile -ExecutionPolicy Bypass -File einrichten.ps1 [-SkillGlobal] [-Selbsttest]

  -SkillGlobal   legt den Skill nach %USERPROFILE%\.claude\skills\video-schnitt, damit Claude ihn in jedem
                 Ordner kennt (sonst nur, wenn Claude in diesem Paketordner geoeffnet ist)
  -Selbsttest    laesst danach den Selbsttest des Werkzeugs laufen (schneidet ein Testvideo, 1 bis 5 Minuten)
  -SkillZiel     anderer Zielordner fuer -SkillGlobal (zum Ausprobieren)

  Diese Datei ist absichtlich reines ASCII (PowerShell 5.1 liest UTF-8 ohne BOM sonst falsch).
#>
param([switch]$SkillGlobal, [switch]$Selbsttest, [string]$SkillZiel = '')

$ErrorActionPreference = 'Stop'
$paket = $PSScriptRoot
$modul = Join-Path $paket 'videoschnitt'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$fehlt = New-Object System.Collections.Generic.List[string]
$kann = New-Object System.Collections.Generic.List[string]

function Zeile([string]$stand, [string]$name, [string]$wert) {
  Write-Host ('  {0,-6} {1}: {2}' -f $stand, $name, $wert)
}

function Version([string]$befehl) {
  # Ueber cmd gestartet: Ein fehlendes Programm oder Text auf dem Fehlerkanal bricht das Skript dann nicht ab.
  $aus = cmd /c ($befehl + ' --version 2>&1')
  return (($aus | Out-String).Trim())
}

$pyExe = ''
$pyArgs = @()
function PyGeht([string]$code) {
  $alt = $ErrorActionPreference
  $ErrorActionPreference = 'SilentlyContinue'
  & $script:pyExe @script:pyArgs -c $code 2>$null | Out-Null
  $ok = ($LASTEXITCODE -eq 0)
  $ErrorActionPreference = $alt
  return $ok
}

Write-Host ''
Write-Host 'Videoschnitt-Paket - Einrichten'
Write-Host ('  Ort: ' + $paket)

# ---------------------------------------------------------------------------------------------------------
Write-Host ''
Write-Host '1 - Schnitt-Werkzeug'

$werkzeugBereit = $false
if (-not (Test-Path -LiteralPath (Join-Path $modul 'schnitt.py'))) {
  Zeile 'FEHLT' 'Werkzeug' 'videoschnitt\schnitt.py liegt nicht im Paket - den Ordner noch einmal ganz kopieren'
  $fehlt.Add('Das Paket ist unvollstaendig: der Ordner videoschnitt fehlt.')
} else {
  $pyText = ''
  foreach ($k in @('python', 'py -3')) {
    $v = Version $k
    if ($v -match '^Python (\d+)\.(\d+)') {
      $pyGross = [int]$Matches[1]; $pyKlein = [int]$Matches[2]; $pyText = $Matches[0]
      $teile = $k.Split(' ')
      $pyExe = $teile[0]
      if ($teile.Count -gt 1) { $pyArgs = @($teile[1]) }
      break
    }
  }
  $pyHolen = @(
    'Python 3.10 oder neuer:   winget install --id Python.Python.3.12 -e --scope user   (danach ein NEUES Fenster oeffnen)',
    'Dann die Python-Pakete:   python -m pip install faster-whisper numpy pillow',
    'ffmpeg (falls noch nicht da):   winget install --id Gyan.FFmpeg -e --scope user',
    'Danach einrichten.cmd noch einmal starten - dann prueft das Werkzeug den Rest selbst.'
  )
  if (-not $pyExe) {
    Zeile 'FEHLT' 'Python' 'nicht gefunden'
    $fehlt.AddRange([string[]]$pyHolen)
  } elseif ($pyGross -lt 3 -or ($pyGross -eq 3 -and $pyKlein -lt 10)) {
    Zeile 'FEHLT' 'Python' ($pyText + ' ist zu alt')
    $fehlt.AddRange([string[]]$pyHolen)
    $pyExe = ''
  } else {
    Zeile 'ok' 'Python' $pyText
    if ($pyExe -eq 'py') {
      Zeile 'HINWEIS' 'Aufruf' '"python" ist nicht im PATH, "py" geht - in allen Befehlen py statt python schreiben'
    }
  }

  if ($pyExe) {
    $pip = $pyExe + ' ' + (($pyArgs + @('-m', 'pip', 'install')) -join ' ')
    if (-not (PyGeht 'import numpy')) {
      # Ohne numpy startet das Werkzeug gar nicht - also hier schon melden, statt es abstuerzen zu lassen.
      Zeile 'FEHLT' 'Python-Pakete' 'numpy fehlt (und vermutlich faster-whisper)'
      $fehlt.Add('Python-Pakete:   ' + $pip + ' faster-whisper numpy pillow')
      $fehlt.Add('ffmpeg (falls noch nicht da):   winget install --id Gyan.FFmpeg -e --scope user')
      $fehlt.Add('Danach einrichten.cmd noch einmal starten - dann prueft das Werkzeug den Rest selbst.')
    } else {
      if (-not (PyGeht 'import PIL')) {
        $kann.Add('pillow (misst die Zeilenbreite der Untertitel, sonst wird geschaetzt):   ' + $pip + ' pillow')
      }
      Write-Host '  Das Werkzeug prueft sich selbst:'
      Write-Host ''
      & $pyExe @pyArgs (Join-Path $modul 'schnitt.py') pruefen
      if ($LASTEXITCODE -eq 0) {
        $werkzeugBereit = $true
      } else {
        $fehlt.Add('Schnitt-Werkzeug: die Zeilen mit "fehlt" oben beheben - der Befehl steht jeweils in der Zeile darunter.')
      }
    }
  }
}

# Nur fuer "Grafik ueber dem Video" - der normale Schnitt braucht das nicht.
$node = Version 'node'
if ($node -match '^v(\d+)\.' -and [int]$Matches[1] -ge 22) {
  Zeile 'ok' 'Node (nur fuer Grafik)' $node
} else {
  Zeile 'fehlt' 'Node (nur fuer Grafik)' 'nicht da oder aelter als 22'
  $kann.Add('Node ab 22 (nur fuer Grafik ueber dem Video):   winget install --id OpenJS.NodeJS.LTS -e')
}
$browser = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
             "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe") |
           Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if ($browser) {
  Zeile 'ok' 'Edge oder Chrome (nur fuer Grafik)' $browser
} else {
  Zeile 'fehlt' 'Edge oder Chrome (nur fuer Grafik)' 'nicht an den ueblichen Orten'
  $kann.Add('Edge oder Chrome (nur fuer Grafik): installieren oder den Pfad in die Umgebungsvariable MAGI_BROWSER schreiben')
}

# ---------------------------------------------------------------------------------------------------------
Write-Host ''
Write-Host '2 - ArtCraft-Programme'

$programme = @(
  @('FilmCraft', 'filmcraft', 'Videoschnitt, Farbe, Ton'),
  @('EffectCraft', 'effectcraft', 'Bewegungsgrafik und Effekte'),
  @('PhotoCraft', 'photocraft', 'Bildbearbeitung'),
  @('LightCraft', 'lightcraft', 'Fotos verwalten und entwickeln'),
  @('VectorCraft', 'vectorcraft', 'Vektorgrafik')
)
$sh = $null
try { $sh = New-Object -ComObject WScript.Shell } catch {}
$gesperrt = $false
foreach ($p in $programme) {
  $ordner = Join-Path $paket ('artcraft\' + $p[1])
  $exe = Join-Path $ordner ($p[1] + '.exe')
  if (-not (Test-Path -LiteralPath $exe)) {
    Zeile 'FEHLT' $p[0] ('artcraft\' + $p[1] + '\' + $p[1] + '.exe liegt nicht im Paket')
    $fehlt.Add($p[0] + ' fehlt im Paket - den Ordner artcraft noch einmal ganz kopieren.')
    continue
  }
  $anhang = ''
  try {
    $sig = (Get-AuthenticodeSignature -LiteralPath $exe).Status
    if ("$sig" -eq 'Valid') { $anhang = ', Signatur gueltig' } else { $anhang = ', Signatur: ' + $sig + ' (Datei beim Kopieren beschaedigt?)' }
  } catch {}
  try {
    if (Get-Item -LiteralPath $exe -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue) { $gesperrt = $true }
  } catch {}
  $verkn = ''
  if ($sh) {
    try {
      $l = $sh.CreateShortcut((Join-Path $paket ('artcraft\' + $p[0] + '.lnk')))
      $l.TargetPath = $exe
      $l.WorkingDirectory = $ordner
      $l.Description = $p[2]
      $l.Save()
      $verkn = '  ->  artcraft\' + $p[0] + '.lnk'
    } catch { $verkn = '  (Verknuepfung nicht angelegt - die .exe direkt starten)' }
  }
  Zeile 'ok' $p[0] ($p[2] + $anhang + $verkn)
}
if ($gesperrt) {
  Zeile 'HINWEIS' 'Windows' 'Die Programme kommen von einem anderen Rechner - beim ersten Start fragt Windows evtl. nach ("Weitere Informationen" > "Trotzdem ausfuehren")'
}

# ---------------------------------------------------------------------------------------------------------
Write-Host ''
Write-Host '3 - Claude-Skill'

$skillQuelle = Join-Path $paket '.claude\skills\video-schnitt\SKILL.md'
if (-not (Test-Path -LiteralPath $skillQuelle)) {
  Zeile 'FEHLT' 'Skill' '.claude\skills\video-schnitt\SKILL.md liegt nicht im Paket (versteckte Ordner mitkopieren!)'
  $fehlt.Add('Der Ordner .claude fehlt im Paket - beim Kopieren versteckte Ordner mitnehmen.')
} else {
  Zeile 'ok' 'Skill im Paket' 'Claude kennt ihn, sobald es in diesem Ordner geoeffnet wird'
  if ($SkillGlobal) {
    if (-not $SkillZiel) { $SkillZiel = Join-Path $env:USERPROFILE '.claude\skills\video-schnitt' }
    $zielDatei = Join-Path $SkillZiel 'SKILL.md'
    if (Test-Path -LiteralPath $zielDatei) {
      Zeile 'bleibt' 'Skill global' ($zielDatei + ' gibt es schon - nicht ueberschrieben')
    } else {
      $text = [System.IO.File]::ReadAllText($skillQuelle, [System.Text.Encoding]::UTF8)
      $text = $text.Replace('"videoschnitt\schnitt.py"', ('"' + $modul + '\schnitt.py"'))
      $neu = '**Paketordner:** `' + $paket + '` - alle Pfade unten gelten ab dort.'
      $text = [regex]::Replace($text, '(?m)^\*\*Paketordner:\*\*[^\r\n]*', { param($m) $neu })
      try {
        New-Item -ItemType Directory -Force -Path $SkillZiel | Out-Null
        [System.IO.File]::WriteAllText($zielDatei, $text, (New-Object System.Text.UTF8Encoding($false)))
        Zeile 'ok' 'Skill global' ($zielDatei + '  (zeigt auf dieses Paket - nach dem Verschieben des Ordners neu anlegen)')
      } catch {
        Zeile 'FEHLT' 'Skill global' ('konnte nicht nach ' + $zielDatei + ' geschrieben werden: ' + $_.Exception.Message)
        $kann.Add('Skill von Hand kopieren: .claude\skills\video-schnitt aus dem Paket nach ' + $SkillZiel)
      }
    }
  } else {
    Zeile '-' 'Skill global' 'nicht angelegt (bei Bedarf: einrichten.cmd -SkillGlobal)'
  }
}

# ---------------------------------------------------------------------------------------------------------
if ($Selbsttest) {
  Write-Host ''
  Write-Host '4 - Selbsttest'
  if ($werkzeugBereit) {
    & $pyExe @pyArgs (Join-Path $modul 'tests\selbsttest.py')
    if ($LASTEXITCODE -ne 0) { $fehlt.Add('Der Selbsttest ist nicht ganz durchgelaufen - die Zeilen mit FEHLER oben ansehen.') }
  } else {
    Zeile '-' 'Selbsttest' 'uebersprungen - erst muss das Werkzeug bereit sein'
  }
}

# ---------------------------------------------------------------------------------------------------------
Write-Host ''
if ($fehlt.Count -eq 0) {
  Write-Host 'BEREIT.'
  Write-Host ('  Video schneiden:  ' + $(if ($pyExe) { $pyExe } else { 'python' }) + ' "' + $modul + '\schnitt.py" alles "<video>" --stil reel')
  Write-Host '  Mit Claude:       Claude in diesem Ordner oeffnen und sagen: "Schneid das Video <Pfad> im Stil reel"'
  Write-Host '  Mehr dazu:        LIES-MICH.md'
} else {
  Write-Host 'NOCH NICHT BEREIT - das fehlt:'
  foreach ($f in $fehlt) { Write-Host ('  * ' + $f) }
}
if ($kann.Count -gt 0) {
  Write-Host ''
  Write-Host 'Freiwillig:'
  foreach ($k in $kann) { Write-Host ('  * ' + $k) }
}
Write-Host ''
if ($fehlt.Count -eq 0) { exit 0 } else { exit 1 }
