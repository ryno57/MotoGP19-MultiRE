# Voie A — revue des acquis et alternatives

Date : 2026-11-10

---

## 1. Acquis récents

- Client MotoGP 19 = **UE 4.21**, pur client, Steam AppID 984780.
- Backend MileNet + AWS GameLift compris.
- `ReserveSpot` renvoie `IpAddress`, `Port`, `playerData` avec clé AES-256
  et nonce 12 o.
- Protocole UDP UE4 : handshake, `NMT_Hello` avec `?EncryptionToken=psess`,
  AES-256-GCM. Déchiffré sur une session réelle.
- Mock MileNet fonctionnel : login, `Regions`, `Create`, `ReserveSpot`,
  handshake. Le client accepte notre IP/port et envoie son `psess`.
- UE4SS v3.0.1 fonctionne sur 4.21 via jonction ASCII.
- CXX Header Dump disponible.
- Le client ne contient pas le SDK GameLift serveur
  (`InitSDK`, `ProcessReady`, etc. absents).

## 2. Ce qui a échoué

- `-server` : démarre un client normal.
- map en argument : ignorée.
- `GameDefaultMap` + `LocalMapOptions` : chargement infini.
- `open` / `ServerTravel` / `ClientTravel` / Kismet `ExecuteConsoleCommand` :
  spinner de chargement, monde = menu, aucun UDP 7777.
- `CreateAdvancedSession(bUseLAN=true)` : proxy créé, aucune session.
- `SetPlayInLan(true)` + `CreateOnlineSession()` : aucun effet visible.
- UI + Null OSS : crash (`MenuGameState`) ou freeze.
- `GetDefaultCreateSettings()` : out-params inutilisables en Lua.

## 3. Distinction importante

Le comportement observé (spinner, pas de socket) ressemble à un
**`ClientTravel`** : le client essaie de se connecter à un serveur qui
n'existe pas. Un **listen server** nécessite un `ServerTravel` ou un
`OpenLevel` exécuté avec autorité.

Le code du jeu peut intercepter la commande `open` et forcer un
`ClientTravel`. Il faut donc contourner le FSM et appeler les fonctions
**engine** directement.

---

## 4. Alternatives autour de la Voie A

### A1. `UGameplayStatics::OpenLevel(..., "listen")`

```lua
local gameplay = UEHelpers.GetGameplayStatics()
gameplay:OpenLevel(
  world,
  "/Game/maps/lobby/lobby",
  true,
  "listen?game=/Game/assets/data/gamemodes/multiplayer/LobbyGameModeBP.LobbyGameModeBP_C"
)
```

Pourquoi c'est prometteur :

- fonction UE4 standard ;
- en `NM_Standalone`, `OpenLevel` appelle `ServerTravel` (autorité) ;
- peut démarrer un listen server sans passer par le FSM du jeu.

Risque : le `GameMode`/`GameInstance` du jeu peut annuler le voyage.

### A2. `UWorld::ServerTravel` avec `bAbsolute=true`

```lua
world:ServerTravel(
  "/Game/maps/lobby/lobby?listen?game=/Game/assets/data/gamemodes/multiplayer/LobbyGameModeBP.LobbyGameModeBP_C",
  true,
  false
)
```

Pourquoi :

- on a testé `bAbsolute=false` ; le jeu logue un avertissement sur le
  `Travel_RELATIVE` ;
- `bAbsolute=true` évite ce problème ;
- en standalone, `ServerTravel` doit passer en `NM_ListenServer`.

### A3. Charger la map serveur `/Game/maps/server/idle?listen`

```lua
gameplay:OpenLevel(world, "/Game/maps/server/idle", true, "listen")
```

Pourquoi :

- c'est la `ServerDefaultMap` du jeu ;
- le serveur dédié démarre sur `idle`, pas sur `lobby` ;
- cette map peut initialiser le `GameSession`/`DedicatedServerComponent`
  et ouvrir le NetDriver.

### A4. `SetPlayInLan(true)` **avant** d'ouvrir l'UI

- appeler `manager:SetPlayInLan(true)` au menu principal ;
- puis naviguer MULTIJOUEUR → COURSES → CRÉER UN SALON ;
- le FSM pourrait construire une session LAN au lieu d'une session
  GameLift.

Testé : `SetPlayInLan` + `CreateOnlineSession` au menu, pas avant l'UI.
C'est une variation non testée.

### A5. Lire les propriétés du FSM à l'écran de création

À l'écran « CRÉATION DE SALON » :

```lua
local props = manager:GetCreateSessionProperties(false)
local max = manager.MaxPlayers
manager:SetPlayInLan(true)
manager:SetCreateSessionProperties(props, max, false)
manager:CreateOnlineSession()
```

Pourquoi :

- le FSM a déjà rempli `CreateSessionProperties` ;
- `GetCreateSessionProperties(false)` n'a pas d'out-param ;
- on évite `GetDefaultCreateSettings` qui casse le script.

Risque : Null OSS peut encore crasher.

### A6. `StartMatchmaking` avec `bUseLAN=true`

