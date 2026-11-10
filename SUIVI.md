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

**Phase : reconnaissance terminée + socle launcher + diagnostics réseau (morceaux 2 et 3).**

Le jeu démarre hors ligne jusqu'au menu principal.
Le lancement en `-server` ne produit pas encore de socket d'écoute sur 7777.
Le build shipping n'écrit pas de log fichier exploitable.
La console en jeu n'a pas encore été testée manuellement.

Le socle `mgp19/` est en place : détection Steam, profils de config,
sauvegarde/restauration, diagnostic réseau et pare-feu.
Aucun profil n'a encore été appliqué pour de vrai.

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
  - `cli.py` — commandes `doctor`, `profiles`, `apply`, `restore`, `status`, `net`, `firewall`
  - `__main__.py` — `python -m mgp19 ...`
- `profiles/vanilla.json` — aucune modification
- `profiles/direct-connect.json` — override Null OSS + IpNetDriver + CVars
- `tests/test_config.py` — 9 tests unitaires
- `tests/test_network.py` — 12 tests unitaires
- `docs/README.md` — structure et commandes
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

### Morceau suivant (4)

`launcher.py` :
- lancement du jeu via Steam avec arguments
- mode `host` / `join`
- application / restauration automatique du profil
- collecte des logs de session

Puis seulement : tests réels host/join.

---

## 8. Inconnues à trancher

| Inconnue | Méthode | Statut |
|---|---|---|
| Code serveur fonctionnel dans le binaire | test `-server` / map | à trancher |
| Listen server possible | console `open ...?listen` | à trancher |
| Connexion client directe | test 2 PC | à trancher |
| Course démarrable sans MileNet | observation FSM | à trancher |
| Format exact des réponses de session | mitmproxy / HAR | à trancher |
| Chiffrement RSA/AES rejouable | endpoint PublicKey | à trancher |
| SteamNetDriver vs IpNetDriver | override config | à trancher |

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

---

## 11. Rappels légaux / éthiques

- Interopérabilité uniquement, sur des jeux possédés par les joueurs.
- Pas de contournement du DRM Steam.
- Pas de distribution d'exécutable patché.
- Pas de fuzzing ni de sondage du backend Milestone de production.
- Pas de modification des paks du jeu.
