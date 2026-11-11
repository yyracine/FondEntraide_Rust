# RESUME.md — Fond d'Entraide

> **Fichier de reprise de session.** À consulter au début de chaque
> nouvelle session pour savoir où on en est et par où continuer.
> Dernière mise à jour : **09/11/2026** (fin de session).

> **Où en est le projet :** l'application est complète et stable. La session
> s'est terminée par la rédaction du `GUIDE.md` et une relecture critique de
> ses sections 5, 7 et 9, qui a mis au jour **un bug de production** (les trois
> purges échouaient toutes) désormais corrigé et vérifié.

---

## 0. À retenir — les deux apports de la dernière session

### 0.1 BUG CORRIGÉ : les trois purges échouaient

**Symptôme** — dans Paramètres, les trois boutons de purge
(« Vider la hiérarchie et les membres », « Tout vider (sauf réglages) »,
« Réinitialisation totale ») échouaient tous, sur la vraie base, avec :

```
Purge impossible : Ce membre a des descendants : supprimez-les d'abord
```

**Cause** — le trigger `trg_membre_suppr_avec_enfants` refuse la suppression
d'un membre ayant des descendants. Le code faisait un `DELETE FROM membres`
global ; SQLite traite les lignes dans un ordre arbitraire et rencontre un
parent avant ses enfants. Désactiver les clés étrangères ne suffit pas : un
trigger `BEFORE DELETE` n'est pas une contrainte de clé étrangère.

**Correctif** — nouvelle fonction `parametres._vider_membres(con)` (§ 6),
appelée par `purger()` à la place du `DELETE` global. Elle supprime par
**niveaux de profondeur**, feuilles d'abord, en bouclant :

```python
DELETE FROM membres
WHERE id NOT IN (SELECT DISTINCT parent_id FROM membres
                 WHERE parent_id IS NOT NULL)
```

**Vérifié** (sur copie, jamais sur la base réelle) :

| Purge | Garde | Vide |
|---|---|---|
| `hierarchie` | `campagnes`, `parametres` | clans…membres, paiements, affectations |
| `donnees` | `parametres` | + `campagnes` |
| `tout` | rien | tout, `parametres` compris |

Base réelle contrôlée après coup : **sha256 `46615a295c5f870871237104436d6629…`
inchangé, 227 paiements, `integrity_check = ok`**.

> **Non testé** : la purge via les clics réels dans l'interface (les dialogues
> de confirmation). Seule la fonction `purger()` a été exercée en direct.

### 0.2 `GUIDE.md` créé, puis relu section par section

`GUIDE.md` — **714 lignes, 12 sections + sommaire** — est le mode d'emploi
utilisateur : démarrage, hiérarchie, 8 onglets, saisie, cotisations, reçus,
tableau de bord, exports, paramètres, mode démo, outils CLI, dépannage.

Il a été relu et **corrigé** en profondeur sur les sections 5, 7 et 9. Les
erreurs trouvées étaient de vrais écarts avec le code, pas des détails :

| Section | Exemples d'erreurs corrigées |
|---|---|
| **5 — Cotisations** | sélecteur d'année annoncé « à droite » (il est à gauche) ; 4 filtres en cascade absents ; montant auto-rempli non documenté ; libellés de colonnes inventés ; reçu « proposé » alors que c'est une question Oui/Non |
| **7 — Tableau de bord** | 4 cartes annoncées au lieu de **5** (manquait « Membres en retard ») ; « Taux » au lieu de « Taux de recouvrement » ; niveau « membre » inexistant dans Répartition ; colonne « Moyenne/an » oubliée |
| **9 — Paramètres** | les 3 boutons de purge avaient des libellés inventés ; nom de sauvegarde faux (`familles_AAAAMMJJ.db`) ; conservation des `avant_restauration_*` mal expliquée ; rattachement d'un exercice sur l'année de début absent |

**Méthode de relecture** (à refaire pour toute doc) : extraire les libellés
réels du code (`grep 'text="…"'`), puis écrire un script de contrôle qui
vérifie que **chaque** terme cité dans le guide existe dans le fichier source.
Dernier bilan : 20/20, 37/37, 49/49 et 68/68 contrôles passés.

---

## 1. Le projet en une phrase

Construire une base SQLite des cotisations familiales (tontine) à partir
d'un classeur Excel, avec des requêtes, puis une application desktop
Tkinter de saisie qui est aujourd'hui le cœur du travail.

