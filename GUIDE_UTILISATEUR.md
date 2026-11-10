# Guide du caissier — Fonds d'Entraide

Ce guide décrit l'application telle qu'elle se présente : encaisser un
versement, imprimer un reçu, sauvegarder, restaurer, purger. Il s'adresse à la
personne qui tient la caisse, pas au développeur.

> **À retenir avant tout** : vos données vivent dans un seul fichier, à côté de
> l'application (`cotisations_v2.db`). Une copie de sauvegarde
> (`sauvegardes/`) et les exports CSV (`exports/`) sont également stockés là.
> Rien ne part sur Internet.

---

## 1. Ouvrir l'application

Double-cliquez sur le raccourci « Fonds d'Entraide ». La fenêtre s'ouvre sur la
liste des clans, avec les compteurs en haut à droite : nombre de clans, de
familles, de membres et total encaissé.

S'il n'y a pas de raccourci, lancez `fonds-app.exe` : l'application cherche la
base à côté de l'exécutable, puis à la racine du projet.

### Mode démonstration

Pour essayer sans risque : **Sauvegardes → Démonstration → « Ouvrir une
démonstration »**. Une seconde fenêtre s'ouvre sur une base fictive (2 clans,
5 familles, 15 membres, quelques versements) recréée à chaque lancement. Elle
porte le bandeau « Base de démonstration ». Fermez-la d'un clic sur la croix :
votre base réelle n'a jamais été ouverte.

---

## 2. Se repérer sur l'écran

De haut en bas :

1. **Recherche rapide** (« Encaisser pour un membre : nom ou prénom… ») : sert à
   trouver quelqu'un sans parcourir la hiérarchie.
2. **Quatre colonnes** : Clans → Grandes familles → Lignées → Familles. Quand un
   niveau ne contient qu'un seul élément, l'application descend toute seule.
   Les boutons de chaque colonne : `⤓` exporter en CSV, `+` ajouter, `✎`
   renommer, `✕` supprimer (deux clics pour confirmer).
3. **Barre des membres** : recherche locale, **Voir tous**, **Nouveau membre**,
   **Tarif**, **Sauvegardes**, **Plus ▾**.
4. **Puces d'exercice** : `Tous · 2026 · 2025 · 2024`. L'exercice en cours est
   sélectionné par défaut.
5. **Tableau des membres** : Nom, Prénom, Statut, Payé, Reste, Arriérés,
   Parent, et un bouton **Fiche** par ligne. La ligne du bas rappelle le nombre
   de membres affichés et les totaux.

**Reste** = ce qui reste dû sur l'exercice choisi. **Arriérés** = la part de ce
reste dont l'échéance est déjà passée.

---

## 3. Encaisser un versement

### Par la hiérarchie

1. Cliquez un clan, puis une grande famille, une lignée, une famille.
2. Le tableau affiche les membres de la famille.
3. **Cliquez la ligne du membre** (pas le bouton Fiche) : la feuille
   « Encaisser » s'ouvre.

### Par la recherche

1. Tapez un nom ou un prénom dans la recherche en haut.
2. Cliquez le résultat : la feuille s'ouvre directement, sans changer de
   famille.

### Dans la feuille

- L'en-tête rappelle le membre, son chemin dans la hiérarchie et le périmètre :
  « Exercice 2026 · X F dus sur le périmètre ».
