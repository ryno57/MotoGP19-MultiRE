# MotoGP 19 — Community Host / MultiMod
## Fichier de suivi du projet

Dernière mise à jour : 2026-11-10

---

## 0. Protocole de travail (convention)

À partir de maintenant :

- Tout ce qui n'est pas du texte pur (code, fichiers, tests, commandes) se fait
  **par petits ou moyens morceaux**.
- Après chaque morceau : **arrêt**, puis mise à jour de ce fichier + résumé court
  dans la conversation.
- On ne lance pas une grosse phase d'un coup.
- On ne modifie jamais les paks ni les exécutables du jeu.
- Chaque modification de config utilisateur est sauvegardée puis restaurée.

---

## 1. Objectif du projet

Permettre à une ligue sur MotoGP 19 (Milestone, UE4) d'héberger ses courses
sur les PC des joueurs, au lieu de dépendre des serveurs Milestone, afin
d'éviter les déconnexions en pleine course.

Pistes :

1. Serveur local / listen server + connexion directe par IP.
2. Si nécessaire : mock du backend MileNet + faux GameLift pour rediriger
   les clients vers le serveur du host.
3. Launcher Windows pour rendre tout ça simple pour la ligue.

---

## 1 bis. Décisions validées (2026-11-10)

- **Phase A timeboxée à 4 soirées.** Si aucun serveur local n'est créé,
  on s'arrête et on réévalue.
- **Focus sur la Voie A** (serveur local via UE4SS). La Voie B (backend
  officiel) est mise de côté pour l'instant.
- **UE4SS sur le compte principal, Steam en mode hors ligne.**
  - Pas de matchmaking officiel avec UE4SS chargé.
  - Tests locaux uniquement.
  - Compte secondaire conseillé si possible.
- **Launcher : le plus pratique et visible.** Cible GUI, avec un socle CLI
  réutilisable. La GUI arrive après validation du serveur local.
- **2e PC : fourni par le pote** pour les tests de connexion.
- **Le pote n'a pas de résultats UE4SS supplémentaires** : nous sommes en
  avance sur ce point.
- Feuille de route détaillée : `docs/ROADMAP.md`.

---

## 2. État actuel

**Phase : Voie A épuisée (serveur local impossible). Décision : Voie B ou plan B.**

Le jeu démarre hors ligne jusqu'au menu principal.
Le lancement en `-server` ne produit pas de socket d'écoute sur 7777.
Le build shipping n'écrit pas de log fichier exploitable.
La console en jeu n'a pas encore été testée manuellement.

Le socle `mgp19/` est en place : détection Steam, profils de config,
sauvegarde/restauration, diagnostic réseau, pare-feu, lancement host/join
via Steam et enregistrement de sessions.

Le launcher a été testé en conditions réelles : profil appliqué, jeu lancé,
session enregistrée, config restaurée. **Mais le test n'a pas produit de
serveur local** : la map passée en argument est ignorée, et le profil
`direct-connect` coupe l'accès MileNet, ce qui déclenche des dialogues
« services Milestone inaccessibles ».

Des informations externes (contact sous Linux/Proton + scripts) ont été
recoupées : elles confirment que **le binaire client n'embarque pas le SDK
GameLift serveur** et que `-server` n'active pas de serveur dédié.
Voir `docs/EXTERNAL-INTEL.md`.

**Mise à jour importante** : les artefacts fournis par le contact
(`flows.mitm`, `mem_hits.txt`, `race_session.pcap`, etc.) ont permis de
déchiffrer une session réelle (3563/3572 paquets). Le protocole HTTP et UDP
est maintenant confirmé et documenté dans `docs/PROTOCOL-CONFIRMED.md`.
Le serveur observé est une instance AWS GameLift officielle, pas un serveur
local. Le problème du serveur local reste entier.

Le **faux backend MileNet** a été testé avec le vrai jeu : login, `Regions`,
`Create` et `ReserveSpot` acceptés ; le mock répond au handshake UE4 et le
client envoie son paquet `psess-...` / `NMT_Hello`. Le **control plane est
maîtrisé**. Il reste à envoyer le `NMT_Welcome` / la réplication (ou à utiliser
UE4SS) pour obtenir un vrai serveur de jeu.

**UE4SS v3.0.1** est installé et se charge sur UE 4.21. Les mods Lua ne
fonctionnaient pas à cause du `™` dans le chemin ; une jonction ASCII
(`F:\SteamLibrary\steamapps\common\MotoGP19`) et un lancement direct via
`steam_appid.txt` ont résolu le problème. La console UE4SS et le dump de
classes fonctionnent. `open` / `ServerTravel` sont exécutés mais ne créent
pas de serveur local : le monde reste le menu avec un écran de chargement.
Le session manager a été inspecté via le CXX Header Dump :
`SetPlayInLan(bool)` et `CreateOnlineSession()` existent et s'exécutent sans
erreur, mais ne créent pas encore de session locale. Prochaine piste :
`CreateAdvancedSession(bUseLAN=true)` ou le FSM `UMpCreateSessionFsmState`.

> Note : le projet a été déplacé dans `F:\MotoGP19-MultiRE` (dépôt git).
> C'est ce dossier qui fait foi désormais.

---

## 3. Faits vérifiés sur l'installation

- Jeu : `F:\SteamLibrary\steamapps\common\MotoGP™19`
- Moteur : **Unreal Engine 4.21**
- Binaire : `motogp19/Binaries/Win64/motogp19-Win64-Shipping.exe`
- Bootstrap : `motogp19.exe` (lance le Shipping)
- `n.VerifyPeer=false` déjà présent dans la config → TLS permissif
- NetDriver : `SteamNetDriver` avec fallback `IpNetDriver`
  (la ligne `IpNetDriver` est présente en commentaire dans `DefaultEngine.ini`)
- Backend :
  - `LiveBaseUrl = online-milestone2.eu-west-1.elasticbeanstalk.com`
  - `MileNet.ShippingServer = online.milestone.it`
  - `MileNetAppId = 5c347579d008650df4620a08`
