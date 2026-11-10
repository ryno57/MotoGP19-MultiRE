# Mock MileNet — faux backend local

## Périmètre (morceaux 6A + 6B)

Le mock implémente :

- serveur HTTPS local sur `127.0.0.1:8443`
- certificat TLS auto-signé
- paire RSA-1024 pour les corps
- endpoints :
  - `GET /services/v1/Security/PublicKey`
  - `POST /services/v1/PlayerProfile/Steam/Login`
  - `POST /services/v1/PlayerProfile/UpdateSession`
  - `POST /services/v1/PlayerProfile/User/GetPlatformIds/`
  - `GET /services/v1/GameSessions/Regions/`
  - `POST /services/v1/GameSessions/Create/`
  - `POST /services/v1/GameSessions/ReserveSpot/`
  - stubs `Storage`, `Notifications`, `Statistics`, `Analytics`
- déchiffrement/chiffrement RSA-OAEP-SHA1 + AES-128-CBC
- `Create` renvoie une fausse session GameLift avec **notre IP/port**
- `ReserveSpot` renvoie un PlayerSession avec **notre IP/port** et une
  **clé AES-256 + nonce** générés par le mock
- écoute UDP du port de jeu pour voir le client arriver
- journalisation dans `work/mock_milenet.log` et `work/mock_udp.jsonl`

## Installation

Le mock est le seul module qui dépend de `cryptography`.
Le reste du projet reste sans dépendance externe.

```powershell
cd F:\MotoGP19-MultiRE
python -m venv .venv
.\.venv\Scripts\pip install cryptography
```

## Lancement

```powershell
.\.venv\Scripts\python -m mgp19 mock --port 8443
```

Options utiles :

```powershell
--game-ip 192.168.0.11     # IP renvoyée au client (défaut : IP locale)
--game-port 7777           # port UDP renvoyé (défaut : 7777)
--no-udp                   # ne pas écouter le port UDP
--udp-log work/mock_udp.jsonl
--log work/mock_milenet.log
```

Sortie attendue :

```text
Mock MileNet en écoute sur https://127.0.0.1:8443
Clé publique servie sur /services/v1/Security/PublicKey
Endpoint de jeu renvoyé : 192.168.0.11:7777
Configure le client avec : [MileNetOnline] LiveBaseUrl=localhost:8443
Écoute UDP sur 0.0.0.0:7777 (log: .../work/mock_udp.jsonl)
Ctrl+C pour arrêter.
```

## Configuration du client

```powershell
python -m mgp19 apply mock-milenet --yes
```

Écrit dans `Engine.ini` :

```ini
[MileNetOnline]
LiveBaseUrl=localhost:8443
ProductionBaseUrl=localhost:8443

[MileNet]
ShippingServer=localhost:8443
MileNetServer=localhost:8443

[OnlineSubsystem]
DefaultPlatformService=MILENET
NativePlatformService=STEAM
bHasVoiceEnabled=false
```

Restaurer après le test :

```powershell
python -m mgp19 restore Engine.ini --yes
```

## Ce que renvoie le mock

### `Create`

```json
{
  "gameSessionId": "arn:aws:gamelift:eu-central-1::gamesession/fleet-<uuid>/gsess-<hex>",
  "fleetId": "fleet-<uuid>",
  "fleetArn": "arn:aws:gamelift:eu-central-1:000000000000:fleet/fleet-<uuid>",
  "creationTime": {"$date": 1794336711000},
  "status": "ACTIVE",
  "ipAddress": "192.168.0.11",
  "port": 7777,
  "currentPlayerSessionCount": 0,
  "maximumPlayerSessionCount": 12,
  "gameProperties": [],
  "playerSessionCreationPolicy": "ACCEPT_ALL"
}
```

### `ReserveSpot`

```json
{
  "playerSessionId": "psess-<uuid>",
  "playerId": "<userid>",
  "gameSessionId": "<arn renvoyé par Create>",
  "fleetId": "fleet-<uuid>",
  "fleetArn": "arn:aws:gamelift:eu-central-1:000000000000:fleet/fleet-<uuid>",
  "creationTime": {"$date": 1794336711000},
  "status": "RESERVED",
  "ipAddress": "192.168.0.11",
  "port": 7777,
  "playerData": "{\"EncryptionKey\":\"<base64 32 o>\",\"EncryptionNonce\":\"<base64 12 o>\",\"Environment\":\"Steam\",\"IsTrustedPlatform\":false,\"Platform\":\"Steam\",\"IsDevLocation\":false}"
}
```

## Écoute UDP

`UdpProbe` écoute `0.0.0.0:<game-port>` et écrit chaque paquet dans
`work/mock_udp.jsonl` :

```json
{"time": ..., "src": "192.168.0.11:54321", "len": 61,
 "hex": "...", "strings": ["psess-...", "..."]}
```

Il extrait les chaînes ASCII pour tous les décalages de bits 0–7, ce qui
permet de voir le `NMT_Hello` / `?EncryptionToken=psess-...` même décalé.
Si une clé AES de session est connue, il tente aussi un déchiffrement
AES-256-GCM et ajoute `decrypted_strings`.

## Handshake UE4

Le mock répond au handshake observé dans `race_session.pcap` :

- challenge : `bdfd35ff3cdbd4e48e749656b47ecf4133eaf6ff5a7e6b5804`
- réponse : `030000fe3edbd4e48e749656b47ecf4133eaf6ff5a7e6b5804`

Le client renvoie ensuite un paquet de 61 o contenant `psess-...`.
Le mock le journalise (`HANDSHAKE hello`) et extrait le `psess`.

Il ne va pas plus loin : pas de `NMT_Welcome`, pas de réplication.
Le client répète donc le `hello` puis timeout.

`Regions` ne renvoie qu'une seule région (`eu-central-1`) pour éviter
6 × 10 s de timeout ICMP pendant les tests.

## Test réel avec le client

1. Fermer le jeu.
2. Lancer le mock :
   ```powershell
   .\.venv\Scripts\python -m mgp19 mock --port 8443
   ```
3. Appliquer le profil :
   ```powershell
   python -m mgp19 apply mock-milenet --yes
   ```
4. Lancer le jeu normalement (Steam).
5. Aller dans **MULTIJOUEUR** et créer un salon privé.
6. Observer :
   - `work/mock_milenet.log` : login, `Create`, `ReserveSpot`
   - `work/mock_udp.jsonl` : paquets du client vers notre port
7. Restaurer :
   ```powershell
   python -m mgp19 restore Engine.ini --yes
   ```

## Limites

- **Il n'y a pas encore de serveur de jeu local.** Le client va se connecter
  à notre port UDP puis timeout : c'est attendu.
- Le schéma exact de la réponse `Create` est une reconstitution. Si le client
  la refuse, on ajustera les champs.
- `FindSessions` / `FindSessionById` ne sont pas encore implémentés.
- Le certificat est auto-signé ; le client ne le vérifie pas.

## Sécurité

- Le mock écoute en local par défaut.
- Il ne contacte pas le vrai MileNet.
- Les logs ne contiennent pas `EncryptionKey`, `AuthToken`, ni token complet.
- Les fichiers `mem_hits.txt`, `race_session.pcap` et `race_clear.jsonl`
  contiennent des identifiants de session : ne pas les publier.
