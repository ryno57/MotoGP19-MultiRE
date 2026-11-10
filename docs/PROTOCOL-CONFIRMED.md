# Protocole MotoGP 19 — éléments confirmés par les artefacts

Source : `flows.mitm`, `mem_hits.txt`, `race_session.pcap`, `mgp19_local.pcap`,
`mgp19_server.pcapng`, `ue4_decrypt.py`, fournis par le contact.

Les valeurs sensibles (psess, SteamID, clé AES, nonce, IDs de compte) sont
volontairement remplacées par des placeholders.

---

## 1. Ce qui a été vérifié

- `race_session.pcap` a été déchiffré avec la clé lue dans `mem_hits.txt`.
- Résultat : **3563 paquets déchiffrés sur 3572** (9 paquets de handshake/contrôle).
- Le client se connecte à un serveur GameLift officiel `<server-ip>:7777`.
- La session contient bien :
  - le login `?EncryptionToken=psess-...`
  - la map `/Game/maps/lobby/lobby`
  - le GameMode `/Game/assets/data/gamemodes/multiplayer/LobbyGameModeBP.LobbyGameModeBP_C`
  - la réplication UE4 classique (LobbyPlayerControllerBP, WeekendCompetitionBP, etc.)

- `mgp19_local.pcap` ne contient que du TCP loopback vers `127.0.0.1:8443`
  (le proxy mitmproxy), pas de serveur de jeu local.
- `mgp19_server.pcapng` contient du TCP de contrôle (AWS/Steam/DNS), pas de
  trafic UDP de jeu. Ce n'est pas une capture d'un serveur local.

---

## 2. HTTP MileNet

### 2.1 Hôte et redirection

