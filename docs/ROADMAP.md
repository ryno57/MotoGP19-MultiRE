# Feuille de route — MotoGP 19 Community Host

Dernière mise à jour : 2026-11-10

---

## 0. Décisions validées

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
- **Le pote n'a pas de résultats UE4SS supplémentaires** : nous sommes
  en avance sur ce point.

---

## 1. Objectif

Une course de ligue hébergée sur le PC d'un joueur, avec les autres joueurs
qui se connectent à son IP, sans dépendre des serveurs Milestone.

### Critères de succès

1. Un client démarre un listen server local (UDP 7777).
2. Un deuxième client se connecte.
3. Une course peut démarrer et finir.
4. 4 joueurs stables.
5. 8 à 12 joueurs stables.
6. Aucune dépendance à MileNet.

### Non-objectifs

- Réécrire le netcode.
- Contourner le DRM Steam.
- Distribuer un exécutable patché.
- Maintenir un serveur GameLift Milestone.

---

## 2. État actuel

### Acquis

- Backend MileNet compris et mock fonctionnel :
  login, `Regions`, `Create`, `ReserveSpot`, handshake UE4, `psess`.
- UE4SS v3.0.1 fonctionnel sur UE 4.21 via jonction ASCII.
- Console UE4SS, mods Lua, dump de classes.
- CXX Header Dump disponible.
- Sauvegardes, scripts d'installation/désinstallation, documentation.

### Blocage

- Aucun serveur de jeu local n'est encore créé.
- `open`, `ServerTravel`, `SetPlayInLan(true)` + `CreateOnlineSession()`
  ne suffisent pas.
- Le client reste au menu / écran de chargement, sans UDP 7777.

---

## 3. Phase A — Création d'une session locale

**Timebox : 4 soirées à partir de maintenant.**  
L'installation UE4SS et le CXX Header Dump sont déjà faits.

### Expériences, dans l'ordre

#### A1. `CreateAdvancedSession(..., bUseLAN=true)`

- via `UCreateSessionCallbackProxyAdvanced` ;
- `PublicConnections = 12`
- `PrivateConnections = 0`
- `bIsDedicatedServer = false`
- `bUseLAN = true`
- `bAllowInvites = true`

**Succès :** session créée, monde qui voyage, UDP 7777 ouvert.

#### A2. `SetCreateSessionProperties` + `CreateOnlineSession`

- construire un `TArray<FSessionPropertyKeyPair>` minimal ;
- `SetCreateSessionProperties(properties, 12, false)` ;
- `CreateOnlineSession()`.

#### A3. `UMpCreateSessionFsmState`

- trouver/instancier le state ;
- `SetPublic(false)` ;
- configurer `LevelToOpen` / `GameModeToOpen` ;
- déclencher la création.

#### A4. Remplacer `StrategyInstance`

- inspecter `StrategyInstance` ;
- essayer `USingleSessionStrategy` au lieu de
  `PlatformToDedicatedSessionStrategy`.

#### A5. Inspection des propriétés

Via UE4SS (Live View ou Lua) :

- `bPlayInLan`
- `CurrentState`
- `StrategyInstance`
- `CreateSessionProperties`
- `MaxPlayers`
- `SessionShouldAdvertice`
- `bCreatePublicSession`

### Jalon M3 — session locale créée

- **Oui** → Phase B.
- **Non après 4 soirées** → arrêt de la Phase A, réévaluation.

---

## 4. Phase B — Connexion d'un deuxième client

### B1. Vérifier le port

```powershell
Get-NetUDPEndpoint -LocalPort 7777
```

### B2. Pointer le mock vers le host

`ReserveSpot` renvoie :

- IP du host,
- port 7777,
- clé AES-256 + nonce.

### B3. Gérer le chiffrement

1. `net.AllowEncryption=0` pour un premier test.
2. Injection de clé via UE4SS (`AESHandlerComponent` / `NetConnection`).
3. Clé partagée entre le mock et le serveur local.

### B4. Test 2 PC

- host : lance le serveur local ;
- client : `join <ip>` via le mock ;
- vérifier le `NMT_Hello` / `psess`.

### Jalons