- Manifest API MileNet complet dans `DefaultEngine.ini`
- Réponse de session de jeu contenant :
  - `IpAddress`
  - `Port`
  - `PlayerSessionId`
  - `EncryptionKey`
  - `EncryptionNonce`
  - `GameSessionId`, `Region`, `Properties`
- Le binaire contient :
  - `GameLiftServerSDK`
  - `UGameLiftServerGameSessionComponent`
  - `UDedicatedServerGameSessionComponent`
  - `bIsDedicatedServer`
  - support `DedicatedServerGame.ini` / `DedicatedServerEngine.ini`
- Maps serveur présentes dans les paks :
  - `/Game/maps/server/idle`
  - `/Game/maps/lobby/lobby`
- Maps de course présentes, ex. :
  - `/Game/maps/Tracks/mugello/mugello`
- CVars de dev présentes :
  - `Online.ListenServerAllowed`
  - `Online.HostAloneAllowed`
  - `Online.IgnoreRolePlayerRestrictions`
  - `Online.ForceAdvertise`
  - `Online.ForceJoinability`
  - `Online.OverrideMaxPlayers`
  - `Online.MatchMakingVersion`
- `ConsoleKeys=Tilde` et `ConsoleKeys=F1` dans `DefaultInput.ini`
  mais aussi `ConsoleKey=None` → console peut-être désactivée en shipping.
- Les symboles du SDK GameLift serveur sont **absents** des strings :
  `InitSDK`, `ProcessReady`, `StartGameSession`, `AcceptPlayerSession`, `FleetId`.
  `GameLiftServerSDK` n'apparaît que comme nom de module.
- Les composants serveur existent toutefois comme chaînes :
  `UGameLiftServerGameSessionComponent`,
  `UDedicatedServerGameSessionComponent`,
  `Session map not set for dedicated server`,
  `UDedicatedServerGameSessionComponent::RetrieveEncryptionInformations not implemented`.
- `AESGCM`, `EncryptionToken`, `NMT_Hello`, `PlayerSessionId`, `playerData`
  sont présents → cohérent avec le protocole décrit par le contact externe.
- `IpNetDriver listening on port` et `LocalMapOptions` sont présents.

---

## 4. Tests déjà effectués

### Test 1 — lancement direct du Shipping en `-server`

- Commande : map `idle`, `-server -nullrhi -log -nosteam -port=7777`
- Résultat : le process démarre puis tente de passer par Steam.
- Aucun log fichier produit.
- Lancé via Steam (`SteamAPI_RestartAppIfNecessary`) : le jeu tourne,
  connexion TCP vers MileNet observée, port 27015 (Steam GameServer) ouvert,
  mais **pas de 7777**.

### Test 2 — override config `DefaultPlatformService=NULL`

- `IpNetDriver` forcé, `net.AllowEncryption=0`, CVars online activées.
- Le process tourne, mais **aucun socket d'écoute**.
- Pas de log fichier.
- Conclusion : le mode `-server` attend probablement une session
  MileNet/GameLift avant de créer le NetDriver.

### Test 3 — lancement client normal

- Le jeu s'ouvre sur l'écran « Appuyer sur une touche ».
- Puis menu principal accessible, entrée **MULTIJOUEUR** visible.
- Donc le jeu est utilisable hors ligne jusqu'au menu.

### Nettoyage

- `steam_appid.txt` temporaire supprimé.
- `Engine.ini` restauré depuis sauvegarde.
- Sauvegarde conservée :
  `%LOCALAPPDATA%\motogp19\Saved\Config\WindowsNoEditor\Engine.ini.bak-motogp19-multimod`
- ⚠️ Effet de bord restant : `GameUserSettings.ini` est passé en **1920×1080**
  à cause du test en fenêtre. À remettre en **2560×1440** (ou via options jeu).

---

## 5. Livrables déjà présents

- `SUIVI.md` — journal de bord
- `mgp19/` — socle Python
  - `paths.py` — détection Steam / installation / chemins utilisateur
  - `config.py` — lecture-écriture .ini UE4, profils, backups
  - `network.py` — IP locale/publique, endpoints, ports UDP, pare-feu
  - `launcher.py` — lancement Steam, modes host/join, sessions, logs
  - `mock_backend.py` — faux backend MileNet local (HTTPS + RSA/AES + Create/ReserveSpot + handshake + UDP probe)
  - `cli.py` — commandes `doctor`, `profiles`, `apply`, `restore`, `status`, `net`, `firewall`, `host`, `join`, `sessions`, `mock`
  - `__main__.py` — `python -m mgp19 ...`
- `profiles/vanilla.json` — aucune modification
- `profiles/direct-connect.json` — override Null OSS + IpNetDriver + CVars
- `profiles/mock-milenet.json` — redirection MileNet vers `localhost:8443`
- `tests/test_config.py` — 9 tests unitaires
- `tests/test_network.py` — 12 tests unitaires
- `tests/test_launcher.py` — 8 tests unitaires
- `tests/test_mock_backend.py` — 4 tests unitaires (crypto + serveur + session + handshake)
- `docs/README.md` — structure et commandes
- `docs/MOCK-BACKEND.md` — utilisation du faux backend
- `docs/MOCK-TEST-RESULTS.md` — résultats du test réel 6C
- `docs/UE4SS-INSTALL.md` — installation UE4SS, jonction ASCII, tests
- `docs/ROADMAP.md` — feuille de route validée, phases et jalons
- `docs/VOIE-A-ALTERNATIVES.md` — revue des acquis et alternatives serveur local
- `tools/install_ue4ss.ps1`, `tools/uninstall_ue4ss.ps1`, `tools/launch_ue4ss.ps1`
- UE4SS v3.0.1 installé dans `motogp19/Binaries/Win64`
- jonction ASCII `F:\SteamLibrary\steamapps\common\MotoGP19` → `MotoGP™19`
- backup `backups/ue4ss-20261110-202311/` (Win64, config, saves, appmanifest)
- `docs/PHASE1-RESULTS.md` — compte rendu du premier test réel
- `docs/EXTERNAL-INTEL.md` — analyse des infos du contact
- `docs/PROTOCOL-CONFIRMED.md` — protocole HTTP/UDP confirmé par les artefacts
- `work/race_clear.jsonl` — session UDP déchiffrée (hex, direction, temps)
- `work/flows.strings.txt` — chaînes extraites de `flows.mitm`
- `work/inspect_pcaps.py`, `work/inspect_all.py` — inventaire des captures
- `work/decrypt_race.py` — déchiffrement du pcap avec la clé mémoire
- `tools/strings_extract.py` — extraction de strings (ASCII + UTF-16)
- `tools/pak.py` — lecteur / extracteur de `.pak` UE4
- `work/strings/shipping.txt` — strings du binaire
- `work/config/DefaultEngine.ini`
- `work/config/DefaultGame.ini`
- `work/config/DefaultInput.ini`
- `work/config/WindowsEngine.ini`
- `work/config/WindowsGame.ini`
- `work/test1..5/` — sorties des tests de lancement

