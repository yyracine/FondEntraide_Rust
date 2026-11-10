# PLAN DE MIGRATION — Python / Tkinter → Rust / Tauri

> **Objet** : porter l'application « Fonds d'Entraide » (9 402 lignes de
> Python, Tkinter + SQLite) vers une application Rust à interface moderne,
> sans perdre une ligne de l'historique (599 membres, 1 807 000 FCFA).
>
> **Documents liés** : `PROBLEMES.md` (les 22 défauts à ne pas recopier),
> `schema_v2.sql` (le schéma cible, exécutable).
>
> **Principe directeur** : la réécriture est une **occasion de trancher les
> règles métier**, pas de traduire du Python en Rust. Chaque décision ci-dessous
> ferme un problème de `PROBLEMES.md` ; ce qui n'est pas tranché ici sera
> recopié tel quel.

---

## 1. Décisions de modèle à figer avant de coder

| # | Question | Décision retenue | Ferme |
|---|---|---|---|
| D1 | Comment représenter une échéance ? | **Un mois civil matérialisé** dans `echeances` (exercice, année, mois, date, montant dû). Un mois appartient à **un seul** exercice (`UNIQUE (annee, mois)`). | P01 |
| D2 | Flottants ou entiers ? | **Entiers de FCFA** (`i64` en Rust, `INTEGER` en SQL). Le FCFA n'a pas de sous-unité. | P04 |
| D3 | Comment ventiler un versement ? | Allocation **en cascade** sur les échéances impayées de l'exercice, de la plus ancienne à la plus récente, **sans dépasser le reste dû**. `montant_total = Σ affectations` par construction. Reliquat non affectable → refus explicite. | P04, P22 |
| D4 | Comment numéroter les reçus ? | `sequences('recu', année)` + `paiements.numero_recu UNIQUE`, attribué **dans la transaction du paiement**, jamais réattribué. | P08 |
| D5 | Combien de bases ? | **Une seule** base, choisie au premier lancement et mémorisée. `PRAGMA journal_mode = WAL`. Sauvegardes rotatives (n et n-1). | P03, P16 |
| D6 | Que faire de la généalogie aplatie par l'import ? | On **conserve l'historique tel quel** (aucune réparation silencieuse) ; l'écran Membres permet de rétablir les liens. L'importateur ne réapplique plus l'aplatissement. | P06 |
| D7 | Qui doit des échéances ? | Membres `actif` + bornes `date_entree` / `date_sortie` (facultatives) sur la date de l'échéance. Les autres statuts ne génèrent aucun dû, mais leur historique reste compté. | — |
| D8 | Changer le tarif réécrit-il le passé ? | **Non.** `echeances.montant_du` est figé. Changer un tarif ne touche que les échéances **non encore réglées**, après confirmation. | P01 |
| D9 | Que peut-on supprimer ? | Membre avec descendants ou paiements : refus (FK `RESTRICT`). Versement : suppression autorisée (libère l'échéance), le numéro de reçu reste consommé. Exercice : refusé dès qu'une échéance est réglée. | P09, P21 |
| D10 | Comment produire reçus, listes et exports ? | **Une seule source de données** (les vues SQL), rendue en HTML/CSS puis imprimée par le WebView2 ; CSV généré depuis le même jeu de lignes. Plus de second calcul en Python. | P04, P07 |

### Détail de D3 (l'algorithme central)

```text
entrées : membre, exercice, nombre de mois ou liste d'échéances, montant demandé
1. charger les échéances impayées de l'exercice pour ce membre
   (v_echeance_membre WHERE reste > 0 ORDER BY annee, mois)
2. si un montant est imposé : total = n × montant_du des échéances choisies
3. ventiler dans l'ordre, montant_i = min(reste_dû_i, reste_à_ventiler)
4. si reste_à_ventiler > 0 à la fin : erreur « X F ne peuvent pas être
   affectés à cet exercice » (l'utilisateur ajoute des mois ou paie un autre
   exercice)
5. écrire paiement + affectations + numéro de reçu dans UNE transaction
6. contrôler dans la transaction : v_paiements_incoherents vide,
   v_affectations_depassement vide
```

Cas particulier assumé : l'historique importé contient deux affectations de
2 000 F pour un dû de 1 000 F (paiement 105, novembre et décembre 2025). Elles
sont **conservées telles quelles** ; la vue `v_affectations_depassement` les
signale dans l'écran de contrôle, sans bloquer la migration ni les totaux.

---

## 2. Schéma cible

Le DDL complet et exécutable est dans **`schema_v2.sql`** (`PRAGMA
user_version = 2`). Correspondance avec l'existant :

| v1 (Python) | v2 (Rust) | Changement |
|---|---|---|
| `clans`, `grandes_familles`, `lignees`, `familles`, `membres` | idem | `COLLATE NOCASE` sur les noms, `date_entree`/`date_sortie`, `cree_le` |
| `campagnes` (`annee UNIQUE`) | `exercices` (période unique) | **plus d'année-étiquette unique** : 01/07 → 30/06 est légal |
| — | `echeances` | **nouveau** : un mois = une ligne, montant dû figé |
| `paiements` (+ `campagne_id`) | `paiements` (sans exercice) | l'exercice se déduit des affectations ; `numero_recu` |
| `affectations (annee, mois)` | `affectations (echeance_id)` | plus de mois libre, plus de doublon possible |
| `parametres` (clé/valeur, compteurs de reçus) | `meta` + `sequences` | les reçus sortent de la table de réglages |
| `v_solde_membre_campagne` (`× 12`) | supprimée | remplacée par `v_echeance_membre` / `v_solde_membre_exercice` |

Vues fournies : `v_membre_complet`, `v_echeance_membre`,
`v_solde_membre_exercice`, `v_encaisse_exercice`, `v_paiements_incoherents`,
`v_affectations_depassement`.

Garde-fous en base : parent dans la même famille (trigger), anti-cycle
(trigger), échéance dans la période de l'exercice (trigger), suppressions
protégées par `RESTRICT`, unicité du nom dans son parent.

---

## 3. Architecture technique

```text
fonds-entraide/
├── Cargo.toml              # workspace
├── core/                   # crate métier — AUCUNE dépendance à Tauri
│   ├── src/lib.rs
│   ├── src/db/mod.rs       # ouverture, PRAGMA, migrations, PRAGMA user_version
│   ├── src/domaine/        # Membre, Exercice, Echeance, Paiement, Recu, Montant
│   ├── src/services/       # cotisations, ventilation, tableau_bord, recus, exports
│   └── tests/              # goldens + scénarios (base en mémoire)
├── src-tauri/              # commandes Tauri fines, chemins, état
│   └── src/main.rs
└── ui/                     # Svelte + TypeScript + Tailwind
```

- **Cœur métier** : `rusqlite` (feature `bundled`), `chrono`, `serde`,
  `thiserror`. Une transaction par commande d'écriture ; `foreign_keys = ON`,
  `journal_mode = WAL`, `synchronous = NORMAL`.
- **Interface** : Tauri 2 + Svelte/TypeScript/Tailwind (ou React si tu
  préfères). Un seul thème sombre soigné en v1, tokens issus de `Design.md`,
  navigation par onglets, tableaux virtualisés.
- **Commandes Tauri** (fines, sans logique) : `lister_clans`, `creer_clan`,
  `modifier_clan`, `supprimer_clan`, idem pour chaque niveau,
  `exercices_lister`, `exercice_ouvrir`, `situation_membre`,
  `paiement_enregistrer`, `tableau_bord`, `recu_preparer`, `recu_pdf`,
  `liste_pdf`, `export_csv`, `sauvegarder`, `restaurer`.
  Erreurs sérialisées `{ code, message }` — jamais de panique visible.
- **Typage du domaine** :

```rust
pub struct Montant(i64);                 // FCFA entiers
pub struct Periode { debut: NaiveDate, fin: NaiveDate }
pub struct Ventilation { echeance_id: i64, montant: Montant }

pub fn ventiler(dus: &[(i64, Montant)], total: Montant)
    -> Result<Vec<Ventilation>, ErreurMetier>;
```

- **Tests** : `cargo test` sur `core` uniquement, `open_in_memory()` + les
  goldens du § 5. L'interface n'a pas besoin d'être lancée pour valider
  l'argent.

---

## 4. Phases

| Phase | Livrable | Critère de sortie |
|---|---|---|
| **0. Sécuriser** | dépôt git, copie `reference_2026.db` (`.backup`), goldens du § 5 figés dans un fichier | `git log` existe, copie vérifiée par `integrity_check` |
| **1. Schéma** | `schema_v2.sql` + migrations versionnées | schéma appliqué sur base vide, scénario de test vert (voir § 5.2) |
| **2. Migration des données** | binaire `migrate` (ou script jetable) v1 → v2 | counts et sommes identiques au § 5.1, `v_paiements_incoherents` vide |
| **3. Cœur métier** | `core` : lecture, ventilation, situation, tableau de bord, reçus | tests goldens verts, aucune UI |
| **4. Socle Tauri** | fenêtre, sélection de la base, commandes lecture | l'app affiche les 7 clans et 599 membres depuis la base migrée |
| **5. Écrans** | 5 niveaux, cotisations, tableau de bord, paramètres | parité de la checklist § 5.3 |
| **6. Reçus & exports** | reçu PDF/impression, listes PDF, CSV | reçu numéroté stable, total imprimé = total à l'écran |
| **7. Entretien** | sauvegardes, restauration, purge, mode démo | purge testée sur copie, base réelle intacte (SHA-256) |
| **8. Recette & packaging** | installeur MSI/NSIS, doc utilisateur | parcours complet sur poste cible, données réelles |

Chemin critique : 0 → 1 → 2 → 3. Les phases 4/5 peuvent démarrer dès que le
schéma est stable, avec des données factices.

---

## 5. Critères d'acceptation

### 5.1 Données (après migration, sur `reference_2026.db`)

| Contrôle | Valeur exigée |
|---|---|
| `PRAGMA integrity_check` / `foreign_key_check` | `ok` / 0 ligne |
| clans / GF / lignées / familles / membres | 7 / 46 / 46 / 391 / 599 |
| exercices / paiements / affectations | 3 / 227 / 1 805 |
| `SUM(affectations.montant)` | **1 807 000** |
| 2024 / 2025 / 2026 | 1 453 000 / 338 000 / 16 000 |
| `SUM(paiements.montant_total)` | 1 807 000 |
| `v_paiements_incoherents` | **0 ligne** |
| `v_affectations_depassement` | exactement 2 lignes : membre 209, nov. et déc. 2025 (paiement 105) |
| reçu existant `recu_paiement_2` | conservé comme `paiements.numero_recu` |

### 5.2 Règles (tests automatisés du crate `core`)

1. Exercice `01/04/2026 → 31/03/2027` : 12 échéances, d’avril à mars ;
   régler avril→novembre **réussit**, décembre→mars **échoue** (aujourd'hui
   l'inverse se produit — P01).
2. Deux exercices ne peuvent pas revendiquer le même mois civil (contrainte).
3. Un versement de 5 000 F sur 3 mois de 1 000 F est **refusé** (reliquat
   non ventilable) ; 3 000 F passe et `montant_total = Σ affectations`.
4. Un mois partiellement réglé (600 F sur 1 000) laisse un reste de 400 F et
   un second versement de 400 F le solde.
5. `numero_recu` : deux impressions du même reçu donnent le même numéro ;
   supprimer le paiement ne réattribue pas son numéro.
6. Suppressions : membre avec descendant → refus ; membre avec paiement →
   refus ; exercice avec échéance réglée → refus.
7. Changement de famille d'un membre avec parent dans l'ancienne famille →
   erreur métier affichée (pas d'exception brute — P05).
8. Un membre `date_sortie = 30/06/2026` ne doit rien sur les échéances
   postérieures.
9. Tableau de bord : une seule requête par vue, **aucune boucle par membre**
   (test de non-régression sur le nombre de requêtes — P07).

### 5.3 Parité fonctionnelle (checklist manuelle)

| Écran | Doit permettre |
|---|---|
| Clans / GF / Lignées / Familles | créer, modifier, supprimer, filtrer par parent, exporter la liste |
| Membres | parent limité à la famille, anti-cycle, téléphone, statut, fratrie |
| Cotisations | filtres en cascade, mois réglés, arriérés, calendrier, enregistrement, historique, reçu |
| Tableau de bord | 5 cartes, répartition par niveau, retards, grille 12 mois, montants par année, par membre/an |
| Paramètres | tarif par exercice, exercices libres, sauvegarde/restauration/import, purge à double confirmation |

### 5.4 Qualité

`cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test` verts ;
aucun `unwrap()` sur une entrée utilisateur ; aucune erreur SQLite brute
affichée.

---

## 6. Migration des données

Un exécutable `migrate` (ou un script Python jetable, tant que la cible est
vérifiée) lit la base v1 **en lecture seule** et écrit une base v2 neuve :

| Étape | Règle |
|---|---|
| hiérarchie | copie directe, identifiants conservés |
| `campagnes` → `exercices` | 2024/2025/2026 en année civile (01/01 → 31/12), montant conservé |
| exercices → `echeances` | 12 lignes par exercice, `montant_du = montant_mensuel`, `date_echeance` au 1er du mois |
| `paiements` | copie ; `numero_recu` repris de `parametres.recu_paiement_<id>` |
| `affectations` | `(annee, mois)` → `echeance_id` par jointure ; montant **inchangé** (les 2 000 F restent 2 000 F) |
| `parametres.recu_numeros` | → `sequences` |
| fin | `meta` : version, date de migration, empreinte SHA-256 de la source |

La source n'est **jamais** modifiée. En cas d'écart sur un seul golden : la
migration échoue et n'écrit rien (transaction globale).

### Ce que la migration a révélé sur les données réelles

Exécutée sur `cotisations.db` (SHA-256 conservé), elle a produit
`cotisations_v2.db` : 1 807 000 FCFA, 1 805 affectations, 227 paiements,
intégrité `ok`, 0 clé étrangère orpheline, 0 paiement incohérent, et les deux
seuls dépassements de l'historique (membre 209, nov. et déc. 2025) signalés
sans être modifiés. Quatre constats ont modifié le schéma :

1. **Deux familles homonymes dans une même lignée** (lignées 18 et 32) :
   l'`UNIQUE (lignee_id, nom)` initialement prévu est retiré. Fusionner ou
   renommer serait une réparation silencieuse des données de l'adhérent.
2. **Trois groupes de membres strictement homonymes** (famille 336 :
   « Kouakou Jeanne » ×3 et « Kouakou Salange » ×3 ; famille 380 : « SAKIA »
   sans prénom ×2) : aucune contrainte d'unicité sur les noms de membres ;
   le signalement de doublon se fera à la saisie.
3. **Aucun montant fractionnaire** malgré le type `REAL` de la v1 : la
   conversion en entiers ne perd rien. Le script refuse désormais la
   migration si un montant non entier apparaît (plutôt que de le tronquer).
4. **Toutes les dates sont déjà ISO** : 0 normalisation nécessaire, mais le
   script convertit `JJ/MM/AAAA` et refuse une date illisible.

Le script `migrer_v2.py` est rejouable : il reconstruit la cible depuis zéro,
la vérifie, puis la publie par renommage atomique.

---

## 7. Risques et parades

| Risque | Parade |
|---|---|
| Perdre ou fausser l'historique financier | copie `.backup` figée, migration transactionnelle, goldens § 5.1 |
| Recopier les bugs de modèle | décisions D1–D10 figées **avant** la phase 3 |
| Dérive fonctionnelle (écran oublié) | checklist § 5.3 cochée écran par écran |
| Design « pro » qui glisse en fin de projet | maquette des 6 écrans clés avant la phase 5 |
| Impression PDF/reçus découverte trop tard | prototype d'impression WebView2 dès la phase 4 |
| WebView2 absent sur un poste ancien | installeur avec runtime inclus, test sur poste cible |
| Coût du 100 % Rust pour l'UI | Tauri + web pour l'UI ; Rust pour tout le reste |

---

## 8. Hors périmètre (v1)

Multi-utilisateur / réseau / synchronisation · import Excel récurrent (une
seule migration) · application mobile · refonte du référentiel orthographique
des patronymes (`REALISE.md` § 4.5) · thème clair complet (un thème sombre
soigné suffit en v1) · rappels automatiques par SMS.

---

## 9. Estimation

| Phase | Charge |
|---|---|
| 0–2 (sécuriser, schéma, migration) | 3–4 j |
| 3 (cœur métier + tests) | 5–8 j |
| 4 (socle Tauri) | 2–3 j |
| 5 (écrans) | 10–15 j |
| 6 (reçus, PDF, exports) | 4–6 j |
| 7 (sauvegardes, purge, démo) | 3–4 j |
| 8 (recette, packaging, doc) | 4–5 j |
| **Total** | **31–45 jours-homme** |

La phase 5 est la plus élastique : c'est là que se joue le « design pro », et
elle se découpe facilement (un écran = un lot livrable).

---

## 10. Définition de « terminé »

1. Les goldens § 5.1 passent sur la base migrée.
2. Les 9 tests de règles § 5.2 passent en CI (`cargo test`).
3. La checklist § 5.3 est cochée sur le poste du caissier.
4. Un reçu imprimé porte le même numéro et le même montant qu'avant.
5. La purge, exercée **par des clics réels**, ne casse rien et laisse la base
   réelle intacte (empreinte SHA-256 identique).
6. `PROBLEMES.md` est clos, ou chaque point restant est explicitement reporté.
