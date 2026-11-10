# Documentation du projet

## Structure

```
mgp19/
  paths.py      détection Steam / installation / chemins utilisateur
  config.py     lecture-écriture des .ini UE4, profils, sauvegardes
  network.py    IP locale/publique, endpoints, ports UDP, pare-feu
  launcher.py   lancement Steam, modes host/join, sessions
  mock_backend.py  faux backend MileNet local (HTTPS + crypto)
  cli.py        interface en ligne de commande
  __main__.py   point d'entrée `python -m mgp19`
profiles/
  vanilla.json
  direct-connect.json
tests/
docs/
SUIVI.md        journal de bord du projet
```

## Commandes

Depuis la racine du projet :

```powershell
python -m mgp19 doctor
python -m mgp19 profiles
python -m mgp19 apply direct-connect            # aperçu (diff)
python -m mgp19 apply direct-connect --yes      # écrit réellement
python -m mgp19 status
python -m mgp19 restore Engine.ini --yes

python -m mgp19 net                             # diagnostic réseau
python -m mgp19 net --public                    # + IP publique
python -m mgp19 firewall                        # aperçu règle pare-feu
python -m mgp19 firewall --range                # aperçu plage 7777-8077
python -m mgp19 firewall --yes                  # ajout réel (admin)

python -m mgp19 host                            # aperçu hébergement
python -m mgp19 host --track losail --port 7777
python -m mgp19 host --yes                      # lance réellement
python -m mgp19 join 192.168.0.42               # aperçu connexion
python -m mgp19 join 192.168.0.42 --yes         # lance réellement
python -m mgp19 sessions                        # historique des sessions

# Faux backend MileNet (nécessite .venv + cryptography)
.\.venv\Scripts\python -m mgp19 mock --port 8443
python -m mgp19 apply mock-milenet --yes
python -m mgp19 restore Engine.ini --yes
```

## Sessions

Chaque lancement réel crée un dossier dans `sessions/<horodatage>-<mode>/` :

- `session.json` — état, args, notes
- `Engine.before.ini` / `Engine.after.ini`
- `net.before.json` / `net.after.json`
- `steam-command.txt`
- `logs/`, `crashes/`, `crash-report/` si disponibles

La config est restaurée automatiquement à la fin. Si le launcher est interrompu,
la session reste marquée `active` et sera restaurée au prochain lancement.

## Sécurité

- Le launcher ne modifie que
  `%LOCALAPPDATA%\motogp19\Saved\Config\WindowsNoEditor\`.
- Avant la première écriture, le fichier d'origine est copié dans
  `_mgp19_backups/<fichier>.original.mgp19bak`.
- Chaque application crée aussi un snapshot horodaté.
- `restore` remet le fichier d'origine.
- Aucun accès aux paks ni aux exécutables.
- Si le jeu tourne, l'écriture est refusée.

## Profils

- `vanilla` : aucune modification.
- `direct-connect` : force le sous-système Null, `IpNetDriver`,
  désactive le chiffrement réseau et active les CVars de test online.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## UE4SS

L'installation UE4SS, la jonction ASCII et les tests sont documentés dans
`docs/UE4SS-INSTALL.md`.

## Feuille de route

Le plan de développement validé, les phases et les jalons sont dans
`docs/ROADMAP.md`.