---

## 6. Décisions prises

1. Priorité au **serveur local / direct connect** avant tout mock backend.
2. Ne pas réimplémenter le netcode : le jeu utilise la réplication UE4 standard.
3. Ne pas toucher aux paks ni aux exécutables.
4. Utiliser des **profils de config** sauvegardés/restaurés automatiquement.
5. Le mock MileNet n'est construit que si le test direct échoue.
6. Chaque fonctionnalité du launcher doit être adossée à un fait vérifié.

---

## 7. Prochaine étape (Phase 1 — test décisif)

Objectif : obtenir une map de course en mode serveur et connecter un 2e client.

Ordre :

1. Tester manuellement la console en jeu : `~` puis `F1`.
2. Si console OK :
   ```
   open /Game/maps/Tracks/mugello/mugello?listen
   ```
3. Vérifier l'apparition d'un socket 7777.
4. Depuis un 2e PC :
   ```
   open <IP_du_host>:7777
   ```
5. Si échec : forcer `IpNetDriver` + `net.AllowEncryption=0` via le profil
   `direct-connect`.
6. Si la map charge mais pas la course : analyser `GameMode` / session / FSM.
7. Documenter le résultat dans `docs/PHASE1-RESULTS.md`.

Critère de sortie : un 2e client voit le host et une course peut démarrer.

### Morceau 3 — terminé

`network.py` + commandes de diagnostic réseau :
- IP locale / publique
- endpoint `ip:port`
- test d'écoute UDP du port 7777
- règle de pare-feu Windows (vérification + ajout explicite)
- parsing des endpoints pour les futurs `host` / `join`

### Morceau 4 — terminé

`launcher.py` + commandes `host` / `join` / `sessions` :
- lancement du jeu via Steam avec arguments
- mode `host` (map + `?listen` + port)
- mode `join` (endpoint)
- application / restauration automatique du profil
- collecte des logs et métadonnées de session
- récupération d'une session restée active

### Morceau 5 — test réel effectué (résultat négatif)

Test :

- `python -m mgp19 host --yes`
- profil `direct-connect`, map Mugello `?listen`, port 7777
- session `20261110-190919-host`, durée 162,8 s

Observé :

1. Le jeu démarre normalement.
2. Écran sauvegarde automatique, puis « Appuyer sur une touche ».
3. Dialogue « Un nouveau correctif est disponible ».
4. Dialogue « Vous ne pouvez pas accéder aux services de Milestone ».
5. Après « Annuler » : spinner de chargement, puis sortie du jeu.
6. **Aucun socket UDP 7777** de toute la session.

Conclusion :

- Les arguments Steam sont bien transmis.
- La map en argument ne déclenche pas de serveur local.
- Le profil `direct-connect` empêche l'accès MileNet et bloque le flux online.
- Le launcher lui-même fonctionne : profil appliqué, jeu lancé, session
  enregistrée, config restaurée, logs collectés.

Détails : `docs/PHASE1-RESULTS.md`.

### Nouvelle orientation après les infos externes

Le test console reste utile, mais il n'est plus la seule priorité.
Le contact a montré que :

- le client ne peut pas démarrer en serveur dédié (`-server` inopérant) ;
- la map en argument est ignorée ;
- le SDK GameLift serveur n'est pas lié dans le binaire client ;
- le protocole HTTP et UDP est maintenant connu.

Plan révisé :

**A. Solution de secours immédiate (officielle)**

1. Reproduire sur Windows le correctif de latences du contact.
2. Rediriger `[MileNetOnline] LiveBaseUrl` vers le proxy local.
3. Héberger via le backend officiel, en forçant une région proche.
4. Documenter clairement que ça dépend encore de Milestone.

**B. Chemin vers l'indépendance**

1. Tester UE4SS sur UE 4.21 :
   - console,
   - export des classes,
   - inspection de `UGameLiftServerGameSessionComponent`,
     `UDedicatedServerGameSessionComponent`, `UGameSessionSettings`.
2. Tenter `open` / `ServerTravel` avec la map lobby et le bon GameMode.
3. Si un listen server démarre :
   - construire le faux backend MileNet,
   - répondre à `Create` / `ReserveSpot` avec notre IP/port et notre clé,
   - fournir la clé AES/nonce au serveur.
4. Si UE4SS échoue : Ghidra sur les chaînes serveur, ou plan B.

**C. Si aucun serveur local n'est possible**

- Le contournement officiel reste la solution pragmatique.
- L'indépendance totale exigerait de récupérer un binaire serveur ou de
  réécrire le netcode.

Détails et niveau de confiance : `docs/EXTERNAL-INTEL.md`.

---

## 8. Inconnues à trancher