`UStartMatchmakingCallbackProxyAdvanced::StartMatchmaking` prend un
`FBPOnlineSessionSettings` simple :

```lua
local settings = {
  NumMaxPlayers = 12,
  bIsLANMatch = true,
  bIsDedicated = false,
  bUseMigration = false,
  Joinability = 0,
  Settings = {},
}
proxy_class:StartMatchmaking(world, {}, "GameSession", settings, {}, 30, 10, true)
```

Pourquoi :

- le proxy gère le succès/échec et le manager peut voyager vers le lobby ;
- `bIsLANMatch=true` peut créer une session locale ;
- le struct est plus simple que `FSessionPropertyKeyPair`.

### A7. `AGameSpecificGameSession::CreateSession()`

- le menu contient un `IgnitionGameSession` ;
- `AGameSpecificGameSession` a une fonction `CreateSession()` ;
- dans une map de jeu, cet acteur peut être le composant serveur ;
- appeler `CreateSession()` pourrait démarrer la session locale.

À tester après avoir chargé une map (via A1/A2).

### A8. `UGameLiftServerGameSessionComponent`

- inspecter ses fonctions/propriétés dans le CXX dump ;
- si `SessionMap`/`StartGameSession` sont exposés, les appeler ;
- le SDK GameLift n'est pas lié, mais le composant peut avoir une logique
  locale partielle.

### A9. Dépôt Steam « Dedicated Server »

- vérifier avec SteamCMD `app_info_print 984780` s'il existe un dépôt
  serveur séparé ;
- beaucoup de jeux UE4 publient un outil « Dedicated Server » gratuit ;
- si ce binaire existe, la Voie A est résolue sans bidouille client.

C'est l'alternative **la plus rentable** à vérifier : elle peut rendre
tout le reste inutile.

### A10. Ligne de commande `-server -game -ExecCmds`

```text
motogp19-Win64-Shipping.exe -server -game -nullrhi -log -port=7777 `
  -ExecCmds="open /Game/maps/server/idle?listen"
```

Pourquoi :

- variante non testée de `-server` ;
- `-game` et `-ExecCmds` peuvent forcer le chargement de la map.

### A11. Serveur UE4 4.21 générique + paks du jeu

- monter les paks dans un serveur UE4 4.21 ;
- charger `LobbyGameModeBP` ;
- très lourd, et le module C++ du jeu est dans le Shipping.exe ;
- dernière option si tout le reste échoue.

---

## 5. Ce qu'il faut arrêter de tester

- `-server` seul ;
- map en argument seul ;
- `open` console seul ;
- `CreateAdvancedSession` avec des settings vides ;
- `SetPlayInLan` + `CreateOnlineSession` sans propriétés ;
- UI + Null OSS sans propriétés du FSM.

Ces pistes sont documentées comme impasses.

---

## 5 bis. Résultats des tests (2026-11-10)

- **A1 `OpenLevel` + `listen`** : log `A1 OpenLevel lobby listen`, puis
  dialogue « services Milestone », spinner, **freeze du processus**
  (`Responding=False`). Aucun `NetMode`/`NetDriver`, aucun UDP 7777.
- **A2 / A3** : non testés, A1 ayant figé le jeu avant.
- **A9 dépôt Steam serveur** : `app_info_print 984780` ne liste que
  `984781` (jeu) + shared + DLC ; aucun dépôt serveur.
  Recherche Steam Store : aucun outil « Dedicated Server ».
  **A9 est mort.**
- **A10 dernier test — injection `?Listen` dans le voyage offline** :
  hook de `GetOptionsToPassInNewLevel` + `OnServerTravel`, flag F9.
  L'URL de voyage contient bien `?Listen`, Mugello se charge et le joueur
  roule sur la piste, mais **aucun socket UDP** n'est ouvert et aucun
  `NetDriver` n'existe sur le monde principal. `ServerTravel` ne traite pas
  `?Listen` comme la commande `open`.
- Conclusion : même un appel engine direct fige le client, et injecter
  `?Listen` dans le flux offline ne crée pas de serveur. La Voie A est
  **définitivement morte**.

Il reste :

1. **Voie B** : backend officiel + correctif de latences.
2. **Plan B** : autre jeu avec serveur dédié.

---

## 6. Recommandation

Ordre des prochains tests :

1. **A1 — `OpenLevel` avec `listen`** (le plus standard).
2. **A2 — `ServerTravel` avec `bAbsolute=true`**.
3. **A3 — `server/idle?listen`**.
4. **A9 — dépôt Steam serveur** (en parallèle, peut tout résoudre).
5. **A4/A5 — FSM avec propriétés** si A1/A2 échouent.
6. **A6 — `StartMatchmaking` LAN**.

Chaque test doit vérifier :

- `World.NetMode` (0=Standalone, 1=Dedicated, 2=Listen, 3=Client) ;
- `World.NetDriver` non nul ;
- `Get-NetUDPEndpoint -LocalPort 7777` ;
- le monde chargé (`World:GetFullName()`).

Si A1/A2/A3 échouent et qu'aucun dépôt serveur n'existe, la Voie A est
très probablement morte : il faudra passer à la Voie B ou au plan B.
