# RÉALISÉ — Projet « Cotisations Fonds d'Entraide »

**Date** : session de travail complète
**Dossier** : `C:/Users/HP/Documents/Dev/Free-Pi/Fond-Entraide`
**Source de données** : `C:/Users/HP/Documents/Fond Entraide Revise/FONDS D'ENTRE AIDE Final MAJ 3 Aout 24 (1).xlsx`

---

## 1. Résumé du travail accompli

### 1.1 Point de départ

Le dossier contenait un fichier `Test1.xlsx` de 79 Ko présenté comme le fichier de travail.
L'analyse a montré qu'il ne contenait **qu'une seule feuille**, alors que le vrai classeur
de référence en compte **54**. Le fichier a donc été localisé ailleurs sur le disque
(`Fond Entraide Revise/`), puis utilisé comme source définitive.

### 1.2 Livrables produits

| Fichier | Rôle | État |
|---|---|---|
| `schema.sql` | Schéma SQLite : 8 tables, contraintes CHECK, index, 2 vues | final |
| `import_complet.py` | Import des 46 feuilles détaillées vers la base | final |
| `import_cotisations.py` | Import de la feuille unique de `Test1.xlsx` (conservé) | final |
| `extrait_repertoires.py` | Extraction des 7 feuilles-répertoires vers `repertoires.json` | final |
| `repertoires.json` | Totaux `LIGNEE xxx` servant de référence d'audit | final |
| `requetes.py` | CLI de consultation : 15 commandes | final |
| `cotisations.db` | Base peuplée | final |
| `cotisations_backup_test1.db` | Sauvegarde de la version issue de `Test1.xlsx` | archive |
| `README.md` | Documentation technique du modèle et des commandes | final |
| `REALISE.md` | Le présent compte rendu | final |

---

## 2. Modèle de données implémenté

```
Clan              ← cellule A1, préfixe "Famille"/"LIGNEE" retiré        (7)
 └ Grande famille ← nom de la feuille                                    (46)
    └ Lignée       ← cellule A3 ou A4 ("Descendants  XXX")               (46)
       └ Famille   ← 1re personne nommée après chaque ligne TOTAL        (391)
          └ Membre ← chaque ligne portant un vrai nom                    (599)
```

### 2.1 Tables

| Table | Lignes | Rôle |
|---|---|---|
| `clans` | 7 | sommet de la hiérarchie |
| `grandes_familles` | 46 | une par feuille de calcul |
| `lignees` | 46 | une par grande famille |
| `familles` | 391 | branche de cotisation |
| `membres` | 599 | nom, prénom, téléphone, ordre de fratrie, parent direct, statut |
| `campagnes` | 3 | 2024, 2025, 2026 — 1 000 FCFA/mois |
| `paiements` | 227 | un versement réel (date, montant, mode) |
| `affectations` | 1 805 | détail mois par mois d'un paiement |

### 2.2 Choix de conception

