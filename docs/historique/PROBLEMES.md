# PROBLEMES.md — Registre des problèmes connus

> **Audit du 10/11/2026.** Périmètre : les 25 modules Python (9 402 lignes),
> `schema.sql` (293 lignes) et la base `cotisations.db`.
>
> **Méthode** : lecture intégrale des modules métier, des écrans, des exports
> et de l'import ; `python -m py_compile *.py` (OK) ; `python -m pyflakes *.py`
> (1 seul avertissement, volontaire : `import reportlab` de test) ; requêtes
> de contrôle sur `cotisations.db` ; mesures d'exécution et scénarios
> reproduits **sur copie** de la base (`_revue_travail.db`, supprimée après).
>
> **Périmètre non couvert** : l'interface graphique n'a pas été lancée. Les
> problèmes d'affichage ou de comportement de widgets ne sont donc pas tous
> recensés ici.
>
> **Base de référence au moment de l'audit** : `integrity_check = ok`,
> 0 violation de clé étrangère, 7 clans / 46 GF / 46 lignées / 391 familles /
> 599 membres / 3 campagnes / 227 paiements / 1 805 affectations,
> **1 807 000 FCFA** (2024 : 1 453 000 · 2025 : 338 000 · 2026 : 16 000).
> Ces chiffres constituent la vérité de référence pour toute réécriture.

---

## 1. Synthèse