- **M4** — UDP 7777 ouvert.
- **M5** — un 2e client voit le host.
- **M6** — une course démarre.

### Si M4/M5 échoue

- vérifier la clé AES ;
- vérifier `IpNetDriver` vs `SteamNetDriver` ;
- vérifier le NAT / pare-feu ;
- tester en LAN d'abord.

---

## 5. Phase C — Launcher

### Socle CLI

- `host` : profil mock, mock, UE4SS, attente du port, infos de connexion.
- `join <ip>` : profil, lancement, connexion.
- `stop` : ferme le jeu, arrête le mock, restaure la config.
- diagnostic réseau / pare-feu / logs.

### GUI

Cible : une fenêtre simple et visible.

- état du jeu / UE4SS / mock / port 7777 ;
- boutons **Héberger**, **Rejoindre**, **Arrêter**, **Restaurer** ;
- champs IP, port, circuit, nombre de joueurs ;
- panneau de logs ;
- bouton « copier les infos de connexion » pour le Discord.

Techno : Tkinter/ttk (stdlib) dans un premier temps, `customtkinter` si on
veut plus joli.

### Jalon M7 — launcher GUI v1

---

## 6. Phase D — Durcissement ligue

- tests 4, 8, 12 joueurs ;
- plusieurs circuits ;
- météo / usure / pénalités ;
- reconnexion après déco ;
- race director ;
- documentation d'onboarding ;
- gestion des versions / backups.

### Jalon M8 — 12 joueurs stables

---

## 7. Phase E — Indépendance / repli

### Si la Voie A marche

- suppression de MileNet ;
- mock backend local ;
- serveur browser / lobby ;
- documentation complète.

### Si la Voie A échoue

1. **Voie B** : backend officiel + correctif de latences.
2. **Plan B** : autre jeu avec serveur dédié.

---

## 8. Arbre de décision

```text
M1 UE4SS charge ?           → OUI (fait)
M2 CXX dump disponible ?    → OUI (fait)
M3 session locale créée ?   → en cours (timebox 4 soirées)
   ├── OUI → M4 UDP 7777
   │        ├── OUI → M5 2e client
   │        │        ├── OUI → M6 course
   │        │        │        ├── OUI → M7 GUI → M8 ligue
   │        │        │        └── NON → GameMode / FSM
   │        │        └── NON → clé AES / NAT / netdriver
   │        └── NON → FSM / stratégie
   └── NON après 4 soirées → Voie B / plan B
```

---

## 9. Ce qu'on ne refait pas

- `-server`
- map en argument
- `GameDefaultMap` + `LocalMapOptions`
- `open` / `ServerTravel` seuls
- `SetPlayInLan(true)` + `CreateOnlineSession()` seuls
- attente d'un serveur dédié dans le binaire client

Ces pistes sont documentées comme impasses.

---

## 10. Organisation du travail

- petits/moyens morceaux ;
- arrêt après chaque morceau ;
- mise à jour de `SUIVI.md` + résumé dans la conversation ;
- backups avant modification ;
- tests unitaires Python ;
- logs/captures pour UE4SS ;
- aucun commit de ma part ;
- aucun secret publié.

---

## 11. Risques

| Risque | Parade |
|---|---|
| VAC / ban | Steam hors ligne, pas de matchmaking officiel, compte secondaire si possible |
| Crash UE4SS | backups, `--disable-ue4ss` |
| Aucun serveur local | timebox 4 soirées → Voie B / plan B |
| Chiffrement AES | `net.AllowEncryption=0` ou injection de clé |
| NAT / port 7777 | pare-feu, UPnP, test LAN |
| Compatibilité 4.21 | garder UE4SS v3.0.1 qui fonctionne |
| Temps | jalons courts, pas de dev avant validation |

---

## 12. Prochain morceau

**7A — `CreateAdvancedSession(bUseLAN=true)`**

Créer une session LAN via `UCreateSessionCallbackProxyAdvanced`, vérifier :

- le voyage vers le lobby ;
- l'ouverture d'UDP 7777 ;
- les logs UE4SS.

Si ça marche → Phase B.  
Si ça échoue → A2 (`SetCreateSessionProperties` + `CreateOnlineSession`).