- **Source** : `C:/Users/HP/Documents/Fond Entraide Revise/FONDS D'ENTRE AIDE Final MAJ 3 Aout 24 (1).xlsx`
- **Dossier de travail** : `C:/Users/HP/Documents/Dev/Free-Pi/Fond-Entraide/`
- **Lancement** : `python app.py`
- **Guide utilisateur** : `GUIDE.md` — mode d'emploi complet (démarrage,
  hiérarchie, saisie, cotisations, reçus, tableau de bord, exports, paramètres,
  mode démo, outils en ligne de commande, dépannage).

---

## 2. L'état actuel — que fait l'application

Application Tkinter avec **8 onglets** (fenêtre 1060×800, thème clair/sombre).

| Onglet | Rôle | Statut |
|---|---|---|
| 1. Clans | saisie du niveau clan | ✔ testé |
| 2. Grandes familles | rattachées à un clan | ✔ testé |
| 3. Lignées | rattachées à une grande famille | ✔ testé |
| 4. Familles | rattachées à une lignée | ✔ testé |
| 5. Membres | parent limité à la même famille, anti-cycle, téléphone, colonne **Grande famille** | ✔ testé |
| 6. Cotisations | versements, grille 12 mois, arriérés, calendrier, **reçu PDF** | ✔ testé |
| 7. Tableau de bord | synthèse **lecture seule** + **export CSV / PDF / impression** | ✔ testé |
| 8. Paramètres | montant, exercices libres, sauvegardes, purge | ✔ testé |

### Le tableau de bord (onglet 7) — 5 sous-onglets
- **Cartes** : encaissé / attendu / taux de recouvrement (vert ≥80 %, orange ≥40 %, rouge sinon) / à jour / en retard.
- **Répartition** : par Clan / Grande famille / Lignée / Famille, avec membres, cotisants, part %.
- **Membres en retard** : triés par montant dû, `mois_payés/12`, reste dû.
- **Montants par année** : une colonne par année, les 4 niveaux, totaux par niveau. ← **demande du 09/11**
- **Par membre / an** : montant cotisé de chaque membre par année + total + moyenne/an. Se limite à l'exercice choisi. ← **demande du 09/11**

### Export & impression du tableau de bord (fait le 09/11)
Trois boutons dans la barre de titre de l'onglet 7 :
- **Exporter CSV** et **PDF…** → demandent d'abord l'étendue
  (*Oui* = tout le tableau de bord + chiffres clés, *Non* = seulement le
  sous-onglet affiché), puis le **dossier** de destination (le nom est
  imposé : `tableau_de_bord_<exercice>_<sous-onglet|complet>_<horodatage>`).
- **Imprimer PDF** → construit le PDF complet dans le dossier temporaire
  et l'envoie à l'imprimante par défaut (`os.startfile(..., "print")`).
- Module dédié `exports.py` : `Document` / `Bloc` (description neutre),
  `ecrire_csv`, `ecrire_pdf(..., moteur=)`, `imprimer`, `chemin_temporaire`.
- CSV : `;` comme séparateur, encodage `utf-8-sig` (Excel affiche les
  accents), **nombres exportés comme nombres** (1453000 et non « 1 453 000 »),
  pourcentages convertis en fractions (0.75).
- PDF : pages A4 **paysage**, mise en page reportlab si installé, sinon
  moteur interne sans aucune dépendance (`_pdf_minimal`). Pagination
  automatique avec répétition de l'en-tête, pied de page daté + n° de page.
  Vérifié : 62 pages pour la base de référence complète, alignement titre /
  tableau mesuré à 40,0 pt sur les deux moteurs.

