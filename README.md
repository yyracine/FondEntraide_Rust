# Cotisations – Fonds d'entraide 

> **Reprise de session : lire `RESUME.md` en premier.** Il contient l'état
> d'avancement, les règles métier, les décisions prises et la prochaine
> étape. Ce fichier-ci décrit la construction de la base depuis l'Excel.

Base SQLite des cotisations familiales, construite depuis
`FONDS D'ENTRE AIDE Final MAJ 3 Aout 24 (1).xlsx` (54 feuilles, 1,26 Mo).

## Hiérarchie

```
Clan              <- cellule A1, préfixe "Famille"/"LIGNEE" retiré      (7)
 └ Grande famille <- nom de la feuille                                  (46)
    └ Lignée       <- cellule A3 ou A4 ("Descendants  XXX")             (46)
       └ Famille   <- 1re personne nommée après chaque ligne TOTAL     (391)
          └ Membre <- chaque ligne portant un vrai nom                 (599)
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `schema.sql` | Schéma SQLite (tables, contraintes, index, vues) |
| `import_complet.py` | Import des 46 feuilles du classeur vers `cotisations.db` |
| `requetes.py` | CLI de consultation / rapports |
| `extrait_repertoires.py` | Extrait les 7 feuilles-répertoires vers `repertoires.json` |
| `repertoires.json` | Totaux des feuilles `LIGNEE xxx` (référence d'audit) |
| `cotisations.db` | Base générée |
| `README.md` | Ce document |

## Règles d'import

Motif d'une feuille de cotisation :
- lignes 1-4 : titres et en-tête des mois
  - `D..O` = Janv→Déc **2024** (Total en `P`)
  - `Q..AB` = Janv→Déc **2025** (Total en `AC`)
  - `AD..AO` = Janv→Déc **2026** (Total en `AP`)
- ligne 5+ : l'arbre. La **colonne remplie** donne le niveau (A=1, B=2, C=3).

Règles de nettoyage :
1. `(Penfant 21)` / `(APenfant211)` **sans nom** → ignorés (ne sont pas des membres).
2. Marqueur `(Enfant4)` retiré du nom ; le numéro va dans `ordre_fratrie`.
3. Placeholders `XXXX`, `YYYYY`, `ZZZZZ`, `AMY` → ignorés.
4. 7 feuilles sans grille de mois (listes de noms de lignées) → ignorées 

## Modèle de données

- **`membres`** : `nom`, `prenom`, `telephone`, `ordre_fratrie`, `parent_id`
  (parent direct), `famille_id`, `statut` (actif/inactif/decede/parti/suspendu).
- **`campagnes`** : une par année, `montant_mensuel` = 1 000 FCFA.
- **`paiements`** : un versement réel (`date_paiement`, `montant_total`, `mode`).
- **`affectations`** : détail mois par mois d'un paiement `(annee, mois, montant)`.

> ⚠️ **Un paiement peut couvrir plusieurs années.** Les totaux se calculent
> donc **toujours depuis `affectations`**, jamais depuis `paiements.campagne_id`.

## Application Rust / Tauri

Le portage vit dans `core/` (métier, testé par `cargo test`), `src-tauri/`
(coquille Tauri 2) et `ui/` (interface embarquée). Le schéma est celui de
`schema_v2.sql` ; les bases et les sauvegardes restent locales.

Le mode d'emploi pas à pas du caissier est dans
[`GUIDE_UTILISATEUR.md`](GUIDE_UTILISATEUR.md) : encaisser, imprimer un reçu,
sauvegarder, restaurer, purger.

### Mode démonstration

```
cargo run -p fonds-app -- --demo
```

Ouvre une base **fictive**, recréée à chaque lancement dans le dossier
temporaire (`fonds-entraide-demo.db`) : 2 clans, 5 familles, 15 membres, deux
campagnes et cinq versements passés par la même ventilation que la vraie base.
La base réelle n'est jamais ouverte, et l'interface affiche un bandeau « Base de
démonstration ». Le contrôle automatique de cette base :
`cargo test -p fonds-core --test demo`.

### Installeur Windows

`src-tauri/tauri.conf.json` est prêt pour NSIS (installation par utilisateur,
interface en français, icône `src-tauri/icons/icon.ico`). Le CLI Tauri
s'installe sans compilation, avec le paquet npm officiel :

```
npm i --no-save --prefix target/tauri-cli/wrapper @tauri-apps/cli@2
node target/tauri-cli/wrapper/node_modules/@tauri-apps/cli/tauri.js build
```

L'installeur sort dans `target/release/bundle/nsis/`
(`Fonds d'Entraide_0.1.0_x64-setup.exe`). `cargo install tauri-cli --locked`
puis `cargo tauri build` donnent le même résultat, en compilant tout le CLI.

Avec NSIS 3.13, le script généré s'arrête sur `NSISCOMCALL` (paramètres séparés
par des virgules à l'intérieur d'un macro). Le contournement est de passer
`"${shortcut}"` par `$R9` avant les appels `IPersistFile::Load` et
`IPersistFile::Save` de `target/release/nsis/x64/utils.nsh`, puis de relancer
`makensis` sur `installer.nsi` : ce dossier est régénéré à chaque build.

Pour vérifier un installeur sans toucher à l'installation réelle, installez-le
en silence dans un dossier temporaire, puis désinstallez-le :

```
"Fonds d'Entraide_0.1.0_x64-setup.exe" /S /D=C:\Temp\fonds-test-install
"C:\Temp\fonds-test-install\uninstall.exe" /S
```

Le `fonds-app.exe` installé doit avoir le même SHA-256 que
`target/release/fonds-app.exe`. NSIS se recopie dans `%TEMP%` et rend la main
avant d'avoir fini : laissez quelques secondes avant de constater la
disparition des raccourcis et de la clé de registre.


