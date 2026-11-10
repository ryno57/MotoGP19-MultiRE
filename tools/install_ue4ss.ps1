param(
    [string]$Source = "F:\MotoGP19-MultiRE\work\ue4ss\extracted",
    [string]$GamePath = "",
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

if (-not $GamePath) {
    $GamePath = "F:\SteamLibrary\steamapps\common\MotoGP" + [char]0x2122 + "19"
}

$win64 = Join-Path $GamePath "motogp19\Binaries\Win64"
if (-not (Test-Path -LiteralPath $win64)) {
    throw "Dossier introuvable : $win64"
}
if (-not (Test-Path -LiteralPath (Join-Path $Source "dwmapi.dll"))) {
    throw "Source UE4SS invalide : $Source"
}

$running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "*motogp*" }
if ($running) {
    throw "Le jeu est en cours d'exécution. Ferme-le avant d'installer UE4SS."
}

if (-not $SkipBackup) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = Join-Path "F:\MotoGP19-MultiRE\backups" "ue4ss-$stamp"
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    Get-ChildItem -LiteralPath $win64 -Force |
        Select-Object Name, Length, LastWriteTime |
        Format-Table -AutoSize |
        Out-String -Width 200 |
        Set-Content (Join-Path $backup "before-win64.txt")
    Compress-Archive -LiteralPath $win64 -DestinationPath (Join-Path $backup "Binaries-Win64.zip") -CompressionLevel Optimal -Force
    $config = Join-Path $env:LOCALAPPDATA "motogp19\Saved\Config\WindowsNoEditor"
    if (Test-Path -LiteralPath $config) {
        Compress-Archive -Path (Join-Path $config "*") -DestinationPath (Join-Path $backup "Config-WindowsNoEditor.zip") -CompressionLevel Optimal -Force
    }
    $saves = Join-Path $env:LOCALAPPDATA "motogp19\Saved\SaveGames"
    if (Test-Path -LiteralPath $saves) {
        Compress-Archive -Path (Join-Path $saves "*") -DestinationPath (Join-Path $backup "SaveGames.zip") -CompressionLevel Optimal -Force
    }
    "Backup cree : $backup" | Set-Content "F:\MotoGP19-MultiRE\work\ue4ss\last_backup_path.txt"
    Write-Host "Backup : $backup"
}

Write-Host "Installation UE4SS dans : $win64"
Copy-Item -LiteralPath (Join-Path $Source "dwmapi.dll") -Destination $win64 -Force
Copy-Item -LiteralPath (Join-Path $Source "UE4SS.dll") -Destination $win64 -Force
Copy-Item -LiteralPath (Join-Path $Source "UE4SS-settings.ini") -Destination $win64 -Force
Copy-Item -LiteralPath (Join-Path $Source "Mods") -Destination $win64 -Recurse -Force

Write-Host "Fichiers installes :"
Get-ChildItem -LiteralPath $win64 -Force | Select-Object Name, Length | Format-Table -AutoSize

Write-Host ""
Write-Host "Lance le jeu normalement via Steam."
Write-Host "Une console UE4SS doit apparaitre."
Write-Host "Logs : $win64\\UE4SS.log"
Write-Host "Desinstallation : tools\\uninstall_ue4ss.ps1"
