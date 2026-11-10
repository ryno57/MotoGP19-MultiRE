param(
    [string]$GamePath = "F:\SteamLibrary\steamapps\common\MotoGP19",
    [switch]$Windowed
)

$ErrorActionPreference = "Stop"

$win64 = Join-Path $GamePath "motogp19\Binaries\Win64"
$exe = Join-Path $win64 "motogp19-Win64-Shipping.exe"

if (-not (Test-Path -LiteralPath $exe)) {
    throw "Executable introuvable : $exe. Verifie que la jonction MotoGP19 existe."
}
if (-not (Get-Process -Name steam -ErrorAction SilentlyContinue)) {
    throw "Steam doit etre lance avant le jeu."
}
if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "*motogp*" }) {
    throw "Le jeu est deja lance. Ferme-le avant."
}

$appid = Join-Path $win64 "steam_appid.txt"
if (-not (Test-Path -LiteralPath $appid)) {
    Set-Content -LiteralPath $appid -Value "984780" -NoNewline
    Write-Host "steam_appid.txt cree."
}

$arguments = @("-log")
if ($Windowed) {
    $arguments += @("-windowed", "-ResX=1280", "-ResY=720")
}

Write-Host "Lancement UE4SS via : $exe"
Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $win64
Start-Sleep -Seconds 3
Write-Host "Log UE4SS : $win64\UE4SS.log"
Write-Host "Console UE4SS : fenetre 'UE4SS Debugging Tools'."
Write-Host "Touches du mod MGP19Dump : F8=etat, F9=lobby listen, F10=mugello listen, F11=world."