- Les soldes de l'exercice sont affichés (dû, payé, reste, arriérés).
- Saisissez le **Montant (FCFA)** — un nombre entier, sans espace ni virgule.
- Vérifiez la **Date du versement** (aujourd'hui par défaut).
- Choisissez le **Mode** : Espèces, Mobile money, Virement, Chèque, Autre.
- L'aperçu **Répartition** se met à jour à la frappe : il montre les mois que ce
  versement va couvrir et le reliquat éventuel.
- Cliquez **Enregistrer le versement**.

Le versement part toujours au mois échu le plus ancien encore impayé, puis
remonte. Il ne peut pas dépasser le dû : si vous saisissez 5 000 F pour 3 mois
de 1 000 F, l'enregistrement est refusé avec le message « 5 000 F ne peuvent
pas être affectés : 2 000 F resteraient non ventilés ». Diminuez le montant ou
choisissez un autre exercice dans la feuille.

Après l'enregistrement, le reçu s'affiche sous le formulaire : numéro, montant,
et la liste des mois couverts. Les soldes du tableau et les compteurs du haut se
mettent à jour aussitôt.

### Si vous vous êtes trompé

Ouvrez la **Fiche** du membre (bouton à droite de la ligne), puis dans
« Versements », cliquez **Annuler** : le bouton devient **Confirmer
l'annulation**, un second clic supprime le versement et libère les mois. Le
numéro de reçu, lui, reste consommé : il ne sera jamais réattribué.

---

## 4. Imprimer un reçu

1. Enregistrez le versement : le reçu apparaît dans la feuille.
2. Cliquez **Imprimer le reçu**.
3. La fenêtre d'impression de Windows s'ouvre : choisissez l'imprimante, puis
   imprimez.

La feuille imprimée porte le nom du Fonds, le membre, son chemin, le numéro de
reçu, la date du versement, le mode, le montant, les mois couverts et le total.
Réimprimer un reçu donne toujours le **même numéro** : c'est le même document.

Pour imprimer une **liste** de membres : choisissez la famille et l'exercice,
puis **Plus ▾ → Imprimer la liste affichée**. Ce qui est imprimé est exactement
ce qui est affiché — famille, recherche et exercice compris — avec une ligne de
totaux en bas.

---

## 5. Changer d'exercice et lire les arriérés

Les puces `Tous · 2026 · 2025 · 2024` changent le périmètre des montants :

- une année : Payé, Reste et Arriérés ne portent que sur cette campagne ;
- **Tous** : les trois campagnes s'additionnent — utile pour voir la dette
  globale d'un membre.

Changer d'exercice ne modifie aucune donnée : c'est une façon de regarder.

---

## 6. Voir toute la liste des membres

**Voir tous** affiche les 599 membres dans un seul tableau, avec une colonne
**Chemin** (« clan › grande famille › lignée › famille ») qui distingue les
homonymes. La recherche porte alors sur toute la base.

Pour revenir au tableau d'une famille, cliquez un clan ou une famille dans les
colonnes de gauche. Le bouton « Voir tous » reste visible en permanence.

**Exports CSV** (ouvrables dans Excel) : **Plus ▾ → « Exporter la liste
affichée »** ou **« Tout exporter »**. Le bandeau de confirmation donne le
chemin du fichier, dans le dossier `exports/`. Les montants y sont des nombres
nus, séparés par des points-virgules.

---

## 7. Modifier les membres et la hiérarchie

- **Nouveau membre** : nom obligatoire, prénom, téléphone, sexe, statut, ordre
  dans la fratrie, dates d'entrée et de sortie, parent (limité à la même
  famille), notes. Une date de sortie arrête les cotisations après cette date.
- **Modifier** (dans la Fiche) : mêmes champs. **Supprimer le membre** est
  refusé si la personne a des descendants ou des versements — c'est volontaire,
  pour ne pas effacer d'argent par accident.
- Colonnes : `+` crée, `✎` renomme, `✕` supprime en deux clics. Un niveau qui
  contient encore des enfants ne peut pas être supprimé.
- Changer un membre de famille alors que son parent reste dans l'ancienne est
  refusé, avec un message clair.

## 8. Changer le tarif

**Tarif** ouvre l'écran du tarif de l'exercice affiché : nouveau montant
mensuel et mois d'effet (le mois suivant par défaut). Les mois antérieurs
gardent leur montant, même impayés ; les mois déjà réglés ne bougent pas.
Fermer l'écran **n'annule pas** un tarif déjà appliqué.

---

## 9. Sauvegarder

**Sauvegardes** affiche la liste des copies existantes, de la plus récente à la
plus ancienne, avec leur date lisible et leur taille.

- **Sauvegarder maintenant** crée une copie immédiate, vérifiée (intégrité et
  version de schéma), puis affiche son nom.