| ID | Gravité | Problème | Où | Survit à une réécriture ? |
|---|---|---|---|---|
| P01 | 🔴 | Exercices non civils : mois échus confondus avec les numéros de mois | `cotisations.py` | **Oui** (règle métier à trancher) |
| P02 | 🔴 | Aucun test automatisé, aucun dépôt git | projet | Oui (dette de projet) |
| P03 | 🔴 | L'application ouvre `familles.db` (vide) au lieu de la base de référence | `db.py`, `app.py` | Oui (choix de produit) |
| P04 | 🟠 | `montant_total` ≠ somme des `affectations` (arrondi + montant libre) | `cotisations.py` | Oui (modèle) |
| P05 | 🟠 | `IntegrityError` non interceptée au changement de famille / de clan | `ecran_base.py`, `ecran_grandes_familles.py` | Non (bug d'implémentation) |
| P06 | 🟠 | L'import aplatit la généalogie (niveaux 2 et 3 accrochés au niveau 1) | `import_complet.py` | Non (script jetable) |
| P07 | 🟠 | Requêtes N+1 sur toutes les synthèses | `tableau_de_bord.py`, `ecran_cotisations.py` | **Oui** (si le portage copie les requêtes) |
| P08 | 🟠 | Numéros de reçus stockés dans `parametres` (1 clé par paiement) | `recus.py`, `parametres.py` | **Oui** (modèle) |
| P09 | 🟡 | La vue `v_solde_membre_campagne` calcule `montant_mensuel * 12` | `schema.sql` | Non (vue non utilisée) |
| P10 | 🟡 | Duplication des écrans hiérarchiques (~1 000 lignes) | `app.py`, `ecran_base.py`, `ecran_grandes_familles.py` | Non (disparaît au portage) |
| P11 | 🟡 | Échecs silencieux (`except Exception: pass`) | `app.py`, `theme.py`, `mode_demo.py` | Partiellement |
| P12 | 🟡 | SQL assemblé par f-string, API de CRUD trop permissive | `db.py`, `parametres.py` | Non (réécrit) |
| P13 | 🟡 | Thème recoloré par table de correspondance de couleurs en dur | `theme.py` | Non (réécrit) |
| P14 | 🟡 | Pas de version de schéma, pas de migration | `schema.sql`, `db.py` | **Oui** (à prévoir) |
| P15 | 🟡 | « Tous » coche aussi les mois futurs → erreur garantie à l'enregistrement | `ecran_cotisations.py` | Oui (UX à spécifier) |
| P16 | 🟡 | Deux bases de données sans règle claire de laquelle fait foi | projet | Oui (choix de produit) |
| P17 | 🟡 | Dates de paiement toutes approximées au 28 | `import_complet.py` | Non (donnée historique) |
| P18 | 🟡 | Documentation redondante et déjà dérivée (README / RESUME / REALISE / GUIDE) | docs | Oui (à réécrire avec l'app) |
| P19 | 🟢 | Pas de journalisation (`print`), pas de typage | projet | Non |
| P20 | 🟢 | `os.startfile` / chemins Windows : non portable (assumé) | `exports.py`, `ecran_*.py` | Non (Tauri gère mieux) |
| P21 | 🟢 | Purge : `PRAGMA foreign_keys = OFF` fragile, `_vider_membres` en boucle | `parametres.py` | Oui (logique à revoir) |
| P22 | 🟢 | Surplus ignoré : un mois réglé 2 000 F ne consomme pas 2 mois | `cotisations.py` | Oui (règle métier) |

Légende : 🔴 bloquant · 🟠 majeur · 🟡 mineur · 🟢 confort.

---

## 2. Détail des problèmes

### P01 🔴 — Exercices non civils : « mois échus » n'est pas un numéro de mois

**Où** : `cotisations.py` → `mois_echus()`, `situation()`, `mois_impayes()`,
`enregistrer_versement()` ; répercuté dans `tableau_de_bord.py` et
`ecran_cotisations.py`.

**Nature** : `mois_echus()` renvoie un **nombre de mois écoulés depuis le début
de l'exercice**, tandis que tout le reste du code manipule des **numéros de
mois calendaires** (1 = janvier … 12 = décembre). Les deux notions ne
coïncident que pour une année civile.

**Reproduction (sur copie)** — exercice `01/04/2026 → 31/03/2027`, rattaché à
2026 :

```
mois_echus(2026) = 8
  mois [9, 10, 11] -> REFUSE : Ces mois ne sont pas encore échus pour 2026 :
                      Septembre, Octobre, Novembre. Seuls les 8 premiers mois
                      peuvent être réglés.
  mois [1, 2, 3]   -> ACCEPTE   (janvier-mars, antérieurs au début de l'exercice !)
```

**Causes précises** :

```python
# enregistrer_versement()
futures = sorted(m for m in mois_coches if echus and m > echus)

# mois_impayes()
limite = jusqua or (12 if annee < datetime.date.today().year
                    else datetime.date.today().month)

# situation()
"complet": ... len([m for m in payes if m <= echus and payes[m] >= mensuel]) == echus
```

`mois_impayes()` ignore en outre complètement la période réelle de l'exercice
et utilise le mois courant.

**Conséquences** : les « exercices libres » vendus dans les Paramètres sont
faux hors année civile ; les retards, le taux de recouvrement, `complet` et
les cases à cocher deviennent incohérents.

**Correctif recommandé** : représenter l'échéance par une **date** (ou
`(année, mois)` absolus) et non par un rang. `mois_echus` devient
« nombre de mois entre `date_debut` et `aujourd'hui` », et la validité d'un
mois se teste sur sa date, pas sur son numéro. À trancher **avant** toute
réécriture.

---

### P02 🔴 — Aucun test, aucun versionnage

**Constat** : 9 402 lignes de logique monétaire, **zéro test**, et
`git status` répond `fatal: not a git repository`. Les vérifications reposent
sur `mode_demo.py` + `sauvegardes/*.db` + des procès-verbaux dans
`RESUME.md`.

**Conséquences** : aucune protection contre les régressions ; un correctif
peut casser un calcul sans que personne ne le voie ; l'historique des
décisions n'existe que dans un fichier Markdown.

**Correctif recommandé** : `git init` + une dizaine de tests de
caractérisation figés sur la base de référence (voir § 4), exécutés avant
**et** après la migration.

---

### P03 🔴 — L'application ouvre par défaut une base vide

**Où** : `db.py` → `DB_PATH = BASE_DIR / "familles.db"` ; `app.py` → `main()`
appelle `db.initialiser()` sans argument.

**Constat** : les 599 membres vivent dans `cotisations.db`. `RESUME.md § 3`
indique que `familles.db` contient « 1 clan, 0 membre, 0 affectation,
0 campagne ». Au lancement, l'utilisateur voit donc une application vide et
doit passer par *Paramètres → Importer une base…* pour retrouver ses données.

**Conséquences** : impression de perte de données ; risque qu'un utilisateur
saisisse des données dans la mauvaise base.

**Correctif recommandé** : une seule base, choisie explicitement au premier
lancement (ou ouverte depuis un chemin mémorisé), avec un écran d'accueil.

---

### P04 🟠 — Le montant du paiement et la somme des affectations divergent

**Où** : `cotisations.py` → `enregistrer_versement()`.

```python
part = round(montant_total / len(mois_coches), 2)
```

**Reproduction** : versement de 5 000 F sur 3 mois →
`paiements.montant_total = 5000`, `SUM(affectations.montant) = 5000.01`
(1 666,67 × 3).

**Aggravant** : `montant_total` est librement saisissable dans l'écran. Un
mois dû de 1 000 F peut être réglé 500 F, ou 2 000 F (2 cas existent déjà en
base : paiement 105, novembre et décembre 2025). Le reçu imprime
`montant_total`, le tableau de bord additionne les `affectations`.

**Correctif recommandé** : calculer les parts en **entier de FCFA** avec
report du reste (`part = total // n`, puis distribuer le reliquat), ou
interdire un total différent de `n × mensuel`.

---

### P05 🟠 — Exception SQLite non affichée à l'utilisateur

**Où** : `ecran_base.py` → `EcranHierarchique.enregistrer()` (branche
« modification ») et `ecran_grandes_familles.py` → `enregistrer()`.

```python
db.modifier(self.con, self.NIVEAU, self.id_selection, nom, **extras)
col = db.NIVEAUX[self.NIVEAU]["parent_col"]
self.con.execute(f"UPDATE ... SET {col} = ? WHERE id = ?", (parent_id, ...))
```

Ce second `UPDATE` est **hors** du `try/except db.ErreurSaisie` et hors de
`db.modifier()`.

**Reproduction** : déplacer un membre vers une autre famille en conservant
son parent →

```
IntegrityError: Le parent doit appartenir à la même famille que le membre
```

Exception brute : rien à l'écran, trace dans la console uniquement.

**Correctif recommandé** : déplacer le changement de parent **dans**
`db.modifier()`, ou envelopper l'`UPDATE` et convertir en `ErreurSaisie`.

---

### P06 🟠 — L'import écrase la généalogie

**Où** : `import_complet.py`.

```python
parent_id = dernier_membre if niveau > 1 else None
```

Tous les membres de niveau 2 **et 3** sont rattachés au **dernier membre de
niveau 1** rencontré, jamais à leur parent réel.

**Mesures sur la base** : 461 membres sur 599 sans parent ; **0** membre dont
le parent est lui-même enfant. L'arbre du classeur est donc réduit à deux
niveaux (des fratries de plusieurs dizaines d'enfants).

**Autres défauts du script** :

- chemin source codé en dur (`C:/Users/HP/Documents/Fond Entraide Revise/…`) ;
- `DB.unlink()` supprime la base sans confirmation ;
- date de paiement fabriquée : `f"{annee}-{mois:02d}-28"` (les 227 paiements
  sont datés du 28) ;
- l'import n'est pas idempotent par conception (il détruit puis recrée).

**Correctif recommandé** : conserver `parent_id` réel (le niveau 2 devient le
parent des niveaux 3 de sa branche) ; sortir le chemin dans un argument ;
refuser d'écraser sans `--force`.

---

### P07 🟠 — Requêtes N+1 sur toutes les synthèses

**Mesures** (base réelle, `set_trace_callback`) :

| Fonction | Durée | Requêtes SQL |
|---|---|---|
| `tableau_de_bord.vue_ensemble(2025)` | 76 ms | **1 805** |
| `tableau_de_bord.membres_en_retard(2025)` | 78 ms | **1 800** |
| `tableau_de_bord.grille_mensuelle(2025)` | 63 ms | **601** |

À l'origine : `C.situation()` est appelée dans une boucle sur les membres, et
elle-même exécute `campagne()` + `mois_payes()`. `ecran_cotisations.recharger_membres()`
appelle en plus `situation()` **deux fois** par membre (une fois pour la ligne,
une fois pour le total).

**Conséquence** : acceptable à 599 membres, linéaire en `n` — l'onglet
deviendra pénible à quelques milliers de membres. C'est un défaut de
**conception des requêtes**, pas du langage : il sera recopié tel quel dans
une réécriture si l'on ne réécrit pas les calculs en `GROUP BY` / une seule
requête jointe.

---

### P08 🟠 — Numérotation des reçus dans la table `parametres`

**Où** : `recus.py` (`attribuer_numero`, clé `recu_paiement_<id>`),
`parametres.py` (`purger`).

**Conséquences** :

1. La table `parametres` grossit d'une ligne par paiement (elle contient déjà
   `recu_paiement_2` et `recu_numeros`).
2. `recus.donnees_recu()` **écrit en base** alors qu'il est appelé par un
   simple « aperçu PDF ».
3. `purger("tout")` supprime `parametres` : les compteurs repartent de zéro et
   les numéros sont réattribués — ce qui contredit la garantie documentée
   (« le numéro n'est jamais réattribué »).
4. Aucune contrainte d'unicité : deux paiements ne peuvent pas être garantis
   distincts au niveau du schéma.

**Correctif recommandé** : colonne `numero_recu TEXT UNIQUE` sur `paiements`
(+ table de séquences par année si nécessaire).

---

### P09 🟡 — Vue SQL en contradiction avec la règle métier

**Où** : `schema.sql` → `v_solde_membre_campagne`.

```sql
c.montant_mensuel * 12 AS attendu_annuel
```

Alors que partout ailleurs (et dans `RESUME.md`) la règle est « ne jamais coder
/12 : utiliser les mois échus ». La vue n'est utilisée par aucun module
aujourd'hui : bug latent.

---

### P10 🟡 — Trois implémentations du même écran

**Où** : `app.py` (`EcranClans`), `ecran_base.py` (générique),
`ecran_grandes_familles.py` (spécifique), plus les cascades de filtres
recopiées dans `ecran_cotisations.py`.

**Conséquence** : chaque correctif d'ergonomie ou de validation doit être
appliqué 3 fois ; les trois variantes ont déjà divergé (gestion du parent,
messages, boutons). ~1 000 lignes dupliquées.

**Note** : ce problème **disparaît** avec une réécriture soignée — inutile de
le corriger en Python si la migration est décidée.

---

### P11 🟡 — Échecs silencieux

**Où** : `app.Application.tout_recharger()` (5 blocs `except Exception: pass`),
`theme.Gestionnaire.appliquer()` (observateurs), `mode_demo.lancer()`
(`con.close()`).

**Conséquence** : après une restauration ou une purge, si un rechargement
échoue, la barre d'état affiche « Données rechargées » et l'écran reste
périmé. Aucune trace.

**Correctif** : journaliser et remonter à l'utilisateur.

---

### P12 🟡 — SQL assemblé par f-string, CRUD trop permissif

**Où** : `db.py` (`ajouter`, `modifier`, `lister`, `supprimer`),
`parametres.py` (`purger`, `etat_base`), `tableau_de_bord.py`
(`_NIVEAUX`, `format(filtre=...)`).

Les noms de tables proviennent de constantes internes : **pas d'injection
exploitable aujourd'hui**. Mais `db.ajouter(..., **autres)` et
`db.modifier(..., **autres)` acceptent n'importe quelle clé comme nom de
colonne ; la sûreté repose entièrement sur la discipline des appelants.

**Correctif** : listes blanches de colonnes par niveau, requêtes constantes.

---

### P13 🟡 — Thème par correspondance de couleurs

**Où** : `theme.py` (`CORRESPONDANCES`, `_journal`, `recenser_tk`).

Les écrans écrivent des couleurs claires en dur ; le gestionnaire les traduit
par une table (`"#1f4e5f" → accent`, etc.). Toute nouvelle couleur non listée
reste claire en mode sombre — c'est exactement le bug « zones blanches » déjà
corrigé une fois.

**Note** : modèle de thème entièrement remplacé par une réécriture (CSS/Tauri
ou thème natif). **Ne pas investir ici.**

---

### P14 🟡 — Pas de version de schéma ni de migration

**Constat** : `schema.sql` est rejoué à chaque démarrage (`CREATE ... IF NOT
EXISTS`), donc une base ancienne n'est **jamais** mise à jour. Cela s'est déjà
produit : `cotisations.db` a dû être complétée à la main
(`familles.description`, `membres.sexe`, table `parametres`), avec sauvegardes
manuelles. Aucun `PRAGMA user_version`.

**Correctif** : numéro de version + migrations ordonnées, dès le nouveau
projet.

---

### P15 🟡 — Le bouton « Tous » coche des mois non échus

**Où** : `ecran_cotisations.py` → `_cocher(None)` coche les 12 mois non
réglés, puis `_maj_montant()` propose `12 × mensuel`. `enregistrer()` appelle
ensuite `enregistrer_versement()`, qui **refuse** les mois futurs.

**Conséquence** : un clic sur « Tous » mène mécaniquement à un message
d'erreur. `_cocher_impayes()` est aussi affecté par P01 (mois calculés sur le
mois courant, y compris pour un exercice futur).

---

### P16 🟡 — Deux bases, deux rôles, aucune règle

`familles.db` (saisie) et `cotisations.db` (référence importée) coexistent,
avec des schémas proches mais non garantis identiques. Rien dans l'application
n'indique laquelle est ouverte. Voir P03.

---

### P17 💡/🟡 — Dates historiques fabriquées

Les 227 paiements importés portent la date du 28 du dernier mois couvert
(`import_complet.py`). C'est documenté, mais toute analyse de trésorerie ou de
délai de versement produite à partir de ces données est fausse. À conserver
comme donnée historique, pas comme vérité.

---

### P18 🟡 — Documentation redondante

`README.md`, `RESUME.md`, `REALISE.md`, `GUIDE.md`, `Design.md` se recoupent
(volumétrie, modèle, commandes). `RESUME.md` reconnaît que 3 sections du
`GUIDE.md` sur 12 contenaient de vrais écarts avec le code. Aucune n'est
générée depuis le code.

**Recommandation** : après migration, une seule doc utilisateur + un
`README` technique, et supprimer les comptes rendus de session.

---

### P19 🟢 — Pas de journalisation, pas de typage

Aucun `logging` : les erreurs partent en `print` sur la console, invisible
quand l'application est lancée par double-clic. Aucune annotation de type,
alors que la logique est numérique et datée.

---

### P20 🟢 — Non portable (assumé)

`os.startfile` (aperçu PDF, impression), `explorer`, `.ico`,
`pythonw`. L'application est Windows-only de fait. Une réécriture Tauri
supprime ce point (impression via le moteur web, icônes multi-plateformes).

---

### P21 🟢 — Purge fragile

**Où** : `parametres.purger()`.

- `PRAGMA foreign_keys = OFF` est **silencieusement ignoré** s'il existe une
  transaction ouverte (Piège SQLite) ; le code ne s'en assure pas.
- `_vider_membres()` boucle `DELETE ... WHERE id NOT IN (SELECT parent_id ...)`
  : correct, mais une requête par niveau de profondeur.
- `purger("hierarchie")` conserve `campagnes` tout en supprimant les
  `affectations` : un exercice peut rester « ouvert » avec 0 mois saisis.
- `VACUUM` est exécuté après `commit()`, hors `finally`.

**Note** : cette purge est le correctif de la dernière session ; elle n'a
jamais été exercée par des clics réels (voir `RESUME.md § 0.1`).

---

### P22 🟢 — Surplus non ventilé

Un mois réglé 2 000 F pour un mensuel de 1 000 F ne « consomme » qu'un mois :
le surplus reste collé au mois au lieu d'être affecté aux mois suivants ou
signalé. Cas réel en base (paiement 105).

---

## 3. Ce que la réécriture Rust fait disparaître d'office

Inutile de corriger ces points en Python si la migration est décidée :

- **P05** (exceptions non capturées) : `Result` + gestion d'erreur explicite.
- **P06** (script d'import) : remplacé par un importateur unique, testé.
- **P09, P10, P12, P13, P19, P20** : écrans, SQL et thème réécrits.
- **P18** : la doc sera réécrite avec l'application.

## 4. Ce qu'il faut trancher AVANT d'écrire la première ligne de Rust

Ces points sont des **règles métier ou de modèle** : les recopier en Rust
reviendrait à recopier les bugs.

1. **P01 — représentation du temps** : une échéance est-elle un
   `(année, mois)` absolu rattaché à un exercice daté ? Comment se calcule un
   retard sur un exercice 01/07 → 30/06 ? (bloquant)
2. **P04 — politique de montant** : montant imposé (`n × mensuel`) ou libre
   avec ventilation du reste et des surplus (P22) ?
3. **P08 — numérotation** : séquence par année, stockée avec le paiement,
   jamais réattribuée, y compris après purge.
4. **P03/P16 — une seule base** : où vit le fichier, comment est-il choisi,
   que se passe-t-il au premier lancement ?
5. **P07 — une requête par vue** : écrire les agrégats en SQL (ou en Rust avec
   un seul balayage), pas en boucle.
6. **P14 — version de schéma** et stratégie de migration des données
   existantes (599 membres, 1 807 000 F à l'identique).

## 5. Jeu de tests de référence (« golden values »)

Valeurs à figer dans les tests du nouveau projet — elles serviront de
**critère d'acceptation** de la migration. Sur `cotisations.db` :

| Contrôle | Valeur attendue |
|---|---|
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | 0 ligne |
| clans / GF / lignées / familles / membres | 7 / 46 / 46 / 391 / 599 |
| campagnes / paiements / affectations | 3 / 227 / 1 805 |
| `SUM(affectations.montant)` | **1 807 000** |
| 2024 / 2025 / 2026 | 1 453 000 / 338 000 / 16 000 |
| `SUM(paiements.montant_total)` | 1 807 000 |
| paiements couvrant plusieurs années | 49 |
| membres en retard 2025 (`membres_en_retard`) | 596 |
| clan le plus contributeur (2024) | à figer depuis `--clans --annee 2024` |

Commandes de reproduction :

```bash
python -m py_compile *.py
python -m pyflakes *.py
python requetes.py --recap
python requetes.py --clans --annee 2024
python -c "import sqlite3;c=sqlite3.connect('cotisations.db');print(c.execute('SELECT SUM(montant) FROM affectations').fetchone(), c.execute('PRAGMA integrity_check').fetchone())"
```

---

## 6. Ce qui est solide et doit être conservé

À ne pas jeter lors du portage :

- **Le modèle `paiements` + `affectations`** et la règle « tous les totaux se
  calculent sur `affectations.annee`, jamais sur `paiements.campagne_id` ».
- **Les invariants en base** : parent dans la même famille, anti-cycle,
  suppression protégée (triggers SQL, à transposer en contraintes + triggers
  SQLite côté Rust).
- **La hiérarchie à 5 niveaux** et l'unicité du nom dans son parent.
- **Le principe « zéro dépendance obligatoire »** pour les PDF (le moteur
  maison est un atout sur un poste hors ligne).
- **`mode_demo`** : copie + empreinte SHA-256 + état JSON avant/après.
- **La numérotation stable des reçus** et le montant en toutes lettres.
- **Les libellés, messages et parcours utilisateur** déjà validés sur le
  terrain : ils constituent le cahier des charges de la nouvelle interface.
