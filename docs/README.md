# Documentation du projet

## Structure

```
mgp19/
  paths.py      détection Steam / installation / chemins utilisateur
  config.py     lecture-écriture des .ini UE4, profils, sauvegardes
  network.py    IP locale/publique, endpoints, ports UDP, pare-feu
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
```

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
