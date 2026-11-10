# Installation UE4SS — MotoGP 19

Date : 2026-11-10
Version : **UE4SS v3.0.1** (`Game__Shipping__Win64`)
Jeu : `F:\SteamLibrary\steamapps\common\MotoGP™19`

---

## 1. Ce qui a été installé

Dans `motogp19/Binaries/Win64/` :

```text
dwmapi.dll          proxy loader
UE4SS.dll           coeur UE4SS
UE4SS-settings.ini  configuration
Mods/               mods intégrés + MGP19Dump
steam_appid.txt     984780 (pour le lancement direct via la jonction)
```

Configuration appliquée dans `UE4SS-settings.ini` :

```ini
[General]
bUseUObjectArrayCache = false

[EngineVersionOverride]
MajorVersion = 4
MinorVersion = 21

[Debug]
ConsoleEnabled = 1
GuiConsoleEnabled = 1
GuiConsoleVisible = 1
GraphicsAPI = dx11

[Overrides]
ModsFolderPath = F:\MotoGP19-MultiRE\work\ue4ss\Mods
```

Résultat : UE4SS se charge sur UE 4.21, la console graphique
« UE4SS Debugging Tools » apparaît, et les mods Lua se chargent.

---

## 2. Problème du chemin `™` et solution

Le dossier du jeu contient `™` (`MotoGP™19`). Les mods Lua d'UE4SS
échouaient avec :

```text
luaL_loadfile returned LUA_ERRFILE => ... MotoGP"19 ... Invalid argument
```

Solution : créer une **jonction ASCII** vers le dossier du jeu :

```powershell
cmd /c mklink /J "F:\SteamLibrary\steamapps\common\MotoGP19" "F:\SteamLibrary\steamapps\common\MotoGP™19"
```

Puis lancer l'exécutable via la jonction :

```text
F:\SteamLibrary\steamapps\common\MotoGP19\motogp19\Binaries\Win64\motogp19-Win64-Shipping.exe
```

Le processus voit alors un chemin ASCII, et les mods Lua se chargent.
Un `steam_appid.txt` contenant `984780` est nécessaire pour ce lancement
direct (Steam doit être ouvert).

**Important :** lancer via Steam classique utilise le chemin réel avec `™`.
UE4SS se charge quand même, mais les mods Lua échouent. Pour tester UE4SS,
utiliser `tools\launch_ue4ss.ps1`.

---

## 3. Sauvegardes

Dossier :

```text
F:\MotoGP19-MultiRE\backups\ue4ss-20261110-202311\
```

Contenu :

- `Binaries-Win64.zip` — dossier Win64 avant installation
- `Config-WindowsNoEditor.zip` — Engine.ini, GameUserSettings, etc.
- `SaveGames.zip` — sauvegardes
- `before-win64.txt`
- `appmanifest_984780.acf.bak` — manifeste Steam avant modification
- `README.txt`

L'appmanifest Steam a été restauré à son état d'origine après le test.
La jonction ASCII reste en place pour UE4SS.

---

## 4. Mod MGP19Dump

Fichier :

```text
work\ue4ss\Mods\MGP19Dump\Scripts\main.lua
```

Touches :

| Touche | Action |
|---|---|
| F8 | dump des composants de session, GameMode, GameInstance, World |
| F9 | tente `open /Game/maps/lobby/lobby?listen?game=...LobbyGameModeBP...` |
| F10 | tente `open /Game/maps/Tracks/mugello/mugello?listen` |
| F11 | affiche PlayerController et World |

Le mod utilise `UEHelpers.GetKismetSystemLibrary()` et tente successivement
`World:ServerTravel`, `PlayerController:ServerTravel`,
`PlayerController:ClientTravel`, puis `ExecuteConsoleCommand`.

---

## 5. Résultats du test

### Ce qui marche

- UE4SS se charge sur UE 4.21 (scan des signatures OK).
- La console graphique s'ouvre.
- Les mods Lua se chargent via la jonction ASCII.
- `F8` fonctionne et dump les classes.
- `F9` exécute bien la commande `open` (log `tentative 4: ok`).
- La manette de commande Kismet est valide.

### Dump F8 au menu principal

