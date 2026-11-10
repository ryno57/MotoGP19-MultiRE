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

## 2. État actuel

**Phase : premier test réel effectué (morceau 5). Serveur local non obtenu.**

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
`Create` et `ReserveSpot` acceptés ; le client se connecte à notre IP/port et
envoie le handshake UE4, puis timeout car le mock ne répond pas au handshake.
Le **control plane est maîtrisé**. Il reste à implémenter la réponse au
handshake (6D) et à forcer un serveur local (UE4SS).

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
  - `mock_backend.py` — faux backend MileNet local (HTTPS + RSA/AES + Create/ReserveSpot + UDP probe)
  - `cli.py` — commandes `doctor`, `profiles`, `apply`, `restore`, `status`, `net`, `firewall`, `host`, `join`, `sessions`, `mock`
  - `__main__.py` — `python -m mgp19 ...`
- `profiles/vanilla.json` — aucune modification
- `profiles/direct-connect.json` — override Null OSS + IpNetDriver + CVars
- `profiles/mock-milenet.json` — redirection MileNet vers `localhost:8443`
- `tests/test_config.py` — 9 tests unitaires
- `tests/test_network.py` — 12 tests unitaires
- `tests/test_launcher.py` — 8 tests unitaires
- `tests/test_mock_backend.py` — 3 tests unitaires (crypto + serveur + session)
- `docs/README.md` — structure et commandes
- `docs/MOCK-BACKEND.md` — utilisation du faux backend
- `docs/MOCK-TEST-RESULTS.md` — résultats du test réel 6C
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

---

## 11. Rappels légaux / éthiques

- Interopérabilité uniquement, sur des jeux possédés par les joueurs.
- Pas de contournement du DRM Steam.
- Pas de distribution d'exécutable patché.
- Pas de fuzzing ni de sondage du backend Milestone de production.
- Pas de modification des paks du jeu.
