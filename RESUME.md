# RESUME.md — Fonds d'Entraide

> **Document de reprise.** À lire en premier au début d'une session : état de
> l'application, architecture, commandes de vérification, pièges connus et
> prochaines étapes. La documentation de l'ancienne version Python est archivée
> dans `docs/historique/`.

## 1. Le projet en une phrase

Registre des cotisations d'un fonds d'entraide familial (7 clans, 46 grandes
familles, 46 lignées, 391 familles, 599 membres), devenu une application de
bureau Windows en Rust / Tauri 2, alimentée à l'origine par un classeur Excel
de 54 feuilles.

## 2. État au 11 novembre 2026

- **Portage terminé** : métier dans `core/`, coquille Tauri dans `src-tauri/`,
  interface dans `ui/`. L'ancienne application Python (Tkinter) a été retirée
  du dépôt ; son code reste dans l'historique Git, ses documents dans
  `docs/historique/`.
- **Fonctionnalités livrées** : navigation hiérarchique, encaissement avec
  ventilation sur plusieurs années, reçu imprimable, arriérés par exercice,
  fiche et édition des membres, tarif mensuel, exports CSV, sauvegardes,
  restauration vérifiée, purge en deux clics, mode démonstration, aide intégrée
  (guide + aide-mémoire A4) et installeur NSIS.
- **Audit de sécurité passé**, trois correctifs appliqués : SQLite corrigé via
  `libsqlite3-sys` 0.39.1, neutralisation des formules dans les exports CSV,
  Content-Security-Policy à la place de `csp: null`. Détail dans la section
  « Sécurité » du README.
- **Risques résiduels assumés** : installeur non signé (SmartScreen) et données
  non chiffrées au repos, protégées par la session Windows.
- Branche `main` propre et synchronisée avec `origin`.

## 3. Architecture

| Chemin | Rôle |
|---|---|
| `core/` | Cœur métier et accès SQLite, testé par `cargo test -p fonds-core` |
| `src-tauri/` | Coquille Tauri 2 : commandes, ouverture de la base, configuration |
| `ui/` | Interface HTML/CSS/JS embarquée, sans bundler ni réseau |
| `schema_v2.sql` | Schéma SQLite v2, embarqué dans le binaire |
| `scripts/docs.mjs` | Génère `ui/aide/guide.html` depuis `GUIDE_UTILISATEUR.md` |
| `tests/ui/fumee.mjs` | Test de fumée de l'interface avec un faux DOM |
| `GUIDE_UTILISATEUR.md` | Mode d'emploi du caissier (source du guide intégré) |
| `docs/historique/` | Documents de la version Python et de la migration |

Points structurants :

- `core/` interdit `unsafe` (`#![forbid(unsafe_code)]`) et n'a aucune dépendance
  à Tauri. `rusqlite` 0.41.1 embarque SQLite (feature `bundled`).
- `schema_v2.sql` est la seule source du schéma ; `core/src/demo.rs` l'embarque
  par `include_str!`. **Ne pas le déplacer** sans corriger ce chemin.
