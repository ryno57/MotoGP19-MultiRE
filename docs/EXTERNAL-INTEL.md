# Informations externes — analyse et recoupement

Source : message d'un développeur travaillant sous Linux/Proton, + `scan_mem.py`
et `mitm_addon.py`. Ces infos sont crédibles mais non reproduites par nous.
Ce document sépare ce qui est confirmé, cohérent, à vérifier ou hypothétique.

> **Mise à jour** : les artefacts fournis ensuite (`flows.mitm`, `mem_hits.txt`,
> `race_session.pcap`, `mgp19_local.pcap`, `mgp19_server.pcapng`,
> `ue4_decrypt.py`) confirment la majeure partie de ce document.
> Voir `docs/PROTOCOL-CONFIRMED.md` pour le protocole vérifié.

---

## 1. Tableau de confiance

| Affirmation | Statut | Commentaire |
|---|---|---|
| Backend `online-milestone2.eu-west-1.elasticbeanstalk.com` | **Confirmé par nous** | Présent dans `DefaultEngine.ini` extrait du pak. |
| TLS non vérifié (`n.VerifyPeer=false`) | **Confirmé par nous** | Déjà dans la config du jeu. |
| Redirection via `[MileNetOnline] LiveBaseUrl=` | **Très cohérent** | La clé existe dans notre `DefaultEngine.ini`. Plus propre qu'un fichier hosts. |
| `GET /services/v1/Security/PublicKey` en clair, PEM RSA | **Cohérent** | Chaîne présente dans le binaire ; endpoint dans le manifest. |
| Requête = `base64(RSA-OAEP-SHA1(cléAES16+IV16) + AES-128-CBC(JSON))` | **À vérifier** | Très spécifique, cohérent avec le code de l'addon. Non reproduit chez nous. |
| Réponse = même enveloppe, chiffrée pour la `EncryptionKey` du client | **À vérifier** | Explique le crash si on renvoie de l'AES seul. |
| Login renvoie `{"token": 32 hex, "userid": 24 hex}` | **À vérifier** | Plausible. |
| En-têtes `Authorization` + `WWW-Authenticate` calculé par le client | **À vérifier** | Algorithme inconnu. |
| Substituer `EncryptionKey` → 401 sur les requêtes suivantes | **Plausible** | Important seulement pour un relais transparent, pas pour un faux backend. |
| `Create` : `Latencies`, `MaxPlayers`, `Alias`, `Properties.PlatformSessionId` | **Cohérent** | Correspond aux noms de champs vus dans le binaire. |
| `ReserveSpot` renvoie un PlayerSession GameLift camelCase | **Très cohérent** | `PlayerSessionId`, `playerData`, `IpAddress`, `Port` sont dans nos strings. |
| `playerData` contient `EncryptionKey` (32 o) + `EncryptionNonce` (12 o) | **Très cohérent** | `AESGCM`, `EncryptionToken`, `NMT_Hello` sont dans le binaire. |
| UDP = AES-256-GCM, nonce 12 o, tag 16 o, sans AAD | **Cohérent** | `AESGCM` présent ; format UE4 plausible. |
| `NMT_Hello` contient `?EncryptionToken=psess-...` en clair | **Cohérent** | Le binaire décrit explicitement ce mécanisme. |
| Le client ne peut pas démarrer en `-server` | **Confirmé par notre test** | Aucun port 7777, démarrage client classique. |
| La map passée en argument est ignorée | **Confirmé par notre test** | Le jeu affiche le menu, pas la map. |
| Les réponses HTTP sont chiffrées et non lisibles dans les logs | **Confirmé par nous** | Pas de log fichier exploitable. |
| Aucun import/chaîne `InitSDK`, `ProcessReady`, `StartGameSession`, `AcceptPlayerSession`, `FleetId` | **Confirmé par nos strings** | Ces symboles sont absents. `GameLiftServerSDK` n'existe que comme nom de module. |
| Le code GameLift serveur est probablement désactivé à la compilation | **Hypothèse forte** | Cohérent avec l'absence des symboles du SDK. |
| `GameDefaultMap=lobby` + `LocalMapOptions=?listen...` → chargement infini | **À vérifier** | Non testé chez nous ; cohérent avec l'attente d'une session. |
| Aucun travail public existant | **Cohérent** | Nos recherches vont dans le même sens. |

---

## 2. Ce que ça change vraiment

### 2.1 Le binaire client n'est probablement pas un serveur dédié

C'est la correction la plus importante par rapport à notre hypothèse initiale.

- On avait vu `UGameLiftServerGameSessionComponent`, `UDedicatedServerGameSessionComponent`,
  `GameLiftServerSDK` et les maps serveur.
- Mais les fonctions réelles du SDK GameLift (`InitSDK`, `ProcessReady`,
  `StartGameSession`, `AcceptPlayerSession`, `FleetId`) sont **absentes**.
- Le composant serveur existe donc surtout comme coquille / code désactivé.
- `-server` ne fait pas démarrer un serveur : il lance un client normal.
- La map en argument est ignorée.

Conclusion : **le serveur dédié n'est pas dans l'installation**. Il était
probablement compilé séparément pour AWS GameLift.

