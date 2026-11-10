param(
    [string]$GamePath = "",
    [string]$RestoreBackup = "",
    [switch]$RestoreConfig
)

$ErrorActionPreference = "Stop"

if (-not $GamePath) {
    $GamePath = "F:\SteamLibrary\steamapps\common\MotoGP" + [char]0x2122 + "19"
}

$win64 = Join-Path $GamePath "motogp19\Binaries\Win64"
if (-not (Test-Path -LiteralPath $win64)) {
    throw "Dossier introuvable : $win64"
}

$running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "*motogp*" }
if ($running) {
    $running | Stop-Process -Force
    Start-Sleep -Seconds 2
}

$targets = @(
    (Join-Path $win64 "dwmapi.dll"),
    (Join-Path $win64 "UE4SS.dll"),
    (Join-Path $win64 "UE4SS-settings.ini"),
    (Join-Path $win64 "Mods")
)
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
        Write-Host "Supprime : $target"
    }
}

if ($RestoreBackup -and (Test-Path -LiteralPath $RestoreBackup)) {
    $zip = Join-Path $RestoreBackup "Binaries-Win64.zip"
    if (Test-Path -LiteralPath $zip) {
        $temp = Join-Path $env:TEMP ("ue4ss-restore-" + [guid]::NewGuid().ToString())
        Expand-Archive -LiteralPath $zip -DestinationPath $temp -Force
        $source = Join-Path $temp "Win64"
        if (-not (Test-Path -LiteralPath $source)) {
            $source = Get-ChildItem -LiteralPath $temp -Directory | Select-Object -First 1 -ExpandProperty FullName
        }
        Copy-Item -Path (Join-Path $source "*") -Destination $win64 -Recurse -Force
        Remove-Item -LiteralPath $temp -Recurse -Force
        Write-Host "Binaries/Win64 restaure depuis : $zip"
    }
}

if ($RestoreConfig -and $RestoreBackup) {
    $zip = Join-Path $RestoreBackup "Config-WindowsNoEditor.zip"
    if (Test-Path -LiteralPath $zip) {
        $config = Join-Path $env:LOCALAPPDATA "motogp19\Saved\Config\WindowsNoEditor"
        Expand-Archive -LiteralPath $zip -DestinationPath $config -Force
        Write-Host "Config restauree depuis : $zip"
    }
}

Write-Host "Desinstallation terminee. Verifie les fichiers du jeu via Steam si besoin."