- Une seule fenêtre Tauri (`main`), permissions réduites à `core:default`,
  `withGlobalTauri: true` (l'interface utilise `window.__TAURI__`), CSP définie
  dans `src-tauri/tauri.conf.json`.
- `ui/aide/guide.html` est **généré** : modifier `GUIDE_UTILISATEUR.md`, puis
  lancer `node scripts/docs.mjs`. Ne jamais l'éditer à la main.
- L'aide s'affiche dans une `iframe srcdoc` alimentée par la commande
  `lire_aide` ; les deux documents sont compilés dans le binaire.

## 4. Lancer et localiser les données

```
cargo run -p fonds-app
cargo run -p fonds-app -- --demo
```

Ordre de recherche de la base : variable `FONDS_DB`, puis `cotisations_v2.db`
à côté de l'exécutable, puis la racine du projet. Sauvegardes dans
`sauvegardes/`, exports dans `exports/`, à côté de la base ouverte. En
démonstration, tout se passe dans `%TEMP%\fonds-entraide-demo.db`.

Les données nominatives ne sont **jamais** versionnées : `*.db`, `*.db-wal`,
`*.db-shm`, `*.xlsx`, `sauvegardes/` et `exports/` sont dans `.gitignore`.

## 5. Vérifier avant de livrer

```
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p fonds-core          # 40 tests : 5 unitaires, 21 acceptation,
                                  # 1 démo, 8 hiérarchie, 5 purge
cargo test -p fonds-app           # 1 test : documents d'aide embarqués
node tests/ui/fumee.mjs           # 110 appels Tauri simulés
cargo build -p fonds-app
```

La chaîne complète dépasse cinq minutes : la lancer en tâche de fond avec un
journal et un marqueur `FINI`, puis surveiller le fichier, plutôt qu'en une
seule commande synchrone qui peut être coupée.

## 6. Installeur Windows

```
npm i --no-save --prefix target/tauri-cli/wrapper @tauri-apps/cli@2
node target/tauri-cli/wrapper/node_modules/@tauri-apps/cli/tauri.js build
```

Le build release prend une dizaine de minutes. Avec NSIS 3.13, le script généré
échoue sur `NSISCOMCALL` : dans `target/release/nsis/x64/utils.nsh`, faire
passer `"${shortcut}"` par `$R9` **avant chaque** `${IPersistFile::Load}`
(`STGM_READ` **et** `STGM_READWRITE`) et `${IPersistFile::Save}`, puis relancer
`%LOCALAPPDATA%\tauri\NSIS\makensis.exe` sur `installer.nsi` et copier
`nsis-output.exe` vers `target/release/bundle/nsis/`. Ce dossier est régénéré à
chaque build : le correctif est à refaire à chaque fois.

Test d'installation sans toucher au poste :

```
powershell -NoProfile -Command "Start-Process -FilePath '<installeur>' -ArgumentList '/S','/D=C:\Temp\fonds-test-install' -Wait"
```

Git Bash avale le chemin `/D=` : passer par PowerShell. Vérifier que le
SHA-256 de `fonds-app.exe` installé est celui de `target/release/fonds-app.exe`,
puis désinstaller en silence.

## 7. Sécurité — fait et à confirmer

Fait : `rusqlite` 0.41.1 / `libsqlite3-sys` 0.39.1 (RUSTSEC-2026-0459),
neutralisation des formules CSV (`=`, `+`, `@`, `-` suivi d'une expression),
CSP restrictive. Reste à confirmer à l'écran, car aucun test statique ne couvre
la CSP : ouvrir **Aide**, vérifier que le guide s'affiche et que **Imprimer**
fonctionne, puis enregistrer un versement.

## 8. Règles métier et conventions à ne pas casser

- Les totaux se calculent **depuis `affectations`**, jamais depuis
  `paiements.campagne_id` : un versement peut couvrir plusieurs années.
- Suppression, purge, restauration et annulation se font en **deux clics** dans
  l'interface, sans `confirm()` système.
- Une restauration vérifie l'intégrité et le schéma de la copie **avant**
  d'écrire, et prend une copie de sécurité au préalable.
- La purge est transactionnelle ; exercices et tarifs sont conservés, les
  numéros de reçus déjà utilisés ne sont jamais réattribués.
- Toute valeur venant de l'interface passe par des paramètres SQL liés ; les
  seuls noms de tables interpolés viennent de listes fermées.
- Les structures échangées avec le JavaScript sont en `camelCase`
  (`serde(rename_all = "camelCase")`).
- `chrono` est sans la feature `clock` : les dates passent par SQLite ou par des
  `NaiveDate` explicites.

## 9. Pièges connus

- Le build échoue si `fonds-app.exe` tourne : fermer l'application d'abord.
- `target/release/nsis/x64/` est régénéré à chaque build (voir §6).
- Le faux DOM de `tests/ui/fumee.mjs` ne gère ni `classList.toggle`, ni
  `document.addEventListener`, ni `setAttribute` ; comparer les tableaux issus
  du contexte `vm` avec `Array.from(...)`.
- La CSP conserve `'unsafe-inline'` pour les scripts et les styles : les pages
  d'aide embarquent un bouton d'impression en `onclick` et des styles internes.
- `ui/aide/guide.html` et `schema_v2.sql` sont compilés dans le binaire : les
  déplacer casse le build.

## 10. Prochaines étapes

1. Confirmer à l'écran l'aide, l'impression et un encaissement après la CSP.
2. Signer l'installeur si l'application est diffusée par téléchargement
   (procédure et limites dans le README, section « Signature numérique »).
3. Chiffrer la base au repos seulement si une exigence le demande : cela impose
   une gestion de mot de passe et de récupération.
4. Éventuellement, un index court dans `docs/historique/`.

## 11. Dépôt

- `origin` : https://github.com/yyracine/FondEntraide_Rust.git, branche `main`.
- Derniers commits : `920f1cb` archive des documents Python, `f76debf` section
  sécurité du README, `aad505e` retrait de l'application Python, `dc2339d`
  correctifs de sécurité, `8f824e8` aide intégrée.
- Aucun fichier de données nominatives n'a jamais été commité.