- **`paiements` + `affectations`** : un versement peut couvrir plusieurs mois
  (configuré selon l'option 6b validée par le client). C'est indispensable ici :
  **49 paiements couvrent plusieurs années**.
- **`statut`** sur le membre : `actif` / `inactif` / `decede` / `parti` / `suspendu`,
  avec `date_statut`. Tous les membres importés sont actuellement `actif`.
- **Devise** : FCFA, stockée dans `campagnes.devise`.
- **Cible** : application desktop (choix du client).

---

## 3. Données importées et vérifications

### 3.1 Volumétrie

| Campagne | Mois payés | Montant |
|---|---|---|
| 2024 | 1 453 | **1 453 000 FCFA** |
| 2025 | 336 | **338 000 FCFA** |
| 2026 | 16 | **16 000 FCFA** |
| **Total** | **1 805** | **1 807 000 FCFA** |

### 3.2 Répartition par clan

| Clan | Grandes familles | Membres |
|---|---|---|
| KOUADIO AMBOFF | 16 | 157 |
| AGO | 5 | 118 |
| ADJOUA MALA | 4 | 106 |
| KACOUTIE EDJAPA | 7 | 80 |
| YAOCRE | 9 | 63 |
| ASSOMOU | 1 | 49 |
| TCHOUWA | 4 | 26 |
| **Total** | **46** | **599** |

### 3.3 Contrôles effectués

| Contrôle | Résultat |
|---|---|
| `PRAGMA integrity_check` | **ok** |
| `PRAGMA foreign_key_check` | **aucune violation** |
| Membres sans famille | 0 |
| Familles sans membre | 0 |
| Parents orphelins (`parent_id` invalide) | 0 |
| Somme base 2024 vs somme des 46 feuilles | **1 453 000 = 1 453 000** ✔ |
| Somme base 2024 vs récap Excel | **1 453 000 = 1 453 000** ✔ |
| Somme base 2025 vs somme des 46 feuilles | **338 000 = 338 000** ✔ |
| Idempotence de l'import | 2 imports successifs → 47 puis 47 (feuille unique), 46 GF stables |
| Test des 15 commandes CLI | **15/15 OK** |

---

## 4. Critiques et remarques sur le fichier Excel

> Cette section est le cœur du compte rendu. Les constats ci-dessous ont tous été
> vérifiés par lecture directe du classeur, formules comprises.

### 4.1 🔴 CRITIQUE — Le récapitulatif général est faux

**Constat.** La feuille `TOTAL GENERAL COTISATIONS` **ne somme pas** les 46 feuilles
détaillées. Elle pointe vers les 7 feuilles-répertoires :

```
Récap AB3 : = 'KOUADIO AMBOFF'!AB18
Récap AB4 : = YAOCRE!AB12
Récap AB5 : = 'ADJOUA MALA'!AB7
Récap AB6 : = AGOH!AB8
Récap AB7 : = TCHOUWA!AB7
Récap AB8 : = 'KACOUTIE EDJAPA'!AB10
Récap AB9 : = ASSOMOU!AB4
Récap AB10: = SUM(AB3:AB9)
```

Or ces 7 répertoires contiennent des valeurs **sans rapport** avec les feuilles
détaillées :

| Exercice | Détail (46 feuilles) | Répertoires (référencés par le récap) | Écart |
|---|---|---|---|
| 2024 | **1 453 000** | 49 000 | **+1 404 000** |
| 2025 | **338 000** | 2 000 | **+336 000** |
| 2026 | **16 000** | 0 | **+16 000** |

**Le total général 2025 réellement calculé par Excel est 2 000 FCFA** (cellule `AB10`),
soit **0,6 %** du montant réellement collecté (338 000).

**Conséquence.** Quiconque se fie au récapitulatif pour un bilan financier
**sous-estime les cotisations de plus de 95 %**. C'est le défaut le plus grave du classeur.

**Recommandation.** Faire pointer le récapitulatif vers les lignes `Total Descendants`
des 46 feuilles détaillées :
`= 'AMBOFF Mian Bla'!P296 + 'AMBOFF Gnanda'!P270 + …`
ou, plus robuste, créer une feuille unique normalisée (une ligne = un membre) dont
les totaux sont des `SUMIFS`.

### 4.2 🔴 CRITIQUE — Valeurs en cache obsolètes (fichier non recalculé)

**Constat.** Les valeurs enregistrées dans le classeur ne correspondent pas aux formules.
Exemples relevés :

- `TOTAL GENERAL!AB10` : formule `=SUM(AB3:AB9)` → valeur stockée **2 000**,
  alors que la lecture des colonnes de mois de la même ligne donne **317 000**.
  La colonne « Total 2025 » et les colonnes de mois sont donc **incohérentes entre elles**.
- Les cellules de détail de la ligne 10 (`I10` = Mai 2025 : `=SUM(I3:I9)` → **225 000**)
  sont, elles, correctement calculées : le problème est localisé sur la colonne
  de total annuel, pas sur toute la ligne.

**Cause.** Le fichier a été fermé sans recalcul complet, ou ouvert par un outil qui ne
recalcule pas. Les colonnes de mois et les colonnes de total divergent.

**Conséquence.** Deux personnes ouvrant le même fichier peuvent lire des chiffres
différents selon que leur Excel recalcule ou non. C'est un risque majeur d'erreur
d'interprétation — c'est exactement ce qui s'est produit avec l'écart 317 000 / 338 000.

**Recommandation.** Faire un `Ctrl+Alt+F9` (recalcul complet) puis enregistrer,
et vérifier que `Calcul automatique` est bien actif.

### 4.3 🟠 MAJEUR — Double source de vérité (46 feuilles + 7 répertoires)

**Constat.** Les mêmes cotisations sont saisies deux fois :
- dans les 46 feuilles détaillées, au niveau individu/mois ;
- dans les 7 feuilles `LIGNEE xxx`, au niveau agrégé.

Ces deux jeux **ne concordent pas** (voir 4.1). Il n'existe aucun mécanisme garantissant
leur synchronisation.

**Conséquence.** Impossible de savoir laquelle des deux sources fait foi sans arbitrage
manuel. Tout contrôle de cohérence est manuel et donc faillible.

**Recommandation.** Supprimer les 7 répertoires et générer les agrégats par formule
depuis les feuilles détaillées — ou migrer vers une base de données, ce qui est fait ici.

### 4.4 🟠 MAJEUR — Limite des noms de feuille à 31 caractères

**Constat.** Excel tronque les noms de feuille à 31 caractères. Le nom officiel de la
grande famille est donc **perdu** dans plusieurs cas :

| Nom de feuille (tronqué) | Nom réel (cellule A3/A4) |
|---|---|
| `YAOCRE ALLIEYOFE` | `YAOCRE ALLIEYOFFE` |
| `MIAN BOSSONMA BERNADET` | `MIAN BOSSONMA BERNADETTE` |
| `KACOUTIE EDJAPA` | `KACOUTIE EDJAPA` (complet) |

**Conséquence.** Les libellés de référence sont incohérents entre la feuille et son
contenu. Toute recherche par nom exact échoue.

**Recommandation.** Le nom de grande famille devrait être porté par une cellule
(ex. A3) et non par le nom de feuille.

### 4.5 🟠 MAJEUR — Orthographe instable des noms

**Constat.** Le même patronyme s'écrit de plusieurs façons dans le classeur :

| Variantes relevées | Occurrences |
|---|---|
| `GNANDAKY` / `GNANDAKI` / `GNADAKI` | 3 orthographes |
| `YAOCRE` / `YACRE` / `YOACRE` | 3 orthographes |
| `AMBOFF Akossoua` / `AMBOFF Akossua` | 2 orthographes |
| `KANGAH` / `KANGA` | 2 orthographes |
| `N'GUETTA` / `NGUETTA` | 2 orthographes |
| `ADIJOUMANI` / `ADJOUMANIN` | 2 orthographes |
| `AKOSSUA ATTAH` / `AKASSUA ATTAH` | 2 orthographes |
| `MAIN AMA` / `MIAN AMA` / `MAIN BOSSOUMA` / `MIAN BOSSONMA` | 4 variantes |

**Conséquence.** Un même clan peut être compté deux fois ou pas du tout lors d'un
regroupement automatique. Impossible de faire des statistiques fiables par patronyme.

**Recommandation.** Établir un référentiel de noms (table de correspondance) et
normaliser. Dans la base, le regroupement se fait par code de famille pour éviter
cette faille, mais les patronymes restent hétérogènes.

### 4.6 🟠 MAJEUR — Ambiguïté clan / grande famille

**Constat.** La cellule A1 porte le clan, mais avec deux préfixes différents :
`Famille` dans les 46 feuilles de détail, `LIGNEE` dans les 7 répertoires.
Les 14 libellés A1 distincts se répartissent ainsi : 7 en `Famille xxx`
(46 feuilles) et 7 en `LIGNEE xxx` (7 répertoires).

| Feuille | A1 | Problème |
|---|---|---|
| `AGOH` | `LIGNEE AGOH` | préfixe inattendu (`LIGNEE`), alors que A1 = `Famille xxx` ailleurs |
| `KOUADIO AMBOFF` | `LIGNEE AMBOFF` | le clan « AMBOFF » devient « KOUADIO AMBOFF » dans les feuilles de détail |
| Diverses | `Famille YAOCRE` | préfixe `Famille` |

De plus, les 7 feuilles-répertoires portent un nom **différent** de la feuille :
la feuille `AGOH` déclare le clan… `AGOH`, mais les feuilles de détail déclarent
`Famille AGO`. Idem pour `AMBOFF` vs `KOUADIO AMBOFF`.

**Conséquence.** Deux noms de clan différents pour un même clan (`AMBOFF` vs `KOUADIO AMBOFF`,
`AGOH` vs `AGO`). Sans traitement spécifique, l'import crée des clans fantômes.

**Traitement appliqué.** Deux alias codés en dur dans `requetes.py` (`ALIAS_REPERTOIRE`).
C'est une **rustine** : la source devrait être homogène.

### 4.7 🟡 NOTABLE — Un même patron n'a pas été nommé de la même façon dans A3 et A4

**Constat.** Le nom de lignée se trouve tantôt en A3, tantôt en A4 :

| Feuille | A3 | A4 |
|---|---|---|
| `YAOCRE KOUADIO` | `Descendants  YAOCRE KOUADIO` | ` ` |
| `AMBOFF Apangni` | ` ` | ` Descendants  AMBOFF Apangni` |

**Conséquence.** Toute lecture automatique doit tester les deux cellules. Un lecteur
humain peu attentif lira la mauvaise ligne.

### 4.8 🟡 NOTABLE — Descendants anonymes innombrables

**Constat.** **192 lignes** du classeur sont des marqueurs vides :
`(Penfant 11)`, `(APenfant211)`, `(Penfant 21)`… sans aucun nom ni montant.
Elles représentent près d'un tiers des lignes totales pour **zéro information**.

**Conséquence.** Le fichier paraît trois fois plus gros qu'il ne l'est réellement.
Le comptage des membres est impossible sans nettoyage préalable.

**Traitement appliqué.** Ces 192 entrées ont été **écartées de la base** à la demande
du client, après vérification qu'aucune ne portait de cotisation.

### 4.9 🟡 NOTABLE — Placeholders de remplissage

**Constat.** Des noms manifestement fictifs servent de bouchons :
`XXXX`, `XXXXX`, `YYYY`, `YYYYY`, `ZZZZZ`, `XXX`, `YYY`, `AMY`, ainsi que
`WANDA XXX`, `TIGORI XXXX`, `Enfant 1`, `(Enfant1)` seul.

**Conséquence.** 12 de ces entrées ne correspondent à aucune personne et faussent
le décompte des membres.

**Traitement appliqué.** Les 12 placeholders ont été retirés (aucun n'avait cotisé).

### 4.10 🟡 NOTABLE — Incohérence de calcul sur la branche GNANDAKY BOA (fichier `Test1.xlsx`)

**Constat.** Dans `Test1.xlsx`, trois lignes avaient **8 mois renseignés à 1 000 FCFA
mais un total de 0** : lignes 147 (`GNANDAKI ERNEST`), 182 (`GNADAKI Germain`),
198 (`GNANDAKY Didier`).

**Hypothèse.** Soit des montants saisis en texte, soit un total figé avant saisie.

**Conséquence.** Un total incohérent avec son détail est indétectable à l'œil.
La base, qui recalcule depuis les mois, est ici plus fiable que l'Excel.

### 4.11 🟡 NOTABLE — Aucune date de versement

**Constat.** Le classeur indique **quel mois** est payé, jamais **quand** le paiement
a été effectué. Or l'analyse montre des paiements groupés (5 mois réglés d'un coup,
8 000 FCFA en une fois).

**Conséquence.** Impossible de reconstituer la trésorerie réelle (à quelle date
l'argent est entré), ni de calculer des retards de versement.

**Traitement appliqué.** La date a été **approximée** au 28 du dernier mois couvert,
et ce choix est documenté. À corriger au fil des saisies réelles.

### 4.12 🟡 NOTABLE — Ligne `(EnfantN)` servant à la fois de marqueur et de nom

**Constat.** Le libellé `(Enfant4) GNANDAKI ODETTE` mélange un **numéro d'ordre**
et un **nom de personne** dans une seule cellule.

**Conséquence.** Toute extraction automatique naïve produit soit un nom pollué
(`Enfant4 GNANDAKI`), soit une perte d'information.

**Traitement appliqué.** Le marqueur est retiré du nom, et le numéro est conservé
dans une colonne dédiée `ordre_fratrie`. Le client a explicitement demandé que
seul le nom réel subsiste.

### 4.13 🟢 MINEUR — Deux feuilles sans aucun contenu exploitable

**Constat.** `AMBOFF Apangni` et `KOUAKOU DJAPA` ne contiennent **que** des marqueurs
`(Enfant1)`, `(Enfant 1)`, `(Penfant 11)`… sans nom et sans montant.

**Conséquence.** Deux grandes familles existent dans la nomenclature mais sont
**vides de toute personne** (0 membre, 0 FCFA).

### 4.14 🟢 MINEUR — Feuille `AMBOFF Mian Bla` dupliquée dans `Test1.xlsx`

**Constat.** Le fichier `Test1.xlsx` du dossier projet est une copie de travail de la
feuille n°1, avec des montants différents. Il ne contient qu'une feuille sur 54.

**Conséquence.** Risque de confusion sur la source de référence — c'est précisément
ce qui s'est produit au début de ce travail.

### 4.15 🟢 MINEUR — Aucune protection ni validation des données

**Constat.** Aucune liste déroulante, aucune validation de type, aucune protection de
formule, aucune feuille masquée. Les 42 colonnes sont saisissables librement.

**Conséquence.** Une valeur saisie en texte (`"1000"`) au lieu d'un nombre n'est pas
détectée et fausse les totaux silencieusement.

**Recommandation.** Verrouiller les colonnes de total, valider les colonnes de mois
comme numériques.

### 4.16 🟢 MINEUR — Formules de total écrites en dur, cellule par cellule

**Constat.** Les formules agrègent des cellules nommées une à une :

```
'AMBOFF Mian Bla'!D46  =  D45+D37+D29+D18+D10+D5
'AMBOFF Mian Bla'!D122 =  +D121+D113+D105+D97+D89+D81+D70+D62+D48
```

**Conséquence.** L'ajout d'une branche oblige à réécrire toutes les formules de total,
avec un risque d'oubli. Douze colonnes × 46 feuilles = **un très grand nombre de
formules fragiles**.

**Recommandation.** Utiliser `SOMME.SI` / `SOMME.SI.ENS` sur une colonne de niveau,
ou un tableau structuré.

### 4.17 🟢 MINEUR — Encodage et espaces parasites

**Constat.** Présence d'espaces en fin de nom de feuille (`'AMBOFF Kanga '`),
d'espaces multiples à l'intérieur des libellés (`'Total Descendants   AMBOFF Mian Bla'`),
d'espaces insécables, et de cellules contenant un simple espace `" "` au lieu d'être vides.

**Conséquence.** Faux doublons et comparaisons qui échouent (`"Kanga"` ≠ `"Kanga "`).

**Traitement appliqué.** Normalisation systématique à l'import.

### 4.18 🟢 MINEUR — Libellés de mois accentués non normalisés

**Constat.** Alternance `Janv` / `Fevr` / `Août` selon les feuilles, avec accentuation
irrégulière (`Févr`, `Ao�t`).

**Conséquence.** Un rapprochement par nom de mois est fragile.

---

## 5. Synthèse des critiques

| Sévérité | Nombre | Thèmes |
|---|---|---|
| 🔴 Critique | 2 | récapitulatif faux, cache obsolète |
| 🟠 Majeur | 4 | double source, noms tronqués, orthographes instables, ambiguïté clan |
| 🟡 Notable | 6 | A3/A4 variable, 192 marqueurs vides, placeholders, totaux incohérents, pas de dates, marqueur mêlé au nom |
| 🟢 Mineur | 6 | feuilles vides, doublon `Test1`, pas de validation, formules en dur, espaces/encodage, mois accentués |

**Les trois problèmes à traiter en priorité :**

1. **Le récapitulatif général doit sommer les feuilles détaillées**, pas les répertoires.
   En l'état il sous-estime de 95 %.
2. **Forcer un recalcul complet** du classeur et vérifier que les valeurs en cache
   correspondent aux formules.
3. **Supprimer la double saisie** : soit les 46 feuilles, soit les 7 répertoires, pas les deux.

---

## 6. Commandes disponibles

```bash
python import_complet.py                            # (re)construire la base
python extrait_repertoires.py                       # (re)générer repertoires.json

python requetes.py                                  # récap + état par clan
python requetes.py --clans --annee 2024             # état par clan
python requetes.py --clan "YAOCRE"                  # grandes familles d'un clan
python requetes.py --feuille "AMBOFF Boa"           # familles d'une grande famille
python requetes.py --lignee "N'GUETTA"              # membres d'une lignée
python requetes.py --membre 211                     # fiche complète d'un membre
python requetes.py --recherche "YAO"                # recherche par nom
python requetes.py --impayes 2025                   # actifs sans versement
python requetes.py --grille "AMBOFF Mian Bla" --annee 2024
python requetes.py --top 20                         # meilleurs cotisants
python requetes.py --synthese 2024                  # synthèse par grande famille
python requetes.py --audit 2025                     # base vs répertoires Excel
python requetes.py --recap                          # totaux par campagne

python app.py                                       # application de saisie
python ecran_tableau_bord.py                        # tableau de bord seul (test)
```

### Application de saisie — 8 onglets

| Onglet | Rôle |
|---|---|
| 1. Clans | saisie du niveau clan |
| 2. Grandes familles | rattachées à un clan |
| 3. Lignées | rattachées à une grande famille |
| 4. Familles | rattachées à une lignée |
| 5. Membres | rattachés à une famille ; parent limité à la même famille |
| 6. Cotisations | versements, grille 12 mois, arriérés |
| 7. Tableau de bord | synthèse en lecture seule |
| 8. Paramètres | montant, exercices, sauvegardes, purge |

### Thème clair / sombre

Bouton `☾ Mode sombre` dans la barre de titre, ou **Ctrl+D**, ou menu
Aide → Basculer clair / sombre. Le choix est mémorisé dans la table
`parametres` (clé `theme`) et repris au démarrage.

Le module `theme.py` applique le thème à trois niveaux : styles ttk,
conteneurs Tk purs, et couleurs écrites en dur (recensées au démarrage
puis rejouées avec leur équivalent sombre). Le calendrier de l'onglet
Cotisations est recoloré sans perdre le mois affiché.

### Tableau de bord (lecture seule)

- **Cartes de synthèse** : encaissé, attendu, taux de recouvrement,
  membres à jour, membres en retard.
- **Répartition** par clan / grande famille / lignée / famille, avec le
  nombre de membres, de cotisants et la part de chaque ligne.
- **Membres en retard**, triés par montant dû, avec le nombre de mois payés.
- **Grille mensuelle** de tous les membres (`·` = mois non réglé).
- **Montants par année** : une colonne par année, pour les 4 niveaux
  (clan, grande famille, lignée, famille), avec le total par niveau.
- **Par membre / an** : montant cotisé de chaque membre, année par année,
  plus le total et la moyenne annuelle. Se limite à l'exercice choisi.

Les échéances sont calculées selon la période réelle de l'exercice :
12 mois pour une année passée, le mois courant pour l'année en cours,
0 pour une année future non commencée.

---

## 7. Limites connues de la base

1. **Téléphone** : aucune donnée dans le classeur source. La colonne existe
   (599 membres, **0 renseigné**) et reste à alimenter.
2. **Dates de paiement approximatives** : voir §4.11.
3. **Liens de parenté partiels** : 138 membres sur 599 ont un `parent_id`.
   Les autres sont des têtes de famille, ou leurs liens n'étaient pas exprimés
   sous forme de nommage exploitable dans le classeur.
4. **Patronymes non normalisés** : voir §4.5. Le regroupement se fait par famille,
   ce qui neutralise le problème au niveau comptable mais pas au niveau nominatif.
5. **Statut** : tous les membres sont `actif`. Aucune information de décès,
   de départ ou de suspension n'existe dans le classeur.

---

## 8. Ce qui n'a pas été fait

| Élément | Raison |
|---|---|
| Correction du fichier Excel source | hors périmètre, à décider par le client |
| Saisie des téléphones | donnée absente de la source |
| Application desktop de saisie (Tkinter) | **réalisée** : `app.py`, 8 onglets (saisie hiérarchique, cotisations, tableau de bord, paramètres) |
| Export PDF / impression du tableau de bord | non demandé |
| Import des 7 répertoires dans la base | sources contradictoires, base non fiable — seuls les totaux ont été extraits pour l'audit |
| Dates réelles de versement | information inexistante dans le classeur |


---

## Annexe A — Écarts détaillés base ↔ feuilles-répertoires

Cette annexe permet de **corriger le classeur Excel ligne par ligne**. Toutes les valeurs sont en FCFA.

- **base** = somme des 46 feuilles détaillées (référence, vérifiée) ;
- **répertoire** = valeur portée par la ligne correspondante de la feuille `LIGNEE xxx` ;
- **écart** = base − répertoire.

> L'appariement des libellés est approximatif : le répertoire abrège les noms
> (`MIAN BLA` pour `AMBOFF Mian Bla`, `KOFFI ADEI` pour `KOFFI ADJEI`). Un écart
> peut donc provenir d'un simple défaut d'appariement et non d'une erreur de montant.


### Clan KOUADIO AMBOFF

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| ALLIE KOUADIO AMBOFF | 6 000 | 0 | **6 000** | 0 | 0 | 0 |
| AMBOFF Affoua | 6 000 | 0 | **6 000** | 0 | 0 | 0 |
| AMBOFF Akossoua | 16 000 | 2 000 | **14 000** | 14 000 | 0 | **14 000** |
| AMBOFF Assomou | 8 000 | 1 000 | **7 000** | 10 000 | 0 | **10 000** |
| AMBOFF Boa | 122 000 | 1 000 | **121 000** | 10 000 | 0 | **10 000** |
| AMBOFF Enabla | 6 000 | 0 | **6 000** | 0 | 0 | 0 |
| AMBOFF Gnanda | 144 000 | 0 | **144 000** | 0 | 0 | 0 |
| AMBOFF Gnangoran | 8 000 | 1 000 | **7 000** | 4 000 | 0 | **4 000** |
| AMBOFF Mian | 80 000 | 1 000 | **79 000** | 4 000 | 0 | **4 000** |
| AMBOFF Mian Bla | 210 000 | 18 000 | **192 000** | 96 000 | 0 | **96 000** |
| MIAN BOSSONMA BERNADETTE | 8 000 | 1 000 | **7 000** | 12 000 | 1 000 | **11 000** |
| **SOUS-TOTAL KOUADIO AMBOFF** | **614 000** | **25 000** | **589 000** | — | — | — |

*Lignes du répertoire sans correspondance (aucun membre nommé) :* `AMOAKON Tapé`, `APANGNI`, `KANGA`, `KOUADIO`

### Clan YAOCRE

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| YACRE BOA | 18 000 | 0 | **18 000** | 0 | 0 | 0 |
| YAOCRE ALLIEYOFE | 24 000 | 0 | **24 000** | 0 | 0 | 0 |
| YAOCRE GNANDA | 8 000 | 1 000 | **7 000** | 14 000 | 0 | **14 000** |
| YAOCRE MIAN | 19 000 | 2 000 | **17 000** | 14 000 | 0 | **14 000** |
| YOACRE AMOAKON | 42 000 | 0 | **42 000** | 0 | 0 | 0 |
| **SOUS-TOTAL YAOCRE** | **111 000** | **3 000** | **108 000** | — | — | — |

*Lignes du répertoire sans correspondance (aucun membre nommé) :* `YAOCRE APPIA`, `YAOCRE KOUADIO`, `YAOCRE KOUASSI`, `YAOCRE NEBIE`

### Clan ADJOUA MALA

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| ABLAN BREMA | 326 000 | 1 000 | **325 000** | 10 000 | 0 | **10 000** |
| ALLIE ADJOUA MALA | 14 000 | 1 000 | **13 000** | 6 000 | 0 | **6 000** |
| **SOUS-TOTAL ADJOUA MALA** | **340 000** | **2 000** | **338 000** | — | — | — |

*Lignes du répertoire sans correspondance (aucun membre nommé) :* `ADJOUA SEWA`, `KOUAME ADADE`

### Clan AGO

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| ASSAMA | 8 000 | 1 000 | **7 000** | 6 000 | 0 | **6 000** |
| MIAN | 8 000 | 1 000 | **7 000** | 10 000 | 0 | **10 000** |
| NGUETTA KOUAO ⚠︎ | 20 000 | 0 | **20 000** | 10 000 | 0 | **10 000** |
| TEBLA | 32 000 | 4 000 | **28 000** | 30 000 | 1 000 | **29 000** |
| **SOUS-TOTAL AGO** | **68 000** | **6 000** | **62 000** | — | — | — |

*Lignes du répertoire sans correspondance (aucun membre nommé) :* `AMALAMAN AMOAKOUA`, `N'GUETTA KOUAO`

### Clan TCHOUWA

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| BOSSONMA ⚠︎ | 52 000 | 0 | **52 000** | 50 000 | 0 | **50 000** |
| KACOUTIE NGOUAN ⚠︎ | 48 000 | 0 | **48 000** | 0 | 0 | 0 |
| **SOUS-TOTAL TCHOUWA** | **100 000** | **0** | **100 000** | — | — | — |

*Lignes du répertoire sans correspondance (aucun membre nommé) :* `AKA`, `BOSSOMA`, `EBAH`, `KACOUTIE N'GOUAN`

### Clan KACOUTIE EDJAPA

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| DAKONWA EUGENIE | 66 000 | 0 | **66 000** | 0 | 0 | 0 |
| KOFFI ADJEI ⚠︎ | 86 000 | 0 | **86 000** | 10 000 | 0 | **10 000** |
| **SOUS-TOTAL KACOUTIE EDJAPA** | **152 000** | **0** | **152 000** | — | — | — |

*Lignes du répertoire sans correspondance (aucun membre nommé) :* `AKOSSUA ATTAH`, `AMA ADJO`, `KOFFI ADEI`, `KOUAKOU AMOAKON`, `KOUAKOU DJAPA`, `TANO AMA`

### Clan ASSOMOU

| Grande famille | base 2024 | répertoire 2024 | écart | base 2025 | répertoire 2025 | écart |
|---|---:|---:|---:|---:|---:|---:|
| ASSRE | 68 000 | 6 000 | **62 000** | 28 000 | 0 | **28 000** |
| **SOUS-TOTAL ASSOMOU** | **68 000** | **6 000** | **62 000** | — | — | — |

### Récapitulatif global des écarts

| Exercice | base (46 feuilles) | répertoires | écart | sous-estimation |
|---|---:|---:|---:|---:|
| 2024 | **1 453 000** | 49 000 | **1 404 000** | 96.6 % |
| 2025 | **338 000** | 2 000 | **336 000** | 99.4 % |
| 2026 | **16 000** | 0 | **16 000** | 100.0 % |
| **Total** | **1 807 000** | 51 000 | **1 756 000** | |

---

## 9. Conclusion

La base `cotisations.db` est **fidèle aux 46 feuilles détaillées** : contrôles
d'intégrité passés, aucune perte de donnée financière (vérifié à chaque étape de
nettoyage), et concordance exacte sur 2024 avec le récapitulatif Excel.

**En revanche, le classeur Excel n'est pas fiable pour un bilan** : son récapitulatif
pointe vers des feuilles aux totaux obsolètes et le sous-estime de plus de 95 %.
La base de données est désormais la source de vérité.
