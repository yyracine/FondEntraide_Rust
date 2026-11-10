# Guide d'utilisation — Fonds d'Entraide

Application de gestion des cotisations familiales du Fonds d'Entraide.

---

## Sommaire

1. [Démarrer l'application](#1-démarrer-lapplication)
2. [La hiérarchie : comprendre l'organisation](#2-la-hiérarchie-comprendre-lorganisation)
3. [Les 8 onglets](#3-les-8-onglets)
4. [Saisir les clans, grandes familles, lignées, familles, membres](#4-saisir-la-hiérarchie)
5. [Encaisser une cotisation](#5-encaisser-une-cotisation)
6. [Éditer un reçu](#6-éditer-un-reçu)
7. [Le tableau de bord](#7-le-tableau-de-bord)
8. [Exporter en CSV et en PDF](#8-exporter-en-csv-et-en-pdf)
9. [Les paramètres](#9-les-paramètres)
10. [Tester sans risque : le mode démo](#10-tester-sans-risque-le-mode-démo)
11. [Les outils en ligne de commande](#11-les-outils-en-ligne-de-commande)
12. [Questions fréquentes et dépannage](#12-questions-fréquentes-et-dépannage)

---

## 1. Démarrer l'application

### Installation

Python 3.10 ou plus récent est nécessaire.

```bash
pip install -r requirements.txt
```

Deux dépendances, **toutes deux facultatives** :

| Bibliothèque | Apport | Sans elle |
|---|---|---|
| `tkcalendar` | calendrier de choix de date | champ texte `JJ/MM/AAAA` |
| `reportlab` | rendu PDF plus fin | PDF quand même produit (moteur interne) |

### Lancement

```bash
python app.py
```

La fenêtre s'ouvre en **thème sombre**. Pour basculer : bouton **☾ / ☀** en haut à
droite, ou **Ctrl+D**, ou le menu **Aide → Basculer clair / sombre**. Le choix est
mémorisé.

`Ctrl+D` fonctionne partout dans l'application.

---

## 2. La hiérarchie : comprendre l'organisation

L'application range les personnes en **cinq niveaux emboîtés** :

```
Clan                       (le sommet, ex. « ADJOUA SEWA »)
 └── Grande famille        (ex. « ADJOUA SEWA »)
      └── Lignée           (la souche, ex. « ADJOUA SEWA »)
           └── Famille     (ex. « TANO Ama »)
                └── Membre (ex. « APPIA / SEWA »)
```

Chaque niveau a **exactement un parent** du niveau supérieur, sauf le clan qui est
à la racine. Les 5 premiers onglets suivent cet ordre : on ne peut pas créer une
famille sans lignée, ni un membre sans famille.

### Règles garanties par la base de données

- Un **membre** appartient à **une seule famille**.
- Le **parent d'un membre** (facultatif) doit appartenir à **la même famille**.
- Un membre **ne peut pas être son propre ancêtre** (pas de cycle).
- On ne peut pas **supprimer un membre** qui a des enfants ou des paiements.
- On ne peut pas **supprimer une famille/lignée/…** encore occupée.

Ces règles sont appliquées côté base, pas seulement par l'interface : impossible
de les contourner par erreur.

---

## 3. Les 8 onglets

| # | Onglet | À quoi ça sert |
|---|---|---|
| 1 | **Clans** | créer et gérer les clans |
| 2 | **Grandes familles** | les grandes familles, rattachées à un clan |
| 3 | **Lignées** | les lignées, rattachées à une grande famille |
| 4 | **Familles** | les familles, rattachées à une lignée |
| 5 | **Membres** | les personnes, rattachées à une famille |
| 6 | **Cotisations** | encaisser les versements, éditer les reçus |
| 7 | **Tableau de bord** | chiffres clés, répartitions, retards, exports |
| 8 | **Paramètres** | montant de la cotisation, exercices, sauvegardes |

Chaque onglet de 1 à 5 a un bouton **« Liste en PDF… »** qui exporte exactement ce
qui est affiché (voir [section 8](#8-exporter-en-csv-et-en-pdf)).

---

## 4. Saisir la hiérarchie

Les onglets 1 à 5 se ressemblent : une **liste** en haut, une **fiche** à droite.

### Les quatre boutons de la fiche

| Bouton | Effet |
|---|---|
| **Nouveau** | vide la fiche pour créer un élément |
| **Modifier** | reprend l'élément sélectionné pour le changer |
| **Enregistrer** | valide la saisie |
| **Supprimer** | retire l'élément (confirmation demandée) |

> **Point important :** le bouton « Enregistrer » n'écrit que si vous avez
> d'abord cliqué sur **Nouveau** ou **Modifier**. Sinon l'application répond
> « Rien à enregistrer ». C'est voulu : cela évite les modifications
> accidentelles.

### Le filtre parent

En haut de chaque liste, un filtre limite l'affichage aux enfants d'un parent :

- Onglet 2 : filtre par **clan**
- Onglet 3 : filtre par **grande famille**
- Onglet 4 : filtre par **lignée**
- Onglet 5 : filtre par **famille**

Le bouton **« Tous »** retire le filtre. Le bouton **« Liste en PDF… »** respecte
le filtre : si vous filtrez sur un clan, le PDF ne contient que ses grandes
familles.

### Champs d'un membre

| Champ | Obligatoire | Remarque |
|---|---|---|
| Nom | oui | — |
| Prénom | non | — |
| Téléphone | non | refusé s'il contient des lettres |
| Fratrie (1 = aîné) | non | sert au **tri** de la liste (aînés en premier) |
| Parent | non | limité aux membres de la **même famille** |
| Sexe | non | — |
| Statut | oui | `actif`, `inactif`, `decede`, `parti`, `suspendu` |
| Notes | non | texte libre |

La liste des membres affiche : **Famille (parent) · Nom · Prénom · Téléphone ·
Grande famille · Parent · Statut**.

> Seuls les membres au statut **`actif`** entrent dans les calculs du tableau de
> bord et des retards.

---

## 5. Encaisser une cotisation

Onglet **6. Cotisations**. L'écran est coupé en trois zones :

```
┌─ Sélection ───────────────────────────────────────────────┐
│ Année [2026]  Clan [—]  Grande famille [—]  Lignée [—]     │
│ Famille [—]                              [Tout afficher]   │
└────────────────────────────────────────────────────────────┘
┌─ Membres ───────────────┐  ┌─ Cotisation du membre ──────┐
│ Membre │ Famille │ Mois  │  │ fiche + mois + montant      │
│        │         │ Versé │  │ + versements enregistrés    │
└─────────────────────────┘  └─────────────────────────────┘
```

### Pas à pas

1. **Choisissez l'exercice** dans la liste **« Année »**, en haut à **gauche** du
   bloc Sélection. Vous pouvez aussi **taper une année** (2028, 2031…) : le champ
   accepte la saisie libre. Validez par Entrée ou en quittant le champ.
2. **Restreignez la liste** si besoin avec les quatre filtres en cascade :
   **Clan → Grande famille → Lignée → Famille**. Chaque choix affine le suivant.
   Le bouton **« Tout afficher »** remet tous les filtres à zéro.
3. **Cliquez sur le membre** dans la liste de gauche. La liste affiche quatre
   colonnes : **Membre · Famille · Mois payés · Versé**.
4. **Cochez les mois** réglés.
   - Boutons rapides : **Tous** (les 12), **Aucun**, **1er trim.** (janvier à
     mars), **Impayés** (uniquement les mois non réglés et déjà échus).
   - Un mois **déjà réglé** est refusé :
     « Janvier : déjà réglé(s) pour ce membre. Décochez-les ou corrigez le
     versement existant. »
   - Un mois **pas encore échu** est refusé :
     « Ces mois ne sont pas encore échus pour 2026 : Décembre. Seuls les 11
     premiers mois peuvent être réglés. »
5. **Le montant se remplit tout seul** : cotisation mensuelle × nombre de mois
   cochés. Vous pouvez le **corriger à la main** si le versement diffère (arrondi,
   geste commercial…).
6. Vérifiez la **date** au format `JJ/MM/AAAA`. Trois aides :
   - bouton **« Aujourd'hui »** pour revenir à la date du jour ;
   - le **calendrier** juste en dessous ;
   - une date incohérente est refusée :
     « Saisissez la date au format JJ/MM/AAAA (ex. 31/12/2025) ou
     choisissez-la dans le calendrier. »
7. Choisissez le **mode** : Espèces, Mobile Money, Virement, Chèque, Autre.
8. Cliquez sur **« Enregistrer le versement »**.

La barre d'état confirme :
« Versement enregistré : 3 mois (Mai,Juin,Juillet) pour MAIN BOSSOUMA. »

Une **question** s'affiche alors : « Éditer le reçu de ce paiement (aperçu PDF
puis impression) ? » → voir la [section 6](#6-éditer-un-reçu).

### Le panneau de situation

À droite, au-dessus des mois, il résume l'exercice choisi :

```
Année 2026 · cotisation 1000 FCFA/mois
Payés : 4/11 · Versé : 4000 FCFA
Attendu : 11000 · Reste : 7000 FCFA
Mois en retard : Mai, Juin, Juillet, Août, Septembre, Octobre, Novembre
```

Si tout est réglé, la dernière ligne devient **« À jour pour cette année. »**

> **Le dénominateur n'est pas toujours 12.** C'est le nombre de **mois échus** :
> 11 en novembre 2026, 12 pour une année passée, et `0/0` pour une année future.
> C'est pour cela qu'un membre peut afficher `0/11` et devoir `11 000 F` — et non
> `12 000 F`.

### Le bandeau des arriérés

En orange, sous la fiche, il signale les impayés des **autres années** :

```
⚠ Arriérés à régler : 2024 : 4 mois · 2025 : 2 mois
Total dû, toutes années confondues : 6000 FCFA.
Choisissez l'année concernée dans la liste « Année » ci-dessus
pour la régulariser.
```

Il indique donc **année par année**, avec le **total cumulé**. Pour régulariser,
changez l'année dans la liste « Année » : la situation et les mois à cocher
suivent l'exercice choisi.

### Les versements enregistrés

En bas à droite, l'historique du membre pour l'exercice choisi, sur quatre
colonnes : **Date · Montant · Mois · Mode**.

### Corriger une erreur

Sélectionnez la ligne du versement dans **« Versements enregistrés »**, puis
cliquez sur **« Supprimer ce versement »**. Le versement et ses mois sont retirés :
les mois redeviennent disponibles.

> La suppression est définitive. En cas de doute, préférez une sauvegarde
> (onglet Paramètres) avant de corriger.

---

## 6. Éditer un reçu

Deux façons d'y arriver :

- **juste après avoir enregistré un versement** : l'application demande
  « Éditer le reçu de ce paiement ? » → répondez **Oui** ;
- à tout moment, dans l'onglet Cotisations : sélectionnez le membre, cliquez sur
  la ligne du versement dans **« Versements enregistrés »**, puis sur
  **« Reçu (aperçu PDF)… »**.

L'aperçu s'ouvre dans votre lecteur PDF, puis l'application propose :

| Réponse | Effet |
|---|---|
| **Oui** | imprime le reçu |
| **Non** | enregistre une copie dans le dossier de votre choix |
| **Annuler** | ferme, ne fait rien |

Le reçu est au format **A4 paysage** et contient le montant **en lettres**
(« Douze mille francs CFA »).

### Numérotation

Chaque reçu porte un numéro stable : **`RECU-<année>-000001`**. Le numéro est
**enregistré en base** au moment de l'édition : rééditer le même versement donne
**le même numéro**, jamais un nouveau. La séquence recommence à `000001` chaque
année.

---

## 7. Le tableau de bord

Onglet **7. Tableau de bord**. En haut : le sélecteur d'**Exercice**, puis
**cinq cartes de synthèse**, puis **cinq sous-onglets** de détail.

À l'ouverture, l'application choisit d'elle-même une année **parlante** : d'abord
une année qui contient des cotisations, sinon l'année courante, sinon la première
disponible. Elle évite ainsi de s'ouvrir sur une année future vide. Dès que vous
choisissez une année, ce choix est respecté.

### Les cinq cartes de synthèse

| Carte | Signification |
|---|---|
| **Encaissé** | total réellement versé sur l'exercice |
| **Attendu** | membres actifs × montant mensuel × **mois échus** |
| **Taux de recouvrement** | encaissé ÷ attendu, en pourcentage |
| **Membres à jour** | rapport `x / N` : x membres ont réglé tous les mois échus, sur N membres actifs |
| **Membres en retard** | combien de membres actifs ont au moins un mois échu non payé |

Exemple réel, exercice **2026** en novembre : `16 000` encaissés pour
`6 589 000` attendus, **0,2 %** de recouvrement, `1 / 599` membres à jour et
`598` en retard — parce que seuls 2 versements 2026 sont saisis à ce jour.

> **« Membres à jour » est un rapport, pas un nombre.** La carte affiche par
> exemple `412 / 599`. Un membre **inactif** (statut `inactif`, `decede`, `parti`,
> `suspendu`) n'entre ni au numérateur ni au dénominateur.

### Les cinq sous-onglets

#### Répartition

Un sélecteur **« Niveau »** propose **quatre** regroupements :
**Clan**, **Grande famille**, **Lignée**, **Famille**.

Cinq colonnes :

| Colonne | Contenu |
|---|---|
| **Libellé** | le nom du clan / de la grande famille / de la lignée / de la famille |
| **Membres** | effectif du groupe |
| **Cotisants** | combien ont versé au moins une fois sur l'exercice |
| **Encaissé (FCFA)** | total versé par le groupe |
| **Part** | part de ce groupe dans l'encaissé total, en pourcentage |

#### Membres en retard

Un bandeau chiffré en haut, puis cinq colonnes :

| Colonne | Contenu |
|---|---|
| **Membre** | nom et prénom |
| **Famille** | famille de rattachement |
| **Clan** | clan de rattachement (rappel du chemin complet) |
| **Mois payés / échus** | par exemple `7 / 11` |
| **Reste dû (FCFA)** | ce qu'il reste à verser pour l'exercice |

Si personne n'est en retard :
**« Aucun membre en retard : tout le monde est à jour. »**

#### Grille mensuelle

Une ligne par membre, et **une colonne par mois** — `Janv`, `Févr`, `Mars`…
`Déc` — suivie d'une colonne **Total**. La case est marquée si le mois est réglé,
vide sinon : les trous se voient d'un coup d'œil.

La grille est large : un **ascenseur horizontal** apparaît sous le tableau.

#### Montants par année

Tableau **groupé par niveau**, avec une ligne de titre `— Clan —`,
`— Grande famille —`, etc., puis une ligne **« Total … »** par groupe.

Colonnes : **Libellé · Membres · une colonne par année · Total**.

Le bandeau du haut rappelle : « Montants en FCFA · années : … ».

#### Par membre / an

Le détail personne par personne. Colonnes :
**Membre · Famille · Clan · une colonne par année · Total · Moyenne/an**.

#### Messages de tableau vide

Chaque sous-onglet a son propre message :

| Situation | Message |
|---|---|
| année future, aucune échéance | « Exercice non commencé : aucune échéance due. » |
| aucun retard | « Aucun membre en retard : tout le monde est à jour. » |
| aucune cotisation | « Aucune cotisation enregistrée pour le moment. » |

### Rafraîchir

Bouton **« Rafraîchir »** : relit la base et recalcule tout. Utile après une
saisie faite dans un autre onglet, ou après une restauration.

> Sur une année **future**, les montants attendus sont à **0** et les cartes
> restent vides : il n'y a pas encore d'échéance due.

---

## 8. Exporter en CSV et en PDF

### Tableau de bord — trois boutons

| Bouton | Format | Contenu |
|---|---|---|
| **Exporter CSV** | `.csv` | données ouvertes dans Excel / LibreOffice |
| **Imprimer PDF** | `.pdf` | envoie directement à l'imprimante |
| **PDF…** | `.pdf` | enregistre le fichier dans un dossier |

À chaque fois, l'application demande l'**étendue** :

- **Oui** = tout le tableau de bord (chiffres clés + les 5 tableaux)
- **Non** = seulement le sous-onglet affiché
- **Annuler** = ne rien faire

Puis elle demande le **dossier**. Le **nom du fichier est imposé** :

```
tableau_de_bord_2026_complet_20261109_1430.pdf
tableau_de_bord_2026_membres_en_retard_20261109_1435.csv
```

Avantage : deux exports ne s'écrasent jamais, et l'origine d'un fichier est
toujours lisible (exercice + portée + horodatage).

Le CSV utilise le point-virgule comme séparateur et l'encodage `utf-8-sig`, donc
il s'ouvre correctement dans un Excel français (accents compris).

### Onglets 1 à 5 — bouton « Liste en PDF… »

Exporte **exactement ce qui est affiché** : mêmes colonnes, mêmes valeurs
formatées, **même filtre parent**.

Le nom est de la forme :

```
liste_membres_20261109_1435.pdf
liste_grandes_families_...pdf
```

Caractéristiques du PDF :

- **orientation automatique** : portrait jusqu'à 4 colonnes, paysage au-delà ;
- largeurs de colonnes calculées d'après le contenu ;
- texte trop long abrégé par « … » ;
- **en-tête répété** à chaque page ;
- **ligne de total** si une colonne numérique existe ;
- pied de page avec date et numéro de page.

---

## 9. Les paramètres

Onglet **8. Paramètres**, en **trois blocs** numérotés. La zone défile : faites
glisser avec la molette.

En haut à droite, un rappel permanent du contenu de la base :
« *599 membre(s) · 391 famille(s) · 227 versement(s)* ».

### 1. Montant de la cotisation

| Champ / bouton | Rôle |
|---|---|
| **Montant mensuel par membre** | en FCFA |
| **Année concernée** | liste « Toutes les années » par défaut ; **vous pouvez taper une année** (2024, 2028…) |
| **Appliquer** | enregistre le montant |
| **Appliquer aussi aux campagnes déjà créées** | case à cocher |

Par défaut, le montant s'applique aux **nouvelles** années. Une année **déjà
cotisée** garde son montant, sauf si vous cochez la case : là le montant est
réécrit **rétroactivement**, y compris sur les versements passés.

Un texte d'aide sous le bloc explique lequel des deux cas s'applique, selon que
des exercices existent ou non.

#### « Exercices ouverts »

Tableau des exercices configurés, sur **cinq colonnes** :

| Colonne | Contenu |
|---|---|
| **Exercice** | le libellé que vous avez donné |
| **Rattachement** | l'**année de début** de la période |
| **Période** | du … au … |
| **Montant / mois** | en FCFA |
| **Mois saisis** | nombre de mois ayant au moins une cotisation |

#### « Ouvrir un exercice »

- **Libellé**, **Début**, **Fin** (`JJ/MM/AAAA`) et **Montant**.
- **« Ouvrir / mettre à jour »** crée l'exercice, ou met à jour celui qui porte
  le même rattachement.
- **« Année civile »** remplit les dates du 1er janvier au 31 décembre de l'année
  en cours.
- **« Supprimer l'exercice sélectionné »** retire l'exercice choisi dans le
  tableau.

> **La période est libre.** Un exercice peut aller du `01/07/2025` au
> `30/06/2026`. Le **rattachement** se fait alors sur **2025**, l'année de début.
> C'est ce qui détermine à quel exercice vos cotisations se rattachent.

### 2. Sauvegarde de la base

Le tableau des sauvegardes affiche trois colonnes : **Date · Taille · Fichier**.

Les fichiers s'appellent **`familles_AAAAMMJJ.db`** (un par jour) et sont rangés
dans **`sauvegardes/`**.

| Bouton | Effet |
|---|---|
| **Sauvegarder maintenant** | écrit une copie datée dans `sauvegardes/` |
| **Enregistrer une copie…** | copie vers un dossier de votre choix (clé USB…) |
| **Restaurer…** | remet en place une sauvegarde du dossier `sauvegardes/` |
| **Importer une base…** | remet en place une base choisie ailleurs |
| **Ouvrir le dossier** | ouvre `sauvegardes/` dans l'explorateur |

**Une sauvegarde automatique est faite à chaque fermeture** de l'application.

#### Ce qui est conservé

- Les sauvegardes automatiques `familles_AAAAMMJJ.db` : seules les **deux plus
  récentes** sont gardées (celle du jour et celle de la veille).
- Les fichiers `avant_restauration_<horodatage>.db` : **jamais purgés**. Ils
  gardent la trace de chaque restauration. Videz-les à la main si le dossier
  grossit.

#### Ce qui est refusé

Avant de restaurer, l'application vérifie le fichier :

- `PRAGMA integrity_check` doit répondre **`ok`** ;
- les tables **`clans`** et **`membres`** doivent exister.

Sinon : « Ce fichier n'est pas une base du Fonds d'Entraide (tables
manquantes) », ou « Sauvegarde corrompue ».

> **Avant toute restauration**, l'état actuel est d'abord copié dans
> `sauvegardes/avant_restauration_<horodatage>.db`. Une restauration ratée reste
> donc réversible.

### 3. Purge de la base

Un avertissement orange rappelle : « Opération irréversible : une sauvegarde est
faite automatiquement avant toute purge. »

**Trois boutons**, du moins au plus destructeur :

| Bouton | Efface | Conserve |
|---|---|---|
| **Vider la hiérarchie et les membres** | clans, grandes familles, lignées, familles, membres, **paiements et affectations** | exercices (campagnes), réglages |
| **Tout vider (sauf réglages)** | tout ce qui précède **+ les exercices** | réglages (montant) |
| **Réinitialisation totale** | **absolument tout**, y compris les réglages | rien |

Chaque purge demande une confirmation qui rappelle le contenu actuel
(« 7 clan(s), 391 famille(s), 599 membre(s), 227 versement(s) »).

> **La réinitialisation totale demande une seconde confirmation** : il faut taper
> le mot **`EFFACER`**. Sans ce mot, la purge est annulée.

Si la sauvegarde de sécurité échoue, l'application demande si vous voulez
poursuivre quand même — répondez **Non** dans le doute.

> **Les liens de parenté sont respectés.** La suppression des 599 membres se fait
> du plus jeune vers le plus ancien, pour ne jamais tenter d'effacer un membre
> dont un descendant existe encore.

---

## 10. Tester sans risque : le mode démo

Pour essayer l'application sur vos **vraies données** sans jamais modifier
`cotisations.db`.

```bash
python mode_demo.py
```

**Ce que fait le script :**

1. Copie `cotisations.db` dans `demo/demo_<horodatage>.db` ;
2. lance l'**application complète** sur cette copie (titre de fenêtre :
   « MODE DÉMO ») ;
3. à la fermeture, écrit un **état de vérification** dans
   `demo/etats/etat_<horodatage>.json`.

### L'état de vérification

Il contient, avec horodatages :

- les comptages et totaux de la copie **avant** et **après** vos essais ;
- l'état de la base réelle avant et après ;
- l'**empreinte SHA-256** de `cotisations.db` et le champ
  `base_reelle_intacte: true/false` — la preuve que le fichier n'a pas bougé.

```bash
python mode_demo.py --garder   # reprendre la dernière copie (poursuivre ses essais)
python mode_demo.py --liste    # lister les copies et les états
```

Rien n'est jamais supprimé : chaque lancement laisse sa copie et son état, ce qui
permet de comparer plusieurs sessions.

---

## 11. Les outils en ligne de commande

### `apercu_tableau_bord.py` — voir le tableau de bord sans risque

```bash
python apercu_tableau_bord.py              # sur cotisations.db, en LECTURE SEULE
python apercu_tableau_bord.py familles.db  # sur une autre base
python apercu_tableau_bord.py --liste      # lister les bases disponibles
```

La base est ouverte en **mode lecture seule** : toute écriture est refusée par
SQLite. Les exports PDF et CSV fonctionnent normalement.

### `corriger_noms.py` — réparer les noms parasites

Certains noms saisis dans l'Excel d'origine peuvent commencer par `/` ou être
vides (la barre oblique servait à dire « même famille que la ligne du dessus »).

```bash
python corriger_noms.py                      # SIMULATION : affiche, n'écrit rien
python corriger_noms.py --base demo/x.db     # simulation sur une copie
python corriger_noms.py --appliquer          # écrit réellement
```

Ordre de recherche du vrai nom :

1. le **prénom** de la personne contient `NOM Prénoms` → on garde le nom ;
2. le **nom après le séparateur** (`/APPIA` → `APPIA`) ;
3. le nom du **parent ou d'un ancêtre** ;
4. le dernier **nom connu de la famille**.

Avant d'écrire, le script sauvegarde dans `sauvegardes/avant_correction_noms_*.db`
et conserve la valeur d'origine dans les notes :
`FADJOUA SEWA L7 [nom d'origine: '/APPIA']`.

### `import_complet.py` / `import_cotisations.py` — importer un classeur Excel

Reconstruisent une base à partir du classeur `.xlsx`.

> **Attention :** `import_complet.py` **supprime la base existante** avant de la
> reconstruire. Faites une sauvegarde, et préférez un test avec
> `python mode_demo.py` d'abord.

---

## 12. Questions fréquentes et dépannage

### « Rien à enregistrer » quand je clique sur Enregistrer

Vous n'avez pas cliqué sur **Nouveau** ou **Modifier** avant. C'est une
protection : l'application ne devine pas ce que vous voulez faire.

### Un mois est refusé alors que je veux l'encaisser

Deux causes possibles :

- le mois est **déjà payé** → le message le nomme ; corrigez ou supprimez le
  versement existant ;
- le mois **n'est pas encore échu** → on ne peut pas encaisser l'avenir.

### Le dénominateur affiche 11 et non 12

C'est normal pour l'**année en cours** : seuls les mois écoulés sont dus. Une
année passée affiche `/12`, une année future `/0`.

### « no such column: t.description »

La base ouverte a été créée par une **ancienne version du schéma**. Deux
solutions : restaurer une sauvegarde récente (onglet Paramètres), ou importer
une base à jour.

### Le PDF ne s'imprime pas

`reportlab` sert au **rendu**, mais l'impression passe par le **lecteur PDF
associé** à Windows. Si aucun lecteur n'est installé, l'application affiche le
chemin du fichier pour l'ouvrir à la main.

### L'icône n'apparaît pas dans la barre des tâches

Elle dépend du **raccourci** utilisé pour lancer l'application, pas du code.
L'icône s'affiche bien dans la barre de titre.

### Où sont mes données ?

| Fichier / dossier | Contenu |
|---|---|
| `cotisations.db` | la base de référence (599 membres) |
| `familles.db` | base historique, quasi vide |
| `sauvegardes/` | sauvegardes automatiques et manuelles |
| `demo/` | copies du mode démo et états de vérification |
| `relation.ico` | icône de l'application |

### Puis-je travailler à plusieurs sur la même base ?

Non : une seule application à la fois par fichier. Utilisez `Sauvegarder
maintenant` puis `Enregistrer une copie…` pour transmettre la base.

### Comment revenir au thème clair par défaut ?

L'application démarre en **sombre**. Pour changer :
`Paramètres` → rien de prévu, ou éditer `theme.py` ligne `THEME_PAR_DEFAUT`.
Pour oublier un choix mémorisé, supprimer la ligne `theme` de la table
`parametres`.

---

## Récapitulatif : le parcours complet

```
1. Paramètres      → régler le montant mensuel et ouvrir l'exercice
2. Onglet 1 Clans  → créer les clans
3. Onglet 2        → les grandes familles dans chaque clan
4. Onglet 3        → les lignées
5. Onglet 4        → les familles
6. Onglet 5        → les membres
7. Onglet 6        → encaisser les cotisations + éditer les reçus
8. Onglet 7        → contrôler les chiffres, exporter CSV / PDF
9. Paramètres      → sauvegarder
```

> **Avant toute manipulation risquée** (import, restauration, purge), lancez
> `python mode_demo.py` : vous travaillez sur une copie, la base réelle reste
> intacte et un état de vérification est écrit à la fermeture.
