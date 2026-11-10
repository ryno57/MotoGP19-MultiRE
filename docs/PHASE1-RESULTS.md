# Phase 1 — Résultats du premier test réel

Date : 2026-11-10 19:09–19:12
Machine : `Monke` (192.168.0.11)
Session : `sessions/20261110-190919-host`

## Objectif

Vérifier si un lancement `host` du launcher permet d'obtenir un serveur local
écoutant sur le port 7777, avec la map Mugello en `?listen`.

## Commande utilisée

```powershell
python -m mgp19 host --yes
```

Profil appliqué : `direct-connect`
(DefaultPlatformService=NULL, IpNetDriver, net.AllowEncryption=0, CVars online).

Commande Steam réelle :

```text
"C:\Program Files (x86)\Steam\steam.exe" -applaunch 984780 /Game/maps/Tracks/mugello/mugello?listen -port=7777 -nosteam -log
```

## Déroulé observé

1. Le jeu démarre normalement (bootstrap + Shipping).
2. Écran d'avertissement sauvegarde automatique.
3. Écran « Appuyer sur une touche ».
4. Dialog « Un nouveau correctif est disponible. Effectuez la mise à jour
   pour continuer à jouer. »
5. Après validation : « Vous ne pouvez pas accéder aux services de Milestone.
   Certains contenus ne seront pas disponibles. » (Réessayer / Annuler)
6. Après « Annuler » : écran de chargement avec spinner.
7. Le jeu finit par quitter.
8. Le launcher restaure la config et clôt la session.

## Constats

- Les arguments sont bien transmis par Steam (visibles dans la ligne de commande
  du processus).
- **La map passée en argument n'a pas lancé de serveur** : aucun socket UDP 7777
  n'est apparu pendant la session.
- Le jeu semble ignorer l'argument de map et passer par son flux de démarrage
  normal (startup → menu / vérifications online).
- Le profil `direct-connect` provoque les dialogues « services Milestone
  inaccessibles », car le sous-système Null n'a pas accès à MileNet.
- Aucun log fichier n'est produit par le build shipping.
- Le launcher a correctement :
  - appliqué le profil,
  - lancé le jeu via Steam,
  - attendu la fin,
  - restauré `Engine.ini`,
  - collecté les métadonnées de session.

## Conclusion

Le chemin « map en argument + Null OSS » ne suffit pas.
Il faut d'abord obtenir un serveur local par une autre voie :

1. Lancer en **vanilla** pour atteindre le menu principal.
2. Ouvrir la console (`~` ou `F1`) et tester :
   ```text
   open /Game/maps/Tracks/mugello/mugello?listen
   ```
3. Vérifier l'apparition du port 7777.
4. Si la console est inaccessible, il faudra l'activer via la config ou
   utiliser une autre méthode (autoexec / mock MileNet).

Si le listen server fonctionne en console mais pas en argument, on adaptera le
launcher pour exécuter la commande au bon moment.

Si aucun serveur local n'est possible sans MileNet, on passe au mock backend.

## Artefacts

- `sessions/20261110-190919-host/session.json`
- `Engine.before.ini` / `Engine.after.ini`
- `net.before.json` / `net.after.json`
- Captures : `work/host-screen*.png`, `work/host-after-*.png`
- Log du launcher : `work/test-host.log`