### Passe de correction de bugs + validation complète (fait le 09/11)
- **`cotisations.py`** :
  - nouvelle **`mois_echus(con, annee)`** : source unique du nombre de mois dus
    (12 pour une année passée, mois courant pour l'année en cours, 0 pour une
    année future, bornes réelles si l'exercice est décalé).
  - **`situation()`** : `attendu` valait `mensuel * 12` **même pour l'année en
    cours** (2026 affichait 12 000 au lieu de 11 000) ; il vaut maintenant
    `mensuel * mois_echus`. `complet` compare aussi aux mois échus. `mois_echus`
    est exposé dans le dictionnaire.
  - nouvelle **`verifier_date()`** : accepte `AAAA-MM-JJ`, `JJ/MM/AAAA`,
    `JJ-MM-AAAA`, normalise en ISO, refuse le reste.
  - **`enregistrer_versement()`** valide désormais avant tout INSERT : mois
    hors 1–12, mois non encore échus, membre inexistant, date invalide.
    Avant, on obtenait des erreurs SQLite brutes (`CHECK constraint failed`,
    `FOREIGN KEY constraint failed`) et **une date `32/13/2026` était acceptée
    en base**.
- **`ecran_base.py`** : `_lire_une()` était **définie deux fois** (la première
  version, morte, était écrasée) → fusionnée.
- **`ecran_cotisations.py`** : les deux `/12` codés en dur (tableau et panneau
  de situation) utilisent `mois_echus` ; variable morte `etoiles` retirée.
- **`tableau_de_bord.py`** : `_mensualites_attendues()` délègue à
  `C.mois_echus()` au lieu de dupliquer la logique.
- **Code mort** : imports (`shutil`, `sqlite3`, `messagebox`, `parametres`,
  `CadreDefilant`) et variables inutilisées (`pleine_largeur`, `lbl_row`, `fam`,
  `fkey`, `prefixe`, `nouveau`, `n_police_f1`) supprimés. `pyflakes` ne signale
  plus qu'un `import reportlab` volontaire (test de disponibilité).
- **Validation** : 8 onglets × 2 thèmes, sélections sur les 5 écrans
  hiérarchiques, années 2019/2024/2025/2026, 6 bascules de thème, exports PDF
  avec les 2 moteurs → **0 erreur**. Écriture testée sur copie : création,
  modification et suppression de clan et de grande famille, refus du nom vide
  et du doublon, modification de membre, versement + suppression. **Résultats
  identiques en clair et en sombre** ; `integrity_check = ok`, aucune violation
  de clé étrangère.
- **Piège de test** : `enregistrer_versement` refuse un mois **déjà réglé** ;
  pour tester, prendre `C.mois_impayes(con, id, annee)` et non des mois fixes.
  De même, les écrans n'écrivent que si l'on passe par `nouveau()` (sinon
  `enregistrer()` affiche « Rien à enregistrer »).

### Icône de l'application (fait le 09/11)
- L'icône Tk par défaut (plume rouge) est remplacée par **`relation.ico`**
  (poignée de main + flèches bleue/rouge).
- `app.appliquer_icone(fenetre)` : `iconbitmap(default=...)` sous Windows, repli
  `PhotoImage`/`iconphoto` ailleurs. **N'échoue jamais** : si le fichier manque,
  l'application démarre avec l'icône par défaut.
- `Application(con, icone=None)` accepte un chemin explicite.
- Les fenêtres de test autonomes (`python ecran_membres.py`, etc.) l'appliquent
  aussi via un petit `try/except` autour de `from app import appliquer_icone`.
- Le `.ico` a été **réécrit en multi-tailles** (16, 20, 24, 32, 40, 48, 64, 128,
  256) avec 6 % de marge : à l'origine il ne contenait qu'une image 256×256,
  que Windows redimensionnait mal dans la barre des tâches. Vérifié : rien n'est
  rogné à 16 px.
- Piège : `iconbitmap()` renvoie `''` même quand ça marche sous Windows — ne pas
  s'en servir pour tester. Vérifier au pixel (capture de la barre de titre) ou
  avec `tk.PhotoImage(file="relation.ico")` **qui lui échoue** (Tk ne lit pas
  l'ICO) : c'est normal, ce n'est pas un bug.

### Palette DESIGN.md appliquée (fait le 09/11)
- `theme.py` suit désormais **`DESIGN.md`** (palette sombre type VS Code) :
  fond `#1E1E1E`, surface `#252526`, surface élevée `#333333`, bordure
  `#474747`, texte `#D4D4D4`, texte secondaire `#808080`, accent `#007ACC`,
  accent survolé `#005A9E`. Vérifié au pixel : le fond sombre occupe ~65-72 %
  de chaque écran, l'accent 9 %, texte clair < 3 % (aucune zone blanche).
- Le thème **clair** est l'équivalent clair de la même palette (`#F3F3F3` /
  `#FFFFFF` / accent `#007ACC`), pour que les deux modes restent cohérents.
- Styles ttk retravaillés : boutons plats à surface élevée avec **survol
  accent**, en-têtes de tableau `#007ACC` (survol `#005A9E`) en gras,
  **onglet actif sur fond accent**, champs de saisie à bordure accent au
  focus, sélection `#094771` avec texte blanc.
- Nouveaux rôles : `accent_hover`, `selection_texte`, `texte_doux`, `total`.
  `CORRESPONDANCES` traduit les anciennes couleurs codées en dur
  (`#1f4e5f`, `#2e7d8f`, `#e8eff1`, `#c8d2d8`…) vers la palette.
- `ecran_tableau_bord.py` : les tags `entete` / `total` étaient figés en clair ;
  `_habiller_tags()` les recalcule et s'abonne au thème (ils suivent la bascule).
- Piège : `theme.gestionnaire()` renvoie le gestionnaire courant, à n'utiliser
  qu'après `Application.__init__` (les écrans construits avant n'y ont pas accès).