- Cinq copies au maximum sont conservées : à chaque nouvelle sauvegarde, la plus
  ancienne est effacée. Le dossier ne grossit donc pas sans fin.
- Les fichiers s'appellent `cotisations_AAAA-MM-JJ_HH-MM-SS.db` et vivent dans
  le dossier `sauvegardes/`, à côté de la base.

**Quand sauvegarder** : avant une purge, avant une restauration, avant une
grosse séance de corrections, et en fin de journée. Une copie prend une seconde.

## 10. Restaurer

1. **Sauvegardes**, puis **Restaurer** sur la copie voulue.
2. Le bouton devient **Confirmer** : un second clic restaure.
3. L'application sauvegarde d'abord l'état actuel (une copie de sécurité), puis
   remplace le contenu de la base. Le message final donne le nom de cette copie
   de sécurité : c'est votre marche arrière si vous avez restauré la mauvaise.

Une copie abîmée, ou issue de l'ancienne version Python, est **refusée avant
toute écriture** : la base en cours reste intacte.

---

## 11. Purger

**Sauvegardes → Purger la base.** Trois portées, chacune à double clic :

| Bouton | Efface | Conserve |
|---|---|---|
| **Effacer les cotisations** | versements et affectations | membres, hiérarchie, exercices, tarifs |
| **Effacer membres et hiérarchie** | membres, familles, lignées, grandes familles, clans, **et leurs versements** | exercices et échéances |
| **Tout effacer** | les deux | exercices et échéances |

Avant toute suppression, l'application écrit et vérifie une **copie de
sécurité** ; si la copie échoue, rien n'est effacé. Tout part dans une seule
transaction : soit tout est effacé, soit rien ne l'est. Le message final dit
ligne par ligne ce qui est parti (« Effacé : 227 versements, 1 805
affectations… »).

Deux choses ne sont **jamais** effacées : les exercices avec leurs tarifs, et
les numéros de reçus déjà utilisés (ils ne seront pas réattribués).

Après une purge « Tout effacer », l'application reste utilisable : recréez vos
clans et familles, puis vos membres. Pour revenir en arrière, **Restaurer** la
copie de sécurité indiquée dans le message.

---

## 12. Où sont mes fichiers

| Élément | Emplacement |
|---|---|
| Base de données | `cotisations_v2.db`, à côté de l'application |
| Sauvegardes (5 max) | `sauvegardes/cotisations_AAAA-MM-JJ_HH-MM-SS.db` |
| Exports CSV | `exports/<liste>_AAAA-MM-JJ_HH-MM-SS.csv` |
| Démonstration | fichier temporaire `fonds-entraide-demo.db` |

Ces dossiers contiennent des données nominatives : ils restent sur le poste et
ne doivent pas être envoyés par messagerie ni déposés sur un site public. Une
clé USB ou un disque externe suffit pour une copie hors du poste.

---

## 13. En cas de problème

| Message | Que faire |
|---|---|
| « Montant invalide : un nombre entier de francs, supérieur à zéro. » | Saisir un montant sans espace ni virgule (ex. `3000`). |
| « X F ne peuvent pas être affectés : Y F resteraient non ventilés » | Réduire le montant, ou changer d'exercice dans la feuille. |
| « Aucun exercice ouvert : impossible d'imputer le versement. » | Aucun exercice ne couvre la date : vérifier les exercices. |
| « Suppression impossible : … » | Le nœud ou le membre a des enfants ou des versements : les traiter d'abord. |
| « Copie abîmée » / « schéma … attendu » | Cette copie n'est pas restaurable : en choisir une autre, plus récente. |
| « Base introuvable ou illisible » | Vérifier que `cotisations_v2.db` est bien à côté de l'exécutable, ou restaurer une copie. |

---

## 14. Fin de journée — la check-list

1. Les versements de la journée sont saisis (compteurs cohérents en haut).
2. **Sauvegardes → Sauvegarder maintenant**.
3. Le message de confirmation donne le nom de la copie : notez-le si vous
   tenez un cahier.
4. Fermez la fenêtre.
