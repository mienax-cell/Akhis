<#
  aussen_pruefen.ps1 - laeuft das Schnitt-Werkzeug auch, wenn es NICHT aus der Claude-App gestartet wird?

  Die Claude-App ist ein Windows-Paket (MSIX): Was sie startet, sieht AppData umgeleitet. MAGI wird per
  Doppelklick gestartet und sieht den echten Rechner. Dieses Skript startet das Werkzeug ueber WMI - also
  ausserhalb der App, so wie MAGI es tut - und zeigt, was dabei herauskommt.

  Aufruf:  powershell -NoProfile -ExecutionPolicy Bypass -File aussen_pruefen.ps1 [-Video <pfad>]
  Ohne -Video laeuft nur "pruefen". Mit -Video zusaetzlich ein Schnitt der ersten 5 Sekunden (Probe).
  Diese Datei ist absichtlich reines ASCII (PowerShell 5.1 liest UTF-8 ohne BOM sonst falsch).
#>
param([string]$Video = '')

$ErrorActionPreference = 'Stop'
$modul = Split-Path -Parent $PSScriptRoot
$aus = Join-Path $PSScriptRoot '_aussen.txt'
$bat = Join-Path $PSScriptRoot '_aussen.cmd'
if (Test-Path -LiteralPath $aus) { Clear-Content -LiteralPath $aus }

$zeilen = @('@echo off', 'chcp 65001 >nul', 'set PYTHONIOENCODING=utf-8',
            ('python "{0}\schnitt.py" pruefen' -f $modul))
if ($Video) {
  $zeilen += ('python "{0}\schnitt.py" alles "{1}" --stil reel --probe 5 --ordner "{2}\_aussen.schnitt" --ausgabe "{2}\_aussen.mp4" --ueberschreiben' -f $modul, $Video, $PSScriptRoot)
}
$zeilen += 'echo === ende ==='
[System.IO.File]::WriteAllLines($bat, $zeilen, (New-Object System.Text.UTF8Encoding($false)))

$befehl = 'cmd.exe /c ""{0}" > "{1}" 2>&1"' -f $bat, $aus
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $befehl }
if ($r.ReturnValue -ne 0) { throw ('WMI konnte den Prozess nicht starten (Code {0}).' -f $r.ReturnValue) }

$n = 0
while ($n -lt 360 -and -not ((Test-Path -LiteralPath $aus) -and (Select-String -LiteralPath $aus -Pattern '=== ende ===' -Quiet))) {
  Start-Sleep -Milliseconds 500; $n++
}
Get-Content -LiteralPath $aus -Encoding UTF8
if ($n -ge 360) { Write-Output 'ZEIT ABGELAUFEN - das Werkzeug hat nach 3 Minuten nicht geantwortet.'; exit 1 }