- **Thème par défaut = sombre** (constante `theme.THEME_PAR_DEFAUT`). Le choix de
  l'utilisateur reste prioritaire : il est écrit dans `parametres['theme']` et
  relu au démarrage. Pour revenir au défaut, supprimer cette clé :
  `DELETE FROM parametres WHERE cle='theme'`.
- Piège : `parametres.lire_parametre()` exige un curseur avec `row_factory`
  (`db.initialiser` le fait, `sqlite3.connect` seul **non** → TypeError).

### Noms « parasites » : `/` en tête — corrigé le 09/11
- **Symptôme** : 3 membres en tête des retards, nom affiché `/APPIA`, `/`, `/`.
- **Cause** : dans l'Excel, un `/` en tête de cellule signifie « même famille
  que la ligne du dessus ». `nettoie_personne()` découpait sur le 1er espace
  sans retirer ce `/` : `"/APPIA CYNTHIA"` → nom `/APPIA` ; `"/ APPIA SEWA"`
  → nom `/` (et le prénom récupérait « APPIA SEWA »).
- **Correctif de l'import** (`import_complet.py`) : nouvelle regex
  `RE_PARASITES` qui retire `/ \ - – — . , ; : * + ' …` en tête. Si le
  libellé ne contient plus qu'un mot après un séparateur, ce mot est un
  **prénom** et l'import renvoie `nom=None` (le nom vient du parent) au lieu
  de fabriquer un faux nom.
