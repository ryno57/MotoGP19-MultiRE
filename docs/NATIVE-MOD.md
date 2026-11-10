# Mod C++ natif MGP19NativeMod

Date : 2026-11-10

## But

Contourner le blocage de `UGameplayStatics::OpenLevel` en Lua en l'appelant
**nativement** depuis un mod C++ UE4SS.

Le mod :

1. retrouve `GameplayStatics`, `World` et la `UFunction OpenLevel` via
   `StaticFindObject_InternalSlow` ;
2. lit les offsets réels des paramètres de la `UFunction` ;
3. construit le buffer de paramètres ;
4. appelle `ProcessEvent(OpenLevel)` avec `listen?game=...`.

## Prérequis

- UE4SS v3.0.1 installé dans `motogp19/Binaries/Win64`.
- Visual Studio BuildTools avec MSVC x64.
- CMake (celui de Visual Studio fonctionne).

## 1. Générer `UE4SS.lib`

`UE4SS.dll` exporte l'API C++. On génère une lib d'importation depuis ses
exports :

```powershell
dumpbin /exports UE4SS.dll > ue4ss-exports.txt
# générer UE4SS.def avec les noms exportés, puis :
lib /def:UE4SS.def /machine:x64 /out:UE4SS.lib
```

La lib générée est dans `work/ue4ss-import/UE4SS.lib`.

## 2. Compiler le mod

```powershell
cmake -S work/native-mod -B work/native-mod/build -G "Visual Studio 18 2026" -A x64
cmake --build work/native-mod/build --config Release
```

Sortie : `work/native-mod/build/Release/main.dll`.

## 3. Installer

```text
Mods/
  MGP19NativeMod/
    dlls/
      main.dll
```

Ajouter dans `Mods/mods.txt`, au-dessus de `Keybinds` :

```text
MGP19NativeMod : 1
```

## 4. Déclencher

Le mod attend le fichier :

```text
F:\MotoGP19-MultiRE\work\native-trigger.txt
```

Créer ce fichier quand le jeu est au menu :

```powershell
Set-Content F:\MotoGP19-MultiRE\work\native-trigger.txt "go"
```

Le mod appelle alors `OpenLevel` sur Mugello avec `listen`.

## Résultat obtenu

- `ProcessEvent(OpenLevel)` **retourne sans bloquer** ;
- le hook Lua voit bien :
  `Options=listen?game=...RaceGameMode_BP_C` ;
- **UDP 27015 s'ouvre** ;
- puis le jeu crashe en `EXCEPTION_ACCESS_VIOLATION` à `0x358`.

## Crash

- `RIP = base + 0x5a1f4b`
- instruction : `mov r14, qword ptr [rsi + 0x358]`
- `RSI = 0`
- pile :
  `+0x5a1f4b`, `+0x5a8b91`, `+0x5a3739`, `+0x1d09030`, ...

C'est un appel de fonction membre avec un objet nul. Le crash est identique
en `direct-connect` et en `mock-milenet` : il est dans l'initialisation du
listen server, pas dans l'OSS.

## Test au planning du week-end

Un test a été refait en déclenchant `OpenLevel(listen)` **après être entré
dans le flux Grand Prix / planning du week-end Mugello**, donc avec une
compétition active.

Résultat : **même crash**, même adresse.

La pile montre :

```text
[GameState + 0x3A0] = ReplicatedCompetition
        ↓
appel virtuel [vtable + 0x640] → retourne NULL
        ↓
fonction +0x5a1f10 appelée avec arg2 = NULL
        ↓
mov r14, [rsi + 0x358]  → crash
```

L'objet nul n'est donc pas la compétition elle-même, mais un objet de
session/réseau retourné par une méthode virtuelle de la compétition.

## Diagnostic vtable (sans crash)

Un mode diagnostic du mod C++ lit les pointeurs sans déclencher de voyage :

```text
GameState              = MenuGameState_0
ReplicatedCompetition  = non nul
[vtable + 0x640]       = thunk vers [vtable + 0x638] = RVA 0x53A1B0
```

La fonction `0x53A1B0` fait une recherche indexée :

```text
+0x370 = tableau  (lu : 0)
+0x378 = taille   (lue : 0)
+0x380 = index    (lu : -1)
```

Elle retourne `0` quand la table est vide, ce qui provoque le crash de
l'appelant.

Conclusion : la compétition `ReplicatedCompetition` n'est **pas initialisée**
au moment de `OpenLevel`. Le listen server n'est pas le problème direct ;
c'est l'état de la compétition.

## Pistes suivantes

1. Appeler `StartLevel` ou `SetupDefaultCompetition` sur la compétition
   avant `OpenLevel`.
2. Ou remplir les champs de la compétition (`Level`, `GameMode`, tableau de
   compétiteurs) avant l'appel.
3. Si la compétition est initialisée, retester `OpenLevel(listen)` et vérifier
   que le crash disparaît.
4. Si le serveur tient, tester un deuxième client sur le port 27015.
