# Mock MileNet — faux backend local

## Périmètre du morceau 6A

Le mock implémente le **control plane** HTTP de MileNet :

- serveur HTTPS local sur `127.0.0.1:8443`
- certificat TLS auto-signé
- paire RSA-1024 pour le chiffrement des corps
- endpoints :
  - `GET /services/v1/Security/PublicKey`
  - `POST /services/v1/PlayerProfile/Steam/Login`
  - `POST /services/v1/PlayerProfile/UpdateSession`
  - `POST /services/v1/PlayerProfile/User/GetPlatformIds/`
  - `GET /services/v1/GameSessions/Regions/`
  - stubs `Storage`, `Notifications`, `Statistics`, `Analytics`
- déchiffrement des requêtes client :
  - `RSA-OAEP-SHA1` avec la clé privée du mock
  - `AES-128-CBC` avec la clé/IV contenus dans le blob RSA
- chiffrement des réponses :
  - avec la clé publique `EncryptionKey` envoyée par le client au login
  - même enveloppe RSA + AES
- login : renvoie `{"token": "<32 hex>", "userid": "<24 hex>"}`
- journalisation dans `work/mock_milenet.log`

Les endpoints `Create` et `ReserveSpot` sont encore des stubs : ils renvoient
`{}` et seront implémentés au morceau 6B.

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

Sortie attendue :

```text
Mock MileNet en écoute sur https://127.0.0.1:8443
Clé publique servie sur /services/v1/Security/PublicKey
Configure le client avec : [MileNetOnline] LiveBaseUrl=localhost:8443
Ctrl+C pour arrêter.
```

## Configuration du client

Appliquer le profil :

```powershell
python -m mgp19 apply mock-milenet --yes
```

Il écrit dans `Engine.ini` :

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

Puis restaurer après le test :

```powershell
python -m mgp19 restore Engine.ini --yes
```

## Test rapide du mock

Sans lancer le jeu :

```powershell
.\.venv\Scripts\python -c "import http.client, ssl; c=http.client.HTTPSConnection('127.0.0.1',8443,context=ssl._create_unverified_context()); c.request('GET','/services/v1/Security/PublicKey'); r=c.getresponse(); print(r.status, len(r.read()))"
```

Résultat attendu : `200 272` (PEM RSA-1024).

## Limites

- Le mock ne crée pas encore de session de jeu.
- `Create` / `ReserveSpot` renvoient `{}` : le client ne pourra pas encore
  rejoindre un serveur.
- Le serveur de jeu local n'existe toujours pas : il faudra UE4SS ou un
  binaire serveur.
- Le certificat est auto-signé ; le client ne le vérifie pas
  (`n.VerifyPeer=false`).

## Sécurité

- Le mock écoute uniquement en local par défaut.
- Il ne contacte pas le vrai MileNet.
- Les logs ne contiennent ni `EncryptionKey`, ni `AuthToken`, ni token complet.
- Les fichiers `mem_hits.txt`, `race_session.pcap` et `race_clear.jsonl`
  contiennent des identifiants de session : ne pas les publier.