- **Réparation des données existantes** : `corriger_noms.py`.
  `python corriger_noms.py` = **simulation** ; `--appliquer` = écrit (avec
  sauvegarde dans `sauvegardes/avant_correction_noms_*.db` et mémorisation de
  la valeur d'origine dans `notes` : `[nom d'origine: '/APPIA']`).
  Ordre de recherche du vrai nom : prénom de la personne (« APPIA SEWA » →
  APPIA) → nom après le séparateur (« /APPIA » → APPIA) → nom du parent ou
  d'un ancêtre → dernier nom exploitable de la famille.
- **Résultat sur `cotisations.db`** : 3 noms corrigés (223, 224, 225 → `APPIA`),
  membres toujours 599, paiements 227, affectations 1805 (somme 1 807 000 F),
  `integrity_check = ok`, plus aucun nom vide ni commençant par `/`.
- **Prénoms dédoublonnés** (même jour) : 224 `APPIA SEWA` → **`SEWA`**,
  225 `APPIA FABRICE` → **`FABRICE`** (le nom était répété dans le prénom).
  Résultat : `APPIA / CYNTHIA`, `APPIA / SEWA`, `APPIA / FABRICE`.
  Sauvegarde : `sauvegardes/avant_correction_prenoms_*.db`.

### Mode démo — tester sans risque (fait le 09/11)
- **`python mode_demo.py`** copie `cotisations.db` dans
  `demo/demo_<horodatage>.db` (via l'API `sqlite3.backup`) et lance
  l'**application complète** sur cette copie : toutes les données réelles,
  aucune écriture dans la base d'origine.
- À la fermeture, `demo/etats/etat_<horodatage>.json` garde :
  comptages et totaux **avant/après** de la copie, état de la base réelle
  avant/après, et **empreinte SHA-256** de `cotisations.db` : champ
  `base_reelle_intacte`. Ces états servent aux vérifications ultérieures.
- `--garder` évite de recréer une copie (on reprend ses essais),
  `--liste` affiche copies et états.
- Vérifié : session simulée = 5 onglets chargés (7/46/46/391/599), liste
  Membres exportée (16 pages), versement créé (paiements 227→228),
  reçu `RECU-2026-000001` généré ; `base_reelle_intacte: true`, empreintes
  identiques, `cotisations.db` toujours à 227 paiements.
- Attention : en mode démo la sauvegarde automatique de fermeture écrit dans
  `sauvegardes/` (rotation n / n-1). À surveiller si l'on veut préserver une
  ancienne sauvegarde.

### Bouton « Liste en PDF… » des onglets 1 à 5 (fait le 09/11)
- Un bouton **`Liste en PDF…`** dans chaque onglet : Clans, Grandes familles,
  Lignées, Familles, Membres.
- Module `liste_pdf_mixin.py` (`BoutonListePDF`) : exporte **exactement ce qui
  est affiché** — colonnes/en-têtes de la vue, valeurs formatées, et le
  **filtre par parent actif** (ex. un clan → ses seules grandes familles).
- `exports.liste_pdf()` choisit l'orientation (portrait jusqu'à 4 colonnes,
  paysage au-delà), calcule les largeurs de colonnes d'après le contenu réel,
  tronque avec « … » si besoin, répète l'en-tête à chaque page et ajoute une
  **ligne de total** quand une colonne est numérique.
- Nom de fichier : `liste_<onglet>_<horodatage>.pdf`, dans le dossier choisi.

### Reçu de paiement (fait le 09/11)
- **Bouton `Reçu (aperçu PDF)…`** sous l'historique des versements de l'onglet 6
  (actif seulement si un membre est sélectionné). Enregistrer un versement
  propose aussi **immédiatement** d'éditer le reçu.
- Chaîne : `recus.donnees_recu()` prépare les données → `exports.recu_pdf()`
  écrit le PDF → `os.startfile()` ouvre l'**aperçu** → dialogue
  *Oui = imprimer / Non = enregistrer une copie / Annuler*.
- Contenu : en-tête association, n° de reçu, encadré **« REÇU DE <MEMBRE> »**
  avec le montant en toutes lettres, tableau (membre, exercice, clan, grande
  famille, lignée, famille, mode, date, mois réglés, montant), deux lignes de
  signature, pied de page daté. A4 paysage, 1 page.
- **Numérotation stable** : `RECU-<année>-000001`. Le numéro est mémorisé par
  versement (`parametres.recu_paiement_<id>`) et le compteur par année
  (`parametres.recu_numeros`, JSON). Réimprimer ne change jamais le numéro ;
  supprimer un versement ne réattribue pas son numéro.
- Versement couvrant **deux exercices** : le n° suit la 1re année, et chaque
  mois est étiqueté de son année (« Déc 2025, Janv 2026 »).
- `recus.montant_en_lettres()` : français correct (vingt et un, soixante et
  onze, quatre-vingts, cent/quatre cents, mille invariable).

### Thème clair / sombre (fait le 09/11)
- Bouton `☾ Mode sombre` dans la barre de titre, **Ctrl+D**, ou menu Aide.
- Choix mémorisé dans la table `parametres` (clé `theme`).
- `theme.py` recolorie : styles ttk, conteneurs Tk purs, **et widgets Tk classiques** (Canvas, Text, Listbox, Frame, Label, Button). Sans cette dernière passe, des zones restaient blanches (champ Description, cadre défilant) — c'était le bug corrigé en dernier.

---

## 3. Les deux bases SQLite — ATTENTION

| Base | Rôle | Contenu |
|---|---|---|
| `familles.db` | **base de saisie (travail)** | 1 clan, 0 membre, 0 affectation, 0 campagne |
| `cotisations.db` | **base de référence (importée de l'Excel)** | 7 clans, 46 GF, 46 lignées, 391 familles, **599 membres**, 227 paiements, **1805 affectations**, 3 campagnes |

Totaux par année (sur `affectations.annee`) :
- 2024 → **1 453 000 FCFA** (1453 affectations)
- 2025 → **338 000 FCFA** (336)
- 2026 → **16 000 FCFA** (16)

> **Point bloquant du 09/11** : l'utilisateur n'a **pas de données** dans
> `familles.db`, donc il ne peut pas vérifier que le tableau de bord répond
> à ses exigences. Il a dit « on y reviendra demain ». **Prochaine étape
> probable** : l'aider à importer `cotisations.db` (Paramètres → Importer
> une base…) ou à saisir quelques données pour tester.

---

## 4. Règles métier non négociables

1. **Hiérarchie à 5 niveaux** : Clan (cellule A1, on retire le préfixe « Famille »/« LIGNEE ») → Grande famille (nom de feuille) → Lignée (A3 ou A4) → Famille → Membre.
2. **Le parent d'un membre doit être dans la MÊME famille** (appliqué à 3 niveaux : liste de l'UI, exclusion anti-cycle, triggers SQL).
3. Cotisation = **1000 FCFA/mois/membre**, devise FCFA (XOF).
4. Modèle : `paiements` + `affectations` (un paiement peut couvrir N mois).
5. **Tous les totaux se calculent sur `affectations.annee`, JAMAIS sur `paiements.campagne_id`** (un versement peut couvrir deux années).
6. Dates affichées **JJ/MM/AAAA**, stockées **AAAA-MM-JJ**.
7. Sauvegarde tournante : **2 fichiers exactement** (n et n-1).
8. On ignore les labels `(Penfant NN)` / `(APenfant NN)` ; on enlève le préfixe `(EnfantN)` mais on garde l'ordre de fratrie.

---

## 5. Décisions clés à ne pas oublier

- **Option A** (validée) : pas de migration de schéma. On garde `campagnes.annee UNIQUE`. Quand on ouvre un exercice dont la même année existe déjà avec une période différente → **demande de confirmation** (« remplacer ou annuler ? ») au lieu d'écraser en silence. Implémenté : `ouvrir_exercice(..., remplacer=False)` + dialogue dans l'écran.
- **Exercices libres** : `campagnes.annee` = année de rattachement (étiquette/clé) ; `date_debut`/`date_fin` = vraie période. Conséquence : deux exercices démarrant la même année entrent en collision (résolu par la confirmation ci-dessus).
- **Échéances du tableau de bord** : année passée → 12 mois ; année en cours → le mois courant ; année future → 0 (rien n'est dû, personne n'est en retard).
- **Colonne « Mois payés / échus »** (corrigée le 09/11) : l'ancien libellé « Mois payés » affichait un dénominateur figé `/12` alors que le reste dû se calcule sur les mois **échus** → `0/12` avec `11 000` dû pour l'exercice 2026 (11 mois échus en novembre). Le dénominateur vient maintenant de `mois_echus` (champ ajouté dans `membres_en_retard`), donc `0/12 → 12 000` et `0/11 → 11 000` : la ligne est cohérente. Ne jamais coder `/12` en dur dans une vue : utiliser `mois_echus`.
- **Calendrier** : on N'UTILISE PAS la popup de `DateEntry` (elle se ferme à chaque clic sous Windows) → **Calendrier intégré** (`tkcalendar.Calendar`).
- **Jamais de `<FocusOut>` sur le champ date** : ça ferme le calendrier.
- **Heredoc bash** : `\n` dans `<<'PY'` devient un saut de ligne réel et casse les f-strings. Toujours utiliser l'outil `edit` ou un fichier `.py` pour ces remplacements.
- `lien_parent_id` (généalogique) vs `parent_id` (hiérarchique) : collision documentée dans le code.

---

## 6. Fichiers du projet

### Application (saisie)
- `app.py` — fenêtre principale, 8 onglets, thème, diagnostic, auto-sauvegarde à la fermeture
- `db.py` — connexion, schéma, CRUD générique, `ErreurSaisie`, `parents_disponibles`, `nettoyer_nom`
- `ecran_base.py` — `EcranHierarchique` (squelette des onglets 1–5) + `CHAMPS_EN_LIGNE` (2 colonnes)
- `ecran_membres.py` — onglet 5 (parent même famille, anti-cycle, téléphone).
  Liste : Famille / Nom / Prénom / Téléphone / **Grande famille** / Parent /
  Statut. La colonne Fratrie a été retirée de la LISTE le 09/11 (l'ordre de
  fratrie reste saisissable dans la fiche et sert au tri de la liste).
- `ecran_grandes_familles.py`, `ecran_lignees.py`, `ecran_familles.py` — onglets 2–4
- `ecran_cotisations.py` — onglet 6 (grille 12 mois, arriérés, calendrier intégré)
- `ecran_tableau_bord.py` — onglet 7 (5 cartes de synthèse + 5 sous-onglets)
- `ecran_parametres.py` — onglet 8 (montant, exercices, sauvegardes, purge)
- `ui_commun.py` — `CadreDefilant` (canvas + molette)
- `exports.py` — export CSV / PDF / impression du tableau de bord + `recu_pdf`
- `recus.py` — numérotation des reçus, montant en lettres, données du reçu
- `liste_pdf_mixin.py` — bouton « Liste en PDF… » des onglets 1 à 5
- `mode_demo.py` — application complète sur une copie + états de vérification
- `corriger_noms.py` — détecte/répare les noms parasites (`/`, vide, …)
- `relation.ico` — icône de l'application (multi-tailles)
- `apercu_tableau_bord.py` — lance l'onglet 7 seul sur une base choisie
  (lecture seule), pour tester sans passer par les 8 onglets
- `theme.py` — thème clair/sombre (palettes, correspondances, recensement des widgets Tk)

### Moteur métier (sans UI)
- `cotisations.py` — campagnes, situation/mois payés/impayés, versements, totaux par année et par famille, arriérés, exercices libres
- `parametres.py` — montant, table `parametres`, sauvegarde/restauration/import/purge, exercices.
  **`_vider_membres()`** (ajoutée le 09/11) : supprime les membres par niveaux
  de profondeur pour que la purge ne heurte plus le trigger d'intégrité.
- `tableau_de_bord.py` — calculs de synthèse : vue d'ensemble, par niveau, retards, grille, **montants par niveau×année, montant par membre×année**

### Import & interrogation
- `import_complet.py` — (re)construit `cotisations.db` depuis l'Excel (7 clans, 599 membres, 1805 affectations)
- `import_cotisations.py`, `extrait_repertoires.py` (+ `repertoires.json`)
- `requetes.py` — CLI : `--clans --annee`, `--impayes`, `--grille`, `--synthese`, `--audit`, `--recap`, etc.
- `schema.sql` — 8 tables, vues (`v_membre_complet`, `v_cotisations_mensuelles`, `v_solde_membre_campagne`), 5 triggers
- `requirements.txt` — `tkcalendar>=1.6.1` (+ babel), `reportlab>=4.0` (optionnel)
- `README.md`, `REALISE.md`, **`GUIDE.md`** — documentation.
  `GUIDE.md` = mode d'emploi utilisateur (714 lignes, 12 sections).

Environ **7000 lignes** de Python/SQL au total.

---

## 7. État des tests

- **Étapes 1–8** : 13 blocs moteur + 13 blocs UI pour les cotisations ; tout est passé.
- **Tableau de bord** : chiffres validés sur une base de test à 4 membres / 2 clans / 2 exercices (encaisse 21 000/6 000, répartitions par niveau exactes, retards, grille, membre×année).
- **Thème** : bascule clair↔sombre stable, 17 widgets Tk suivis, **0 zone blanche** après correction (vérifié par mesure de pixels + modèle de vision), diagnostic 8 onglets = 0 inaccessible.
- **Convention de test** : bases temporaires `_*.db`, nettoyage après coup, `PYTHONIOENCODING=utf-8`, `python -m py_compile` après chaque modif. Ne jamais toucher à la vraie base autrement que sur une copie.
- **Purge** (09/11) : les 3 niveaux testés sur copie → OK. La base réelle était
  **cassée** avant le correctif `_vider_membres()` (voir § 0.1).
- **Mode démo** : vérifié par session simulée — base réelle intacte (sha256),
  copie modifiée (paiements 227 → 228), état JSON écrit.
- **Exports** : 2 moteurs PDF × 3 formats, CSV ouvert, listes des onglets 1–5
  (PDF 16 pages pour les 599 membres).
- **`GUIDE.md`** : contrôlé par script — chaque libellé de bouton, colonne,
  sous-onglet, statut et message cité existe dans le code source
  (68/68 puis 49/49, 37/37, 20/20 sur les sections réécrites).
- `sauvegardes/` : l'originale `cotisations_20261108_235409.db`, `familles_20261109.db`, les 2 copies d'avant/après remise à niveau du schéma,
  et les 2 copies d'avant correction des noms.

---

## 8. Prochaines étapes (suggestions)

Point de départ d'une nouvelle session : lire le § 0, puis choisir ci-dessous.

1. **TESTER LA PURGE DANS L'INTERFACE** — c'est le correctif de cette session et
   il n'a jamais été exercé par des clics réels :
   `python mode_demo.py`, onglet Paramètres → « Vider la hiérarchie et les
   membres ». Attendu : plus d'erreur « Ce membre a des descendants ».
2. ~~**Exporter** du tableau de bord (CSV/PDF)~~ — **fait le 09/11**
   (`exports.py` + 3 boutons dans l'onglet 7).
3. ~~**`GUIDE.md`**~~ — **fait le 09/11** (relu et corrigé, sections 5, 7, 9).
4. **Écran Paramètres pour les mentions du reçu** (`recu_association`,
   `recu_siege`, `recu_caissier` sont lus dans la table `parametres` mais
   aucun écran ne permet de les saisir).
5. **Filtre par clan/famille** dans les vues « Montants par année » et
   « Par membre / an » (les autres vues l'ont déjà).
6. **Relire les sections 1–4, 8, 10–12 du `GUIDE.md`** avec la même méthode
   que les sections 5/7/9 : elles n'ont pas eu cette passe critique.
7. Questions restées sans réponse de l'utilisateur :
   - nettoyer `Mariam` (membre 222, sans nom de famille) en `TANO` ?
   - les en-têtes `#007ACC` sont-ils trop saturés sur les grands tableaux ?
   - faut-il un raccourci `lancer.vbs` (icône dans la barre des tâches) ?
