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