```text
GameLiftServerGameSessionComponent : 0 objet
DedicatedServerGameSessionComponent : 0 objet
DedicatedServerComponent : 0 objet
GameSessionSettings : 0 objet
GameSession : IgnitionGameSession (menu)
GameOnlineSessionManager : GameOnlineSessionManagerBP_C (Transient)
PlayerController : MenuPlayerControllerBP_C
GameMode : MenuGameModeBP_C
GameInstance : GameInstance_BP_C
World : menu / IndoorLight / Camera_snapshot
```

### Ce qui bloque

`F9` lance bien la commande, mais :

- le monde reste `/Game/maps/menu/menu` ;
- un écran de chargement avec spinner apparaît ;
- **aucun port UDP 7777 n'est ouvert** ;
- pas de `LobbyGameModeBP_C` chargé.

C'est le **chargement infini** déjà observé par le contact : la map lobby
semble demandée, mais la session/GameMode n'est pas initialisé.

---

## 6. Interprétation

- Le code serveur dédié n'est pas présent/actif dans le client
  (`GameLiftServer...` et `DedicatedServer...` = 0 objet).
- `open`/`ServerTravel` ne suffisent pas : le jeu attend une **session**
  (GameOnlineSessionManager / IgnitionGameSession) avant de voyager.
- Le `GameOnlineSessionManagerBP_C` est le prochain objet à inspecter :
  ses fonctions `CreateSession`, `StartMatchmaking`, `HostAlone`, etc.
- Les CVars `Online.ListenServerAllowed`, `Online.HostAloneAllowed`,
  `Online.IgnoreRolePlayerRestrictions` peuvent être testées via UE4SS
  ou via `Engine.ini`.

---

## 7. Prochaines pistes

1. **Inspecter `GameOnlineSessionManagerBP_C`**
   - lister ses fonctions/propriétés avec F8 ou `Live View` ;
   - chercher `CreateSession`, `HostAlone`, `Listen`, `StartMatchmaking`.
2. **Tester les CVars host-alone**
   - `Online.ListenServerAllowed=1`
   - `Online.HostAloneAllowed=1`
   - `Online.IgnoreRolePlayerRestrictions=1`
   - puis relancer F9.
3. **Appeler directement une fonction de session**
   - via `obj:CallFunction("CreateSession", ...)` si les paramètres sont
     identifiables.
4. **Live View**
   - inspecter les propriétés de `GameOnlineSessionManagerBP_C`,
     `IgnitionGameSession`, `GameInstance_BP_C`.
5. Si rien ne marche : revenir au contournement officiel GameLift
   (réécriture des latences) ou au plan B.

---

## 8. Lancement / désinstallation

### Lancer avec UE4SS

```powershell
powershell -ExecutionPolicy Bypass -File tools\launch_ue4ss.ps1 -Windowed
```

Ou manuellement :

```text
F:\SteamLibrary\steamapps\common\MotoGP19\motogp19\Binaries\Win64\motogp19-Win64-Shipping.exe -log -windowed -ResX=1280 -ResY=720
```

### Lancer normalement via Steam

Steam utilise le chemin réel `MotoGP™19`. UE4SS se charge mais les mods Lua
échouent à cause du `™`. Pour désactiver UE4SS au lancement, ajouter
`--disable-ue4ss` aux options de lancement Steam.

### Désinstaller UE4SS

```powershell
powershell -ExecutionPolicy Bypass -File tools\uninstall_ue4ss.ps1 `
  -RestoreBackup "F:\MotoGP19-MultiRE\backups\ue4ss-20261110-202311" `
  -RestoreConfig
```

Puis supprimer la jonction si souhaité :

```powershell
cmd /c rmdir "F:\SteamLibrary\steamapps\common\MotoGP19"
```

L'appmanifest Steam est déjà restauré ; en cas de doute, le backup est dans
le dossier de sauvegarde.

---

## 9. Avertissement

- `bVACEnabled=1` : UE4SS est une injection de DLL.
- Ne pas l'utiliser sur les serveurs en ligne officiels.
- Pour les tests : compte secondaire ou mode hors ligne.
- Ne pas distribuer de binaire patché.
- Usage privé / interopérabilité uniquement.
