# Cotisations – Fonds d'entraide 

> **Reprise de session : lire `RESUME.md` en premier.** Il contient l'état
> d'avancement, les règles métier, les décisions prises et la prochaine
> étape. Ce fichier-ci décrit la construction de la base depuis l'Excel.

Application de bureau (Rust / Tauri 2) pour le registre des cotisations
familiales, alimentée à l'origine par
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
| `core/` | Cœur métier (SQLite, schéma v2), testé par `cargo test -p fonds-core` |
| `src-tauri/` | Coquille Tauri 2, commandes et configuration de l'installeur |
| `ui/` | Interface embarquée (HTML, CSS, JS), sans dépendance réseau |
| `schema_v2.sql` | Schéma SQLite v2, embarqué dans le binaire |
| `GUIDE_UTILISATEUR.md` | Mode d'emploi du caissier |
| `README.md` | Ce document |

L'ancienne application Python (import Excel, interface Tkinter) a été retirée
du dépôt ; l'historique Git la conserve.

## Règles d'import d'origine

Ces règles décrivent l'import initial du classeur ; les scripts Python qui
l'exécutaient ne font plus partie du dépôt.

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
sauvegarder, restaurer, purger. L'application y donne accès par le bouton
**Aide** : la fiche et le guide s'affichent dans l'application, avec leur propre
bouton d'impression.

Les deux documents sont compilés dans le binaire : la feuille est lue depuis
`aide-memoire.html`, le guide depuis `ui/aide/guide.html`, généré à partir du
Markdown. Après une modification du guide, relancer :

```
node scripts/docs.mjs
```

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

### Signature numérique et SmartScreen

Un installeur non signé déclenche « Windows a protégé votre PC » :
l'utilisateur doit ouvrir « Informations complémentaires » puis « Exécuter quand
même », et une stratégie d'entreprise peut l'en empêcher. C'est l'état actuel de
`Fonds d'Entraide_0.1.0_x64-setup.exe`.

**Ce qui ne marche plus.** Depuis 2024, un certificat EV ne supprime plus
l'avertissement au premier téléchargement. Microsoft documente qu'un fichier
signé OV, EV ou via Artifact Signing affiche le même message d'éditeur non
reconnu tant que la réputation n'est pas établie, et que cette réputation est
liée à l'empreinte du fichier : chaque nouvelle version repart de zéro. Un
certificat auto-signé se comporte exactement comme une absence de signature.

| Option | Coût | Effet SmartScreen | Remarque |
|---|---|---|---|
| Azure Artifact Signing (ex-Trusted Signing) | ~10 $/mois | Avertissement au début, réputation qui monte avec une identité constante | Recommandé hors Store, pas de jeton matériel |
| Certificat OV (DigiCert, Sectigo…) | 150–300 $/an | Identique | Certificat sur jeton ou HSM depuis juin 2023 |
| Certificat EV | 400 $+/an | Aucun avantage depuis 2024 | Inutile de payer pour SmartScreen |
| Microsoft Store | compte développeur | Aucun avertissement, Microsoft re-signe | Contraintes de publication |
| Auto-signé | gratuit | Identique à non signé | Tests internes uniquement |

Avec un certificat OV déjà présent dans le magasin Windows, Tauri signe
nativement l'application et l'installeur :

```json
"bundle": {
  "windows": {
    "certificateThumbprint": "A1B1A2B2A3B3A4B4A5B5A6B6A7B7A8B8A9B9A0B0",
    "digestAlgorithm": "sha256",
    "timestampUrl": "http://timestamp.digicert.com"
  }
}
```

Avec Artifact Signing, c'est `signCommand` qui appelle le CLI Azure (`%1` reçoit
le fichier à signer) :

```json
"bundle": {
  "windows": {
    "signCommand": "artifact-signing-cli -e https://wus2.codesigning.azure.net -a <compte> -c <profil> -d \"Fonds d'Entraide\" %1"
  }
}
```

Vérification après signature :

```
Get-AuthenticodeSignature "Fonds d'Entraide_0.1.0_x64-setup.exe" |
  Format-List Status, SignerCertificate
```

`Status` doit être `Valid`, avec le nom de l'éditeur dans le certificat.
Désactiver SmartScreen chez l'utilisateur, cocher « Débloquer » dans les
propriétés du fichier ou signer avec un certificat auto-signé ne change rien à
l'avertissement : seule la réputation du fichier et de l'éditeur, ou une
distribution par le Microsoft Store, le font disparaître.

Pour ce projet, l'installeur se transmet de la main à la main (clé USB, dépôt
local) : la signature n'apporte rien tant que le fichier ne circule pas par
téléchargement, et un avertissement expliqué vaut mieux qu'un certificat payé
non rentabilisé. Si la diffusion passe un jour par un site, Artifact Signing est
la voie la moins chère, en acceptant les avertissements des premières versions.