8. **Téléphones** des membres (colonne vide dans la source, à alimenter).
9. **Thème sombre de la barre de titres Windows** (DWM) — chantier séparé.
10. Peut-être un **rapport imprimable** de fin d'exercice.

---

## 9. Pièges connus (relire avant de coder)

- `int("Toutes les années")` → ValueError : toujours valider l'année avant de convertir.
- Restaurer une base : écrire **via `src.backup(con)` dans la connexion vivante**, pas vers un chemin fixe.
- Le `statut` de `campagnes` doit être `'ouverte'` (pas `'active'`, sinon violation du CHECK).
- `annee` dans `campagnes` est `INTEGER NOT NULL UNIQUE` : **ne pas** modifier ce schéma (227 paiements en dépendent).
- **`cotisations.db` : schéma remis à niveau le 09/11** (elle avait été créée
  par une ancienne version de `schema.sql`). Ajouts **non destructifs** :
  `familles.description`, `membres.sexe`, table `parametres`. Contrôles après
  coup : 7/46/46/391/599/227/1805/3 lignes inchangées, somme des affectations
  1 807 000 F, `integrity_check = ok`, aucune violation de clé étrangère.
  Les onglets 4 et 5 fonctionnent à nouveau. Sauvegardes :
  `sauvegardes/cotisations_avant_maj_schema_20261109_125825.db` et
  `sauvegardes/cotisations_maj_20261109_130722.db`.
  **Règle** : après avoir touché à `schema.sql`, vérifier avec
  `PRAGMA table_info` que chaque `.db` possède bien les colonnes attendues.