### 2.2 Le vrai chemin restant : forcer un listen server côté client

Si on veut héberger sur nos PC, il faut réussir à faire démarrer le client
comme serveur d'écoute, avec la bonne map et le bon GameMode.

Deux voies :

1. **UE4SS** (console + appels de fonctions + inspection des classes)
   - ouvrir la console,
   - appeler `open` / `ServerTravel` avec la bonne URL,
   - inspecter `UGameLiftServerGameSessionComponent`,
     `UDedicatedServerGameSessionComponent`, `UGameSessionSettings`,
   - éventuellement injecter la clé AES/nonce de session.
   - Risque : UE4SS supporte 4.21 à la limite basse ; signatures manuelles possibles.

2. **Faux backend MileNet**
   - servir notre clé publique,
   - répondre au login,
   - répondre à `Create` et `ReserveSpot` avec notre IP/port et notre clé,
   - mais il faut **un serveur** à cette IP/port.
   - Donc le faux backend ne suffit pas seul : il doit être combiné avec un
     listen server forcé côté client.

### 2.3 Le contournement officiel existe déjà

Le correctif de latences de l'addon permet d'héberger **via le backend
officiel** en forçant une région proche :

- `Create` passe de 40–50 s à ~4 s ;
- l'hébergement fonctionne via GameLift Milestone.

C'est une solution de secours utilisable tout de suite, mais elle ne règle pas
l'indépendance : si Milestone coupe, elle tombe.

### 2.4 Le protocole est maintenant connu

- HTTP : RSA-OAEP-SHA1 + AES-128-CBC, endpoints, login, sessions.
- UDP : AES-256-GCM, clé/nonce dans `playerData`, `NMT_Hello` avec
  `?EncryptionToken=psess-...`.
- On sait donc décrypter le trafic, vérifier une connexion et comprendre
  pourquoi un client refuse de se connecter.

C'est énorme pour le débogage, même si on ne peut pas encore héberger.

---

## 3. Ce qu'il faut demander au contact

Priorité haute :

1. `ue4_decrypt.py` + un petit pcap de session.
2. `mem_hits.txt` avec la réponse de `Create` (schéma exact), même partiellement caviardé.
3. La configuration exacte utilisée pour `[MileNetOnline]` (`LiveBaseUrl`, etc.).
4. Le résultat de ses tests UE4SS, s'il en a.
5. La réponse de `FindSessions` / le flux pour rejoindre une partie publique.

Priorité moyenne :

6. Le `Create` response complet (832 o base64 → JSON).
7. Les en-têtes exacts `Authorization` / `WWW-Authenticate`.
8. Le détail du `playerData` et du `psess`.

---

## 4. Ce que nous devons faire côté Windows

Nos outils doivent être adaptés :

- `scan_mem.py` lit `/proc` : **Linux/Proton uniquement**. Il faut une version
  Windows avec `ReadProcessMemory` / `VirtualQueryEx`.
- `mitm_addon.py` est portable (mitmproxy + cryptography), mais il faut :
  - générer `mgp_priv.pem` / `mgp_pub.pem`,
  - installer `cryptography`,
  - configurer `LiveBaseUrl=localhost:8443` dans `Engine.ini`,
  - lancer mitmproxy en mode reverse.
- Le correctif de latences est portable tel quel.

---

## 5. Recommandation

### Court terme

1. Reproduire le contournement officiel (latence + `LiveBaseUrl`) sur Windows,
   pour donner à la ligue une méthode d'hébergement qui marche **maintenant**.
2. Documenter clairement que ça dépend encore de Milestone.

### Moyen terme

3. Tester UE4SS sur 4.21 :
   - console,
   - export des classes,
   - tentative de `open ...?listen` / `ServerTravel`.
4. Si le listen server démarre : construire le faux backend pour pointer les
   clients vers le host.
5. Si UE4SS échoue : envisager Ghidra, ou accepter le plan B.

### Long terme

- Si le serveur dédié n'est pas récupérable, l'indépendance totale est
  probablement hors de portée sans réécrire le netcode.
- Le contournement officiel reste la solution pragmatique pour la ligue.

---

## 6. Points d'attention

- Les infos viennent d'un prompt IA : certaines formulations peuvent être
  interprétées ou approximatives. Les éléments techniques précis (RSA-1024,
  AES-128-CBC, AES-256-GCM, `playerData`) sont cohérents avec le binaire et
  les scripts fournis, donc crédibles.
- Le `401` après substitution de `EncryptionKey` n'est **pas** un obstacle pour
  un faux backend : on ne relaie pas vers le vrai serveur, on répond nous-mêmes.
- Le crash VCRUNTIME sur une réponse AES seule indique qu'il faut respecter
  l'enveloppe RSA.
- L'algorithme `WWW-Authenticate` n'est nécessaire que pour **envoyer** des
  requêtes authentifiées au vrai serveur, pas pour **répondre** au client.
- La clé AES UDP est générée par le backend et transmise dans `playerData`.
  Pour un serveur local, il faudra la fournir au serveur ou désactiver le
  chiffrement.