| Inconnue | Méthode | Statut |
|---|---|---|
| Code serveur fonctionnel dans le binaire | strings SDK + test `-server` | **non** : SDK GameLift absent, `-server` inopérant |
| Listen server possible | UE4SS / console / `ServerTravel` | inconnu, à tester |
| Connexion client directe | test 2 PC | inconnu, dépend du serveur |
| Course démarrable sans MileNet | observation FSM / UE4SS | inconnu |
| Format exact des réponses de session | memory scan / capture | **ReserveSpot confirmé**, `Create` inconnu |
| Chiffrement HTTP RSA/AES | `flows.mitm` + artefacts | **confirmé** (RSA-OAEP-SHA1 + AES-128-CBC) |
| Chiffrement UDP AES-256-GCM | pcap déchiffré | **confirmé** (3563/3572 paquets) |
| SteamNetDriver vs IpNetDriver | override config | `IpNetDriver` forçable |
| Algorithme `WWW-Authenticate` | reverse | inconnu, non bloquant pour un mock |

---

## 9. Plan des phases (rappel)

- **Phase 1** — test décisif serveur local / direct connect
- **Phase 2** — socle launcher (`paths`, `config`, `launcher`, `diagnostics`)
- **Phase 3** — UX ligue (host/join, port forwarding, supervision)
- **Phase 4** — mock MileNet (si nécessaire)
- **Phase 5** — industrialisation (installateur, docs, tests)

---

## 10. Journal des sessions

### 2026-11-10 — Reconnaissance + tests initiaux

- Analyse des paks et du binaire.
- Découverte de l'architecture MileNet / GameLift.
- Tests de lancement `-server` et client.
- Nettoyage des modifications temporaires.
- Rédaction de ce fichier de suivi.
- Prochain morceau : test console manuel, puis listen server.

### 2026-11-10 — Morceau 2 : socle launcher

Créé :

- `mgp19/paths.py` : détection Steam via registre + `libraryfolders.vdf`,
  lecture de `appmanifest_984780.acf`, gestion du `™` dans le chemin,
  chemins `%LOCALAPPDATA%\motogp19`, détection du jeu en cours.
- `mgp19/config.py` : parseur `.ini` UE4 qui préserve commentaires et fins
  de ligne, opérations `set` / `append` / `clear_array` / `remove`,
  profils JSON, sauvegarde `.original.mgp19bak`, snapshots horodatés,
  écriture atomique, restauration.
- `mgp19/cli.py` + `__main__.py` : `doctor`, `profiles`, `apply`,
  `restore`, `status`, avec mode aperçu par défaut (`--yes` pour écrire).
- `profiles/vanilla.json`, `profiles/direct-connect.json`.
- `tests/test_config.py` : 9 tests, tous OK.
- `docs/README.md`.

Vérifications :

- `python -m unittest discover -s tests` → 9 tests OK.
- `python -m mgp19 doctor` → installation complète détectée.
- `python -m mgp19 apply direct-connect` → diff correct, **aucune écriture**.
- `python -m mgp19 status` → aucune sauvegarde, non modifié.
- `python -m mgp19 restore Engine.ini` → erreur propre (pas de backup).

Aucun profil n'a été appliqué au vrai `Engine.ini`.
Prochain morceau : `network.py` + diagnostics réseau.

### 2026-11-10 — Morceau 3 : diagnostics réseau

Créé :

- `mgp19/network.py` :
  - `local_ip()` sans envoi de paquet
  - `public_ip()` optionnel via service externe
  - `format_endpoint()` / `parse_endpoint()` (IPv4, IPv6 entre crochets)
  - `port_free()` / `udp_listeners()` pour le port 7777
  - `firewall_rule_exists()`, `ensure_firewall_rule()` via `netsh`
  - `diagnostics()` qui agrège le tout
- `tests/test_network.py` : 12 tests.
- `cli.py` : commandes `net` et `firewall`.
- `docs/README.md` mis à jour.

Vérifications :

- `python -m unittest discover -s tests` → **21 tests OK**.
- `python -m mgp19 net` → IP locale `192.168.0.11`, endpoint `192.168.0.11:7777`,
  port libre, règle pare-feu absente.
- `python -m mgp19 firewall` → aperçu de la commande `netsh`, aucune écriture.
- `python -m mgp19 firewall --range` → aperçu plage 7777-8077.

Aucune règle de pare-feu n'a été ajoutée (pas d'admin, pas de `--yes`).
Prochain morceau : `launcher.py` (host / join + application de profil).

### 2026-11-10 — Morceau 4 : launcher host / join

Créé :

- `mgp19/launcher.py` :
  - `LaunchPlan` host/join avec arguments de jeu
  - `find_steam_exe()` + `steam_command()`
  - `run_session()` : applique le profil, lance via Steam, attend le jeu,
    restaure la config, collecte les logs
  - `SessionRecorder` : `session.json`, config avant/après, diagnostic réseau,
    logs / crashs si disponibles
  - `recover_previous_sessions()` : restaure une session restée active
- `tests/test_launcher.py` : 8 tests.
- `cli.py` : commandes `host`, `join`, `sessions`.
- `.gitignore` : ajout de `sessions/`.
- `docs/README.md` mis à jour.

Vérifications :

- `python -m unittest discover -s tests` → **29 tests OK**.
- `python -m mgp19 host` → plan correct :
  map Mugello `?listen`, port 7777, endpoint `192.168.0.11:7777`,
  commande Steam affichée, **aucun lancement**.
- `python -m mgp19 join 192.168.0.42` → plan join correct, **aucun lancement**.
- `python -m mgp19 join 192.168.0.42:99999` → erreur propre.
- `python -m mgp19 host --track losail --port 7778` → map et port corrects.
- `python -m mgp19 sessions` → aucune session.

Aucun lancement réel, aucune écriture de config, aucune règle pare-feu.
Prochain morceau : test réel host/join sur deux PC.

### 2026-11-10 — Morceau 5 : premier test réel host

Exécuté :

- `python -m mgp19 host --yes`
- profil `direct-connect`
- map `/Game/maps/Tracks/mugello/mugello?listen`
- port 7777

Résultat :

- le jeu démarre, affiche l'avertissement de sauvegarde puis l'écran
  « Appuyer sur une touche » ;
- dialogue « Un nouveau correctif est disponible » ;
- dialogue « Vous ne pouvez pas accéder aux services de Milestone » ;
- après « Annuler », spinner puis sortie du jeu ;
- **aucun port UDP 7777 ouvert** ;
- le launcher a bien restauré `Engine.ini` et collecté la session.

