# Cotisations – Fonds d'entraide (clans KOUADIO AMBOFF, YAOCRE, ADJOUA MALA, AGO, TCHOUWA, KACOUTIE EDJAPA, ASSOMOU)

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

**7 clans :** KOUADIO AMBOFF (16 GF), YAOCRE (9), KACOUTIE EDJAPA (7),
AGO (5), ADJOUA MALA (4), TCHOUWA (4), ASSOMOU (1).

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
4. 7 feuilles sans grille de mois (listes de noms de lignées) → ignorées :
   `AGOH`, `KOUADIO AMBOFF`, `YAOCRE`, `ADJOUA MALA`, `TCHOUWA`,
   `KACOUTIE EDJAPA`, `ASSOMOU`.

## Modèle de données

- **`membres`** : `nom`, `prenom`, `telephone`, `ordre_fratrie`, `parent_id`
  (parent direct), `famille_id`, `statut` (actif/inactif/decede/parti/suspendu).
- **`campagnes`** : une par année, `montant_mensuel` = 1 000 FCFA.
- **`paiements`** : un versement réel (`date_paiement`, `montant_total`, `mode`).
- **`affectations`** : détail mois par mois d'un paiement `(annee, mois, montant)`.

> ⚠️ **Un paiement peut couvrir plusieurs années.** Les totaux se calculent
> donc **toujours depuis `affectations`**, jamais depuis `paiements.campagne_id`.

## Totaux (vérifiés = conformes au classeur)

| Campagne | Cotisants | Total FCFA |
|---|---|---|
| 2024 | 227 | **1 453 000** |
| 2025 | 49 | **338 000** |
| 2026 | 2 | **16 000** |

Le récapitulatif Excel `TOTAL GRANDES FAMILLES` de 2024 (1 453 000) correspond
exactement à la somme des feuilles et à la base. **Écart : 0.**

## Utilisation

```bash
python import_complet.py                          # (re)construire la base

python requetes.py                                # récap + état par clan 2024/2025
python requetes.py --clans --annee 2024           # état par clan
python requetes.py --clan "YAOCRE"                # détail d'un clan
python requetes.py --feuille "AMBOFF Boa"         # détail d'une grande famille
python requetes.py --lignee "N'GUETTA"            # membres d'une lignée
python requetes.py --membre 211                   # fiche d'un membre
python requetes.py --recherche "YAO"              # recherche par nom
python requetes.py --impayes 2025                 # actifs sans versement
python requetes.py --grille "AMBOFF Mian Bla" --annee 2024   # grille mensuelle
python requetes.py --top 20                       # meilleurs cotisants
python requetes.py --synthese 2024                # synthèse par GF
python requetes.py --audit 2025                   # audit base vs répertoires Excel

python extrait_repertoires.py                     # (re)générer repertoires.json
```

## Audit : pourquoi le récapitulatif Excel affiche 317 000 en 2025

Le classeur contient **7 feuilles-répertoires** (`KOUADIO AMBOFF`, `YAOCRE`,
`ADJOUA MALA`, `AGOH`, `TCHOUWA`, `KACOUTIE EDJAPA`, `ASSOMOU`) : des tableaux
agrégés par lignée, auxquels le récapitulatif `TOTAL GENERAL COTISATIONS`
se réfère (`=+'AGOH'!AB8`, etc.).

Ces répertoires portent des totaux **très inférieurs et désynchronisés**
par rapport aux 46 feuilles détaillées :

| Exercice | Détail (base) | Répertoires (Excel) | Écart |
|---|---|---|---|
| 2024 | **1 453 000** | 49 000 | +1 404 000 |
| 2025 | **338 000** | 2 000 | +336 000 |
| 2026 | **16 000** | 0 | +16 000 |

La **base fait foi** : elle reproduit exactement la somme des feuilles
détaillées, et son total 2024 (1 453 000) correspond au récap Excel.
Utiliser `--audit <année>` pour le détail clan par clan.

## Points d'attention

1. Les descendants anonymes du fichier source ne sont pas des membres (règle 1).
2. `AMBOFF Apangni` et `KOUAKOU DJAPA` n'ont **aucun membre** : leurs feuilles
   ne contiennent que des marqueurs `(Enfant1)` sans nom et 0 FCFA.
3. Les noms oscillent dans la source (`GNANDAKY`/`GNANDAKI`, `YAOCRE`/`YACRE`,
   `YOACRE`) — conservés tels quels dans `nom`, la clé de regroupement étant la
   grande famille.
4. La `date_paiement` est une approximation (28 du dernier mois couvert) : le
   classeur ne contient aucune date réelle de versement.
