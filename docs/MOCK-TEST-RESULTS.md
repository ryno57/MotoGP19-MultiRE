# Test réel du mock MileNet — résultats (morceau 6C)

Date : 2026-11-10, 19:54–20:02
Machine : `Monke` (192.168.0.11)
Mock : `.venv\Scripts\python -m mgp19 mock --port 8443 --game-ip 192.168.0.11 --game-port 7777`
Client : MotoGP 19 lancé via Steam, profil `mock-milenet`.

---

## Chronologie observée

| Heure | Événement |
|---|---|
| 19:54:36 | Mock démarré, `GET /Security/PublicKey` |
| 19:54:53 | `GET /Security/PublicKey` (client) |
| 19:55:38 | `POST /PlayerProfile/Steam/Login` (1324 o) → **login accepté** |
| 19:55:38 | `GetPlatformIds`, `Storage/Catalog/FilesHeader` → réponses acceptées |
| 19:56–20:00 | `UpdateSession` toutes les 60 s |
| 20:00:35 | `GET /GameSessions/Regions/` (après « Créer un salon ») |
| 20:01:35 | `POST /GameSessions/Create/` (576 o) → **réponse acceptée** |
| 20:01:35 | `POST /GameSessions/ReserveSpot/` (408 o) → **réponse acceptée** |
| 20:01:38+ | Paquets UDP de 25 o vers `192.168.0.11:7777`, toutes les 1 s |
| 20:02 | Dialogue « Connexion à l'hôte interrompue. Le délai d'attente a été dépassé. » |

---

## Ce qui fonctionne

- Le client utilise bien le mock (`LiveBaseUrl=localhost:8443`).
- Le chiffrement HTTP est correct :
  - le client envoie un corps de 1324 o,
  - le mock le déchiffre (RSA-OAEP-SHA1 + AES-128-CBC),
  - le client accepte la réponse chiffrée pour sa `EncryptionKey`.
- Le login renvoie un token/userid acceptés.
- `GetPlatformIds` et `Storage` avec des réponses vides sont acceptés.
- `Regions` avec une liste de régions est accepté.
- `Create` avec notre schéma reconstitué est accepté : le client enchaîne
  immédiatement sur `ReserveSpot`.
- `ReserveSpot` avec notre IP/port et notre clé AES est accepté.
- Le client **se connecte réellement à `192.168.0.11:7777`** et envoie les
  paquets de handshake UE4 de 25 octets.
- Il n'y a eu **aucun dialogue « services Milestone inaccessibles »**.
- La configuration a été restaurée après le test.

---

## Ce qui bloque

Le mock n'implémente pas encore la **réponse au handshake UE4**.
Le client envoie :

```text
01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 04
```

toutes les secondes, sans réponse du serveur, puis abandonne avec un timeout.

C'est **attendu** : le mock n'est pas un serveur de jeu.

---

## Délai de 60 secondes

Le client a mis ~60 s entre `Regions` et `Create` :

- 6 régions × 10 s de timeout ICMP vers `ec2.<region>.amazonaws.com`.
- Nos régions ne répondent pas à l'ICMP → 99999 ms.
- Le client finit par appeler `Create` quand même.

Pour accélérer les prochains tests : ne renvoyer qu'une seule région
(`eu-central-1`) dans `Regions`, ou ajouter une option `--region`.

---

## Conclusion

Le **control plane est maîtrisé** :

```text
Login → GetPlatformIds → Regions → Create → ReserveSpot → connexion UDP
```

Le client accepte nos réponses et tente de se connecter à l'adresse que nous
lui donnons. Il ne manque que :

1. une réponse au handshake UE4 (pour voir le `NMT_Hello` et le
   `?EncryptionToken=psess-...`) ;
2. un vrai serveur de jeu derrière l'UDP (UE4SS ou binaire serveur).

---

## Artefacts

- `work/mock_6c.out` — log du mock pendant le test
- `work/mock_udp.jsonl` — paquets UDP reçus (25 o, handshake)
- `work/6c-screen*.png` — captures du client
- `work/mock_milenet.log` — log HTTP détaillé

Les valeurs de session (psess, token, clé AES) sont éphémères et ne sont pas
reproduites ici.