Interprétation :

- les arguments Steam passent bien ;
- la map en argument ne lance pas de serveur ;
- le profil `direct-connect` coupe MileNet et bloque le flux online ;
- il faut tester le listen server via la console, en vanilla.

Document : `docs/PHASE1-RESULTS.md`.
Prochain morceau : test console `~` / `F1` + `open ...?listen`.

### 2026-11-10 — Infos externes (contact Linux/Proton)

Reçu : `message.txt`, `scan_mem.py`, `mitm_addon.py`.

Recoupement avec nos strings :

- `InitSDK`, `ProcessReady`, `StartGameSession`, `AcceptPlayerSession`,
  `FleetId` : **absents** → le SDK GameLift serveur n'est pas lié.
- `GameLiftServerSDK` : présent uniquement comme nom de module.
- `Session map not set for dedicated server` et
  `RetrieveEncryptionInformations not implemented` : présents.
- `AESGCM`, `EncryptionToken`, `NMT_Hello`, `PlayerSessionId`, `playerData` :
  présents → cohérent avec le protocole décrit.

Conséquences :

- le binaire client n'est très probablement pas un serveur dédié ;
- `-server` et la map en argument sont confirmés inopérants ;
- le chemin « serveur local » passe par UE4SS / listen server forcé ;
- le faux backend MileNet est faisable (crypto et endpoints connus) ;
- le contournement officiel par réécriture des latences est une solution
  de secours immédiate.

Document : `docs/EXTERNAL-INTEL.md` (tableau de confiance + plan révisé).

### 2026-11-10 — Analyse des artefacts du contact

Reçu : `flows.mitm`, `mem_hits.txt`, `ue4_decrypt.py`,
`mgp19_local.pcap`, `mgp19_server.pcapng`, `race_session.pcap`.

Résultats :

- `race_session.pcap` déchiffré avec la clé lue dans `mem_hits.txt` :
  **3563/3572 paquets**, 13,9 Ko C→S et 20,7 Ko S→C.
- Login client observé en clair :
  `/Game/maps/startup/startup?EncryptionToken=psess-...?Name=<pseudo>
  ?NativeId=<steamid>?MLLobbyDLCs=0?PlayerSessionId=psess-...`
- Welcome serveur : `/Game/maps/lobby/lobby` +
  `LobbyGameModeBP.LobbyGameModeBP_C`.
- Classes de lobby confirmées : `LobbyPlayerControllerBP`,
  `LobbyGameState`, `LobbyPlayerState`, `WeekendCompetitionBP`,
  `RaceSelectionControllerComponent`, etc.
- `ReserveSpot` confirmé par `mem_hits.txt` (PlayerSession GameLift +
  `playerData` avec `EncryptionKey`/`EncryptionNonce`).
- `flows.mitm` confirme les en-têtes, endpoints et tailles :
  `Create` réponse 832 o, `ReserveSpot` réponse 1260 o,
  `Authorization` constant, `WWW-Authenticate` variable.
- `mgp19_local.pcap` = TCP loopback vers `127.0.0.1:8443` (proxy), pas un
  serveur local.
- `mgp19_server.pcapng` = TCP de contrôle (AWS/Steam/DNS), pas de UDP de jeu.

Conséquences :

- le protocole HTTP/UDP est confirmé et documenté ;
- le serveur observé est une instance GameLift officielle, pas un serveur local ;
- le problème du serveur local reste entier (UE4SS / listen server) ;
- le mock backend est faisable, mais il faut un serveur à pointer.

Document : `docs/PROTOCOL-CONFIRMED.md`.

### 2026-11-10 — `requests.jsonl`

Reçu les corps de requêtes déchiffrés (10 lignes).

Confirmé :