- Après une purge : `VACUUM`.
- **Purge et triggers** : un `DELETE FROM membres` global échoue à cause de
  `trg_membre_suppr_avec_enfants`. Utiliser `parametres._vider_membres(con)`.
  `PRAGMA foreign_keys = OFF` ne désactive **pas** un trigger `BEFORE DELETE`.
- **Documentation** : ne jamais écrire un libellé d'écran de mémoire. Les
  extraire (`grep 'text="' fichier.py`), puis vérifier par script que le guide
  et le code concordent. Trois sections sur douze contenaient de vraies erreurs.
- Vision model non fiable pour juger l'UI → vérifier avec mesures de pixels (PIL) et geometry (diagnostic).
- **Heredoc bash + `\n`** : écrire une chaîne contenant `\n` via un heredoc
  la casse en vrai saut de ligne (cf. §5). Utiliser un fichier `.py` écrit
  avec l'outil `write`, et vérifier avec `python -m py_compile`.
- Export PDF : ne pas utiliser `styles["Title"]` de reportlab comme parent,
  il ajoute 12 pt de retrait et décale le titre du tableau.

---

## 10. Commandes utiles

```bash
python app.py                    # lancer l'application
python -m py_compile *.py        # vérifier la syntaxe de tous les modules
python requetes.py --recap       # totaux par campagne
python requetes.py --audit 2025  # base vs répertoires Excel
python ecran_tableau_bord.py     # tableau de bord seul (mode test)
python mode_demo.py             # APPLICATION COMPLETE sur une COPIE de
                                # cotisations.db + etat de verification
python mode_demo.py --garder    # reutilise la derniere copie
python mode_demo.py --liste     # liste les copies et les etats
python apercu_tableau_bord.py   # tableau de bord seul sur cotisations.db,
                                # base ouverte en LECTURE SEULE (exports OK)
python apercu_tableau_bord.py familles.db   # sur la base de saisie
python apercu_tableau_bord.py --liste       # lister les .db du dossier
python corriger_noms.py                    # simuler la correction des noms
python corriger_noms.py --appliquer        # appliquer (sauvegarde d'abord)
```

**Vérifier la base réelle sans y toucher :**

```bash
python -c "import hashlib; print(hashlib.sha256(open('cotisations.db','rb').read()).hexdigest())"
# empreinte attendue : 46615a295c5f870871237104436d6629...
```

## 11. Chiffres de référence de `cotisations.db`

| Table | Lignes |
|---|---|
| clans | 7 |
| grandes_familles | 46 |
| lignees | 46 |
| familles | 391 |
| membres | 599 |
| campagnes | 3 |
| paiements | 227 |
| affectations | 1805 |

Total cotisé : **1 807 000 FCFA** — 2024 : 1 453 000 · 2025 : 338 000 ·
2026 : 16 000 (11 mois échus, mensuel 1 000 F).

Table `parametres` : `recu_numeros`, `recu_paiement_2` (la clé `theme` a été
supprimée — le thème sombre est le défaut de `theme.py`).