- Hôte : `online-milestone2.eu-west-1.elasticbeanstalk.com`
- Redirection conseillée : `[MileNetOnline] LiveBaseUrl=localhost:8443`
  (plus propre qu'un fichier hosts).
- TLS non vérifié côté client (`n.VerifyPeer=false`).

### 2.2 En-têtes observés

Requêtes authentifiées :

```text
Host: online-milestone2.eu-west-1.elasticbeanstalk.com
Content-Type: application/json
ML_User-Agent: <MileNetAppId>
Env: Live
Authorization: <token 32 hex>
WWW-Authenticate: <16 octets base64, différent à chaque requête>
User-Agent: motogp19/++UE4+Release-4.21-CL-0 Windows/6.2.9200.1.0.64bit
Content-Length: <taille du corps chiffré>
```

- `Authorization` reste constant pendant la session.
- `WWW-Authenticate` change à chaque requête.
- L'algorithme du `WWW-Authenticate` reste inconnu. Il n'est **pas nécessaire**
  pour un faux backend : on peut l'ignorer ou renvoyer une valeur arbitraire.

### 2.3 Chiffrement

- `GET /services/v1/Security/PublicKey` renvoie une clé PEM RSA (bloc de 128 o).
- Requête : `base64( RSA-OAEP-SHA1(cléAES16 || IV16) + AES-128-CBC(JSON) )`.
- Le login contient la clé publique RSA du client dans `EncryptionKey`.
- Réponse : même enveloppe, chiffrée pour la `EncryptionKey` du client.
- Une réponse AES seule (sans enveloppe RSA) fait planter le client.
- Substituer `EncryptionKey` casse l'authentification **uniquement** pour un
  relais transparent vers le vrai serveur ; un faux backend n'est pas concerné.

### 2.4 Endpoints observés

```text
GET  /services/v1/Security/PublicKey
POST /services/v1/PlayerProfile/Steam/Login
POST /services/v1/PlayerProfile/UpdateSession
POST /services/v1/PlayerProfile/User/GetPlatformIds/
GET  /services/v1/GameSessions/Regions/
POST /services/v1/GameSessions/Create/
POST /services/v1/GameSessions/ReserveSpot/
GET  /services/v1/Storage/<appid>/Catalog/...
```

### 2.5 Requêtes de session

`Create` (corps déchiffré, d'après le contact) :

```json
{
  "Latencies": {"<region>": 30, "...": 300},
  "MaxPlayers": 12,
  "Alias": "MGP19-<pseudo>",
  "Properties": {"PlatformSessionId": "<id lobby Steam>"}
}
```

`ReserveSpot` :

```json
{"GameSessionId": "arn:aws:gamelift:<region>::gamesession/fleet-<uuid>/gsess-<...>"}
```

Tailles observées dans `flows.mitm` :

- `Create` requête : 472 o chiffrés ; réponse : 832 o.
- `ReserveSpot` requête : 384 o ; réponse : 1260 o.
- `Login` requête : 1324 o ; réponse : 300 o.

Le schéma exact de la réponse `Create` n'est pas encore connu.
La réponse `ReserveSpot` est connue (voir ci-dessous).

### 2.6 Réponse `ReserveSpot` (confirmée par `mem_hits.txt`)

Objet AWS GameLift en camelCase :

```json
{
  "playerSessionId": "psess-<uuid>",
  "playerId": "<userid>",
  "gameSessionId": "arn:aws:gamelift:<region>::gamesession/fleet-<uuid>/gsess-<...>",
  "fleetId": "fleet-<uuid>",
  "fleetArn": "arn:aws:gamelift:<account>:fleet/fleet-<uuid>",
  "creationTime": {"$date": <ms>},
  "status": "RESERVED",
  "ipAddress": "<server-ip>",
  "dnsName": "ec2-<...>.compute.amazonaws.com",
  "port": 7777,
  "playerData": "{\"EncryptionKey\":\"<base64 32 o>\",\"EncryptionNonce\":\"<base64 12 o>\",\"Environment\":\"Steam\",\"IsTrustedPlatform\":false,\"Platform\":\"Steam\",\"IsDevLocation\":false}"
}
```

`playerData` est une **chaîne JSON échappée**, pas un objet.
C'est de là que viennent la clé AES-256 et le nonce UDP.

---

## 3. Protocole UDP de jeu

### 3.1 Handshake

Séquence observée sur `race_session.pcap` :

1. Client : paquet de 25 o (`01 00 ... 04`).
2. Serveur : challenge aléatoire de 25 o.
3. Client : réponse de 25 o.
4. Serveur : réponse de 25 o.
5. Client : paquet de 61 o contenant `psess-...` à un décalage de 3 bits.
6. Échange de petits paquets de contrôle.
7. Ensuite : `NMT_Hello` avec `?EncryptionToken=psess-...`, puis données chiffrées.

### 3.2 Chiffrement des datagrammes

- Flux de bits UE4 LSB-first.
- 2 bits de tête, puis N octets, puis 1 bit de terminaison.
- N octets = `[nonce 12 o][tag GCM 16 o][données chiffrées]`.
- AES-256-GCM, sans AAD.
- Clé = `playerData.EncryptionKey`.
- Nonce de session = `playerData.EncryptionNonce` ; octets 4–7 aléatoires par
  paquet, octet 8 incrémenté.

### 3.3 Login client (observé en clair)

```text
/Game/maps/startup/startup?EncryptionToken=psess-<...>?Name=<pseudo>?NativeId=<steamid>?MLLobbyDLCs=0?PlayerSessionId=psess-<...>
```

Suivi de la chaîne `MILENET`.

### 3.4 Welcome serveur (observé)

```text
/Game/maps/lobby/lobby
/Game/assets/data/gamemodes/multiplayer/LobbyGameModeBP.LobbyGameModeBP_C
```

Classes vues ensuite :

```text
LobbyPlayerControllerBP_C
LobbyGameState
LobbyPlayerState
WeekendCompetitionBP_C
PlayerSelectionControllerComponent
RaceSelectionControllerComponent
MpPlayerControllerCommonComponent
CompetitionDataComponent
VotingComponent
TimerComponent
```

Le client envoie ensuite ses choix de salon : `Salon MotoGP`, `Mugello`,
`france`, `MotoGP_LCR-Honda-Castrol-2019`, `CUSTOM_RIDER`, etc.

---

## 4. Interprétation pour notre projet

### Ce que ça confirme

- Le client est un **pur client** : il se connecte à un serveur dédié GameLift.
- Le serveur est une machine AWS ; le client ne l'héberge pas.
- Le protocole HTTP et UDP est entièrement cartographié.
- La clé UDP est fournie par le backend dans `playerData`.
- Le serveur utilise `LobbyGameModeBP` et la map `/Game/maps/lobby/lobby`.

### Ce que ça ne résout pas

- **On n'a toujours pas de serveur local.** Le binaire client ne contient pas
  le SDK GameLift serveur et `-server` ne démarre rien.
- Pour héberger sur un PC, il faut forcer le client en **listen server**
  (UE4SS / console / `ServerTravel`) et lui fournir la clé/nonce.
- Le schéma exact de la réponse `Create` reste à capturer.
- L'algorithme `WWW-Authenticate` reste inconnu (mais inutile pour un mock).

### Pistes

1. **UE4SS** : console, export des classes, tentative de `ServerTravel` sur
   `/Game/maps/lobby/lobby` avec `LobbyGameModeBP`.
2. **Faux backend** : répondre au login, à `Create` et à `ReserveSpot` avec
   notre IP/port et notre clé. Nécessite un serveur local à cette adresse.
3. **Contournement officiel** : réécriture des latences + `LiveBaseUrl`
   vers un proxy, pour héberger via GameLift Milestone (dépend encore d'eux).

---

## 5. Artefacts et reproduction

- `work/race_clear.jsonl` : flux UDP déchiffré (hex, direction, temps).
- `work/flows.strings.txt` : chaînes extraites de `flows.mitm`
  (endpoints, en-têtes, tailles).
- `work/decrypt_race.py` : extraction de la clé depuis `mem_hits.txt` et
  déchiffrement du pcap.
- `work/inspect_pcaps.py` / `work/inspect_all.py` : inventaire des captures.

Attention : `mem_hits.txt` et `race_clear.jsonl` contiennent des identifiants
de session et des clés. Ne pas publier.