- Login : `{"createNew": false, "buildId": 4909173, "branch": "public"}`
  (`EncryptionKey` et `AuthToken` sont retirés par l'addon).
- `Create` : `Latencies` (6 régions), `MaxPlayers: 12`,
  `Alias: "MGP19-<pseudo>"`, `Properties.PlatformSessionId`.
- `ReserveSpot` : `GameSessionId` ARN.
- Deux tentatives : `us-west-1` puis `eu-central-1` ; la seconde correspond
  à `race_session.pcap` / `mem_hits.txt`.

Toujours inconnu :

- le schéma de la réponse `Create` (832 o chiffrés) ;
- l'algorithme `WWW-Authenticate` (non bloquant pour un mock).

Document : `docs/PROTOCOL-CONFIRMED.md`.

### 2026-11-10 — Morceau 6A : faux backend MileNet (control plane)

Créé :

- `mgp19/mock_backend.py` :
  - HTTPS local + certificat auto-signé
  - paire RSA-1024 pour les corps
  - `GET /Security/PublicKey`
  - `POST /PlayerProfile/Steam/Login` (déchiffrement, token/userid)
  - `UpdateSession`, `GetPlatformIds`, `Regions`
  - stubs `Storage`, `Notifications`, `Statistics`, `Analytics`
  - `Create` / `ReserveSpot` encore en stub
- `profiles/mock-milenet.json` : redirection `LiveBaseUrl=localhost:8443`
- `cli.py` : commande `mock`
- `tests/test_mock_backend.py` : 2 tests (crypto + serveur)
- `docs/MOCK-BACKEND.md`

Vérifications :

- `.\.venv\Scripts\python -m unittest discover -s tests` → **31 tests OK**
- `.\.venv\Scripts\python -m mgp19 mock --port 8443` → démarre
- `GET /services/v1/Security/PublicKey` → HTTP 200, PEM 272 o
- `python -m mgp19 apply mock-milenet` → diff correct, **aucune écriture**
- tests d'intégration : login chiffré → token/userid → `GetPlatformIds` OK

Aucun lancement du jeu, aucune écriture de config réelle.
Prochain morceau : 6B (Create/ReserveSpot + écoute UDP + test client).

### 2026-11-10 — Morceau 6B : sessions + écoute UDP

Ajouté :

- `Create` : fausse session GameLift avec `gameSessionId`, `fleetId`,
  `ipAddress` = IP locale, `port` = 7777, `maximumPlayerSessionCount`.
- `ReserveSpot` : PlayerSession avec `psess-<uuid>`, IP/port locaux,
  `playerData` contenant une clé AES-256 + nonce 12 o générés par le mock.
- `UdpProbe` : écoute `0.0.0.0:7777`, journalise les paquets dans
  `work/mock_udp.jsonl`, extrait les chaînes ASCII (décalages 0–7) et tente
  un déchiffrement AES-256-GCM si une clé est connue.
- CLI : `--game-ip`, `--game-port`, `--no-udp`, `--udp-log`.
- `docs/MOCK-BACKEND.md` mis à jour.

Vérifications :

- `.\.venv\Scripts\python -m unittest discover -s tests` → **32 tests OK**
- test d'intégration : login → `Create` → `ReserveSpot`
  - `gameSessionId` présent
  - `ipAddress=127.0.0.1`, `port=7777`
  - `playerData` : clé 32 o, nonce 12 o
- test UDP manuel : paquet `hello psess-test-1234` reçu et journalisé
  dans `work/mock_udp.jsonl`.

Aucun lancement du jeu, aucune écriture de config réelle.
Prochain morceau : 6C (test réel avec le client).

### 2026-11-10 — Morceau 6C : test réel du mock avec le client

Test :

- mock lancé sur `127.0.0.1:8443`, endpoint de jeu `192.168.0.11:7777`
- profil `mock-milenet` appliqué
- jeu lancé via Steam
- navigation : MULTIJOUEUR → COURSE PRIVÉE → CRÉER UN SALON

Résultats :

- `PublicKey`, `Login` (1324 o), `GetPlatformIds`, `Storage` : acceptés.
- `Regions` : accepté ; ~60 s de latence ICMP (6 régions × 10 s).
- `Create` (576 o) : **réponse acceptée**, le client enchaîne sur `ReserveSpot`.
- `ReserveSpot` (408 o) : **réponse acceptée**.
- Le client se connecte à `192.168.0.11:7777` et envoie des paquets UDP de
  25 o toutes les secondes (handshake UE4).
- Timeout : « Connexion à l'hôte interrompue » car le mock ne répond pas au
  handshake.

Conclusion :

- le control plane est maîtrisé ;
- le schéma `Create` reconstitué est accepté ;
- le client utilise bien notre IP/port et notre clé ;
- il manque la réponse au handshake UE4 (6D) et un vrai serveur (UE4SS).

Config restaurée après le test. Aucun processus ni port laissé ouvert.
Document : `docs/MOCK-TEST-RESULTS.md`.

### 2026-11-10 — Morceau 6D : réponse au handshake

Ajouté :

- `HANDSHAKE_CHALLENGE` / `HANDSHAKE_RESPONSE` (paire observée dans
  `race_session.pcap`).
- `UdpProbe` répond au paquet `01...04` par le challenge, puis à l'écho par
  la réponse, et journalise le paquet `hello` de 61 o.
- `Regions` ne renvoie qu'une région (`eu-central-1`) pour éviter 60 s de
  timeout ICMP.
- test unitaire `test_udp_handshake` : challenge → réponse → hello.

Test réel :

- `Create` (408 o) → `ReserveSpot` → handshake.
- Log :

```text
HANDSHAKE challenge_sent 192.168.0.11:61779
HANDSHAKE response_sent  192.168.0.11:61779
HANDSHAKE hello          192.168.0.11:61779
UDP 192.168.0.11:61779 psess-d23ba3c6-ad77-41b0-8a15-8704cd3583ee
```

- 22 paquets `hello` reçus, contenant `psess-...` (décalage de bits 3).
- Le client répète car le mock n'envoie pas de `NMT_Welcome`.

Conclusion :

- le client accepte notre handshake et nous transmet son `EncryptionToken` ;
- il manque la partie serveur de jeu (`NMT_Welcome`, réplication) ;
- prochaine étape : UE4SS ou un vrai serveur.

Config restaurée. Aucun processus ni port laissé ouvert.

### 2026-11-10 — UE4SS : installation et premier test

Installation :

- UE4SS **v3.0.1** (`Game__Shipping__Win64`), téléchargé depuis GitHub.
- Installé dans `motogp19/Binaries/Win64` : `dwmapi.dll`, `UE4SS.dll`,
  `UE4SS-settings.ini`, `Mods/`.
- Backup complet : `backups/ue4ss-20261110-202311/`
  (`Binaries-Win64.zip`, config, saves, appmanifest, README).
- Scripts : `tools/install_ue4ss.ps1`, `tools/uninstall_ue4ss.ps1`,
  `tools/launch_ue4ss.ps1`.

Problème rencontré :

- Les mods Lua échouaient à cause du `™` dans `MotoGP™19`
  (`luaL_loadfile ... Invalid argument`).
- Solution : jonction ASCII
  `F:\SteamLibrary\steamapps\common\MotoGP19` → `MotoGP™19`, puis lancement
  direct du Shipping depuis la jonction avec `steam_appid.txt=984780`.
- L'appmanifest Steam a été restauré à son état d'origine après le test.

Résultats :

- UE4SS se charge sur UE 4.21, signatures trouvées.
- Console GUI « UE4SS Debugging Tools » OK.
- Mods Lua chargés, dont `MGP19Dump`.
- `F8` : dump des classes OK.
  - `GameSession` = `IgnitionGameSession` (menu)
  - `GameOnlineSessionManager` = `GameOnlineSessionManagerBP_C`
  - `PlayerController` = `MenuPlayerControllerBP_C`
  - `GameMode` = `MenuGameModeBP_C`
  - `GameInstance` = `GameInstance_BP_C`
  - `GameLiftServer...`, `DedicatedServer...`, `GameSessionSettings` : 0 objet.
- `F9` : `open /Game/maps/lobby/lobby?listen?game=...LobbyGameModeBP...`
  exécuté (`tentative 4: ok`), mais :
  - le monde reste `/Game/maps/menu/menu` ;
  - écran de chargement avec spinner ;
  - **aucun port UDP 7777** ;
  - pas de `LobbyGameModeBP_C`.

Conclusion :

- UE4SS est opérationnel, mais `open` / `ServerTravel` ne suffisent pas :
  le jeu attend une session (`GameOnlineSessionManagerBP_C` /
  `IgnitionGameSession`) avant de voyager.
- Prochain axe : inspecter `GameOnlineSessionManagerBP_C` (fonctions
  `CreateSession`, `HostAlone`, etc.) et tester les CVars host-alone.

Document : `docs/UE4SS-INSTALL.md`.

### 2026-11-10 — Inspection du session manager

Généré un **CXX Header Dump** via UE4SS (Ctrl+H) dans
`Binaries/Win64/CXXHeaderDump/`. Headers utiles copiés dans
`work/ue4ss/CXXHeaderDump/`.

Fonctions identifiées :

- `UGameOnlineSessionManager` : `SetPlayInLan(bool)`,
  `CreateOnlineSession()`, `SetCreateSessionProperties(...)`,
  `StartMatchmaking()`, `GetDefaultCreateSettings(...)`,
  `IsHostAloneAllowed()`.
- `UMpCreateSessionFsmState` : `SetPublic(bool)`, `SetPassword(FString)`,
  `CreationConfiguration`, `LevelToOpen`, `GameModeToOpen`.
- `AGameSpecificGameSession::CreateSession()`.
- `UMpGameModeCommonComponent::CheckHostAlone()` / `IsHostAlone()`.
- `UCreateSessionCallbackProxyAdvanced::CreateAdvancedSession(..., bUseLAN, ...)`.

Tentatives :

- `SetPlayInLan(true)` → ok.
- `CreateOnlineSession()` → ok.
- `GetDefaultCreateSettings()` → erreur (paramètres out).
- Résultat : aucune session visible, aucun UDP 7777, monde = menu.

Interprétation :

- `CreateOnlineSession()` seul ne suffit pas ;
- il faut des propriétés de session valides ou passer par le FSM ;
- `SetPlayInLan` ne change pas forcément la stratégie
  `PlatformToDedicatedSessionStrategy` ;
- prochaine piste : `CreateAdvancedSession(bUseLAN=true)` ou remplacer
  `StrategyInstance` par `USingleSessionStrategy`.

Document : `docs/UE4SS-INSTALL.md`.

### 2026-11-10 — Plan de développement validé

Décisions :

- Phase A timeboxée à **4 soirées**.
- Focus sur la **Voie A** (serveur local UE4SS) ; Voie B en réserve.
- UE4SS sur compte principal, **Steam hors ligne**, pas de matchmaking
  officiel avec UE4SS.
- Launcher cible **GUI**, socle CLI d'abord.
- 2e PC fourni par le pote.
- Le pote n'a pas de résultats UE4SS supplémentaires.

Feuille de route complète : `docs/ROADMAP.md`.

Jalons :

```text
M1 UE4SS charge            ✅
M2 CXX dump                ✅
M3 session locale          en cours (timebox 4 soirées)
M4 UDP 7777
M5 2e client
M6 course
M7 launcher GUI
M8 12 joueurs
```

Prochain morceau : **7A — `CreateAdvancedSession(bUseLAN=true)`**.

### 2026-11-10 — 7A : CreateAdvancedSession(bUseLAN=true)

Test :

- `UCreateSessionCallbackProxyAdvanced` trouvé via
  `/Script/IgnitionNetwork.Default__CreateSessionCallbackProxyAdvanced`.
- Appel `CreateAdvancedSession(world, {}, pc, 12, 0, true, true, false,
  true, true, false, false, false, true)`.
- Un proxy est bien créé (`UObject: ...`).
- `OnSuccess` / `OnFailure` ne peuvent pas être bindés après l'activation
  (factory déjà activée).
- Résultat :
  - aucune session visible ;
  - **aucun UDP 7777** ;
  - monde = menu.

Test complémentaire avec le profil `direct-connect` (Null OSS) :

- même résultat pour F5 ;
- `F9` (`open ...?listen`) affiche le spinner de chargement ;
- le monde reste `/Game/maps/menu/menu` ;
- aucun UDP 7777.

Conclusion :

- le proxy est créé mais la session n'est pas créée/voyagée ;
- il manque probablement les propriétés de session ou le FSM
  `UMpCreateSessionFsmState` ;
- la navigation UI avec Null OSS n'a pas pu être validée dans ce test
  (problème de focus/clavier).

Prochain morceau : **A2** (`SetCreateSessionProperties` +
`CreateOnlineSession`) ou **A3** (`UMpCreateSessionFsmState`).

### 2026-11-10 — 7B / A2 : SetCreateSessionProperties + CreateOnlineSession

Test :

- appel de `GetDefaultCreateSettings()` sur
  `GameOnlineSessionManagerBP_C` ;
- résultat : `pcall` échoue (`ok=false`), la suite du script ne s'exécute
  pas (pas de #2/#3 dans le log) ;
- aucun `SetCreateSessionProperties` ni `CreateOnlineSession` exécuté ;
- **aucun UDP 7777**, jeu toujours au menu ;
- le processus reste vivant et répond.

Conclusion :

- l'appel direct de `GetDefaultCreateSettings` avec des paramètres out est
  trop fragile en Lua ;
- la construction manuelle de `TArray<FSessionPropertyKeyPair>` est
  difficile (struct opaque) ;
- piste suivante : **A3** (`UMpCreateSessionFsmState`) ou **l'UI avec
  Null OSS** (le FSM de l'UI fait le travail correctement).

Timebox Phase A : **2 soirées / 4** utilisées.

### 2026-11-10 — 7D : UI avec Null OSS → crash

Test :

- profil hybride `direct-connect-mock` :
  - `DefaultPlatformService=NULL`
  - `IpNetDriver`
  - `net.AllowEncryption=0`
  - `LiveBaseUrl=localhost:8443`
  - mock HTTP lancé (`--no-udp`)
- navigation UI :
  - MULTIJOUEUR → CRÉER UNE PARTIE → COURSE PRIVÉE
  - écran « CRÉATION DE SALON PRIVÉ » atteint.
- tentatives pour déclencher « CRÉER UN SALON » :
  - Espace, Retour arrière, X, Y, clic sur le footer ;
  - aucun appel `Regions` / `Create` dans le mock.

Résultat :

- **le jeu a crashé** après ~223 s, état `MenuGameState` ;
- `CrashContext.runtime-xml` : `CrashType=Crash`, pas de message,
  PCallStack natif sans symboles ;
- copie dans `work/crash-7d/CrashContext.runtime-xml`.

Interprétation :

- la création de session via **Null OSS** est instable / non supportée ;
- le session manager du client semble conçu pour le flux MileNet/GameLift ;
- le crash renforce l'hypothèse qu'un serveur local n'est pas un chemin
  supporté par ce binaire client.

Timebox Phase A : **3 soirées / 4** utilisées.
Il reste **1 soirée** avant le point de décision.

### 2026-11-10 — Phase A : échec, timebox épuisé (4/4)

Dernière tentative :

- profil hybride `direct-connect-mock` (Null OSS + mock HTTP) ;
- navigation UI jusqu'à l'écran de création de salon (public, le choix
  privé a été manqué) ;
- `F6` (`SetPlayInLan(true)` + `CreateOnlineSession()`) exécuté ;
- log : `SetPlayInLan(true) ok`, mais pas de `CreateOnlineSession() ok` ;
- `Entrée` sur « CONTINUER » → **le processus ne répond plus**
  (`Responding=False`), CPU bloqué ;
- aucun appel `Regions` / `Create` dans le mock ;
- **aucun UDP 7777**.

Conclusion :

- la création de session locale via Null OSS est **instable / non
  supportée** (crash précédent, freeze maintenant) ;
- le session manager du client est conçu pour MileNet/GameLift ;
- la Phase A est **échouée** après 4 soirées.

Décision recommandée :

1. **Arrêter la Phase A.**
2. Passer à la **Voie B** : backend officiel + correctif de latences.
3. Si l'indépendance est non négociable : plan B (autre jeu).

Aucun processus ni port laissé ouvert. Config restaurée.

### 2026-11-10 — Revue Voie A : alternatives

Constat clé : le spinner du `open` ressemble à un `ClientTravel` (le client
cherche un serveur inexistant). Pour un listen server, il faut un
`ServerTravel` / `OpenLevel` avec autorité.

Alternatives identifiées (doc `docs/VOIE-A-ALTERNATIVES.md`) :

1. `UGameplayStatics::OpenLevel(..., "listen")` — standard UE4.
2. `UWorld::ServerTravel(..., bAbsolute=true)` — évite le `Travel_RELATIVE`.
3. Charger `/Game/maps/server/idle?listen` (ServerDefaultMap).
4. `SetPlayInLan(true)` avant l'UI, pas après.
5. Lire `GetCreateSessionProperties(false)` à l'écran de création.
6. `StartMatchmaking(bUseLAN=true)` avec `FBPOnlineSessionSettings`.
7. `AGameSpecificGameSession::CreateSession()`.
8. Inspecter `UGameLiftServerGameSessionComponent`.
9. **Dépôt Steam « Dedicated Server »** — peut tout résoudre.
10. CLI `-server -game -ExecCmds`.
11. Serveur UE4 4.21 générique + paks.

Prochain test recommandé :

- A1 `OpenLevel` avec `listen` ;
- A2 `ServerTravel` avec `bAbsolute=true` ;
- A3 `server/idle?listen` ;
- en parallèle, vérifier le dépôt Steam serveur (A9).

Chaque test doit logguer `World.NetMode`, `World.NetDriver`, le monde chargé
et l'UDP 7777.

### 2026-11-10 — A1 `OpenLevel` : freeze

Test :

- profil `direct-connect` (Null OSS, IpNetDriver, encryption off) ;
- UE4SS chargé, jeu au menu principal ;
- appel `UGameplayStatics::OpenLevel(world, "/Game/maps/lobby/lobby",
  true, "listen?game=...LobbyGameModeBP...")`.

Résultat :

- log `A1 OpenLevel lobby listen` ;
- le jeu affiche le dialogue « services Milestone » puis un spinner ;
- **le processus ne répond plus** (`Responding=False`) ;
- aucun `A1 immediate` (NetMode/NetDriver) loggé ;
- **aucun UDP 7777**.

A2 (`ServerTravel` absolute) et A3 (`server/idle?listen`) n'ont pas pu être
testés : A1 a figé le jeu avant.

Conclusion :

- même l'appel engine `OpenLevel` fige le client ;
- le blocage n'est pas seulement le `ClientTravel` de la commande `open` ;
- la Voie A par le client est très probablement morte.

Dernière piste indépendante : **dépôt Steam « Dedicated Server »** (A9).
Sinon : Voie B ou plan B.

### 2026-11-10 — A9 : dépôt Steam serveur → inexistant

Vérifications :

- `steamcmd +login anonymous +app_info_print 984780` :
  - dépôt installé : `984781` (contenu du jeu, 18 Go) ;
  - dépôts partagés : `228986`, `228990` (Steamworks) ;
  - DLC : `1058300` ;
  - **aucun dépôt serveur / dedicated** ;
  - `privatebranches = 1` (branche privée non accessible).
- Recherche Steam Store « MotoGP19 Dedicated Server » :
  - seul le jeu apparaît, aucun outil serveur.

Conclusion :

- il n'existe pas de binaire serveur public séparé sur Steam ;
- la Voie A est **définitivement morte** pour ce client.

Décision :

1. **Voie B** : backend officiel + correctif de latences.
2. **Plan B** : autre jeu avec serveur dédié.

---

## 11. Rappels légaux / éthiques

- Interopérabilité uniquement, sur des jeux possédés par les joueurs.
- Pas de contournement du DRM Steam.
- Pas de distribution d'exécutable patché.
- Pas de fuzzing ni de sondage du backend Milestone de production.
- Pas de modification des paks du jeu.
