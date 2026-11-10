-- =====================================================================
--  schema_v2.sql — Schéma cible pour la réécriture Rust / Tauri
--  Moteur  : SQLite 3 (rusqlite, feature "bundled")
--  Devise  : FCFA (XOF) — montants en ENTIERS de francs, jamais de flottants
--  Hiérarchie : clan > grande famille > lignée > famille > membre
--
--  Différences volontaires avec schema.sql (v1) :
--    1. `campagnes.annee UNIQUE` disparaît  -> table `exercices` identifiée
--       par sa PÉRIODE (date_debut, date_fin), pas par une année.
--    2. Les échéances sont MATÉRIALISÉES dans `echeances` (une ligne par mois
--       d'exercice). Un mois appartient à un exercice et un seul :
--       UNIQUE (annee, mois). Fin de l'ambiguïté « nombre de mois échus »
--       vs « numéro de mois calendaire ».
--    3. `affectations` pointe une ÉCHÉANCE (echeance_id), plus un couple
--       (annee, mois) libre : impossible d'affecter un mois inexistant.
--    4. `paiements` ne porte plus d'exercice : l'exercice se déduit des
--       affectations (une seule source de vérité).
--    5. `paiements.numero_recu TEXT UNIQUE` + table `sequences` : la
--       numérotation des reçus quitte la table clé/valeur `parametres`.
--    6. Montants en INTEGER : plus d'arrondi de 0,01 F.
--    7. `PRAGMA user_version` : migrations possibles.
--
--  Règles garanties par la base :
--    - un clan, une grande famille et une lignée sont uniques dans leur
--      parent (COLLATE NOCASE) ; les FAMILLES peuvent être homonymes dans
--      une même lignée : c'est le cas dans l'historique réel ;
--    - le parent d'un membre est dans la MÊME famille (trigger) ;
--    - pas de cycle de parenté (trigger) ;
--    - un membre ayant des descendants ou des paiements ne peut pas être
--      supprimé (FK RESTRICT) ;
--    - une échéance doit tomber dans la période de son exercice (trigger) ;
--    - supprimer un exercice est refusé dès qu'une échéance est réglée.
--
--  NON garanti par la base, par choix : `paiements.montant_total` doit être
--  égal à la somme de ses affectations. Un trigger ne peut pas le vérifier
--  à l'INSERT (les affectations arrivent après) ; c'est une transaction
--  applicative, contrôlée par la vue `v_paiements_incoherents`. On ne pose
--  PAS de trigger anti-dépassement : l'historique importé contient des mois
--  réglés 2 000 F (paiement 105) qu'il faut conserver à l'identique.
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

-- ---------------------------------------------------------------------
-- 0. Métadonnées (version de schéma applicative, réglages simples)
-- ---------------------------------------------------------------------
CREATE TABLE meta (
    cle     TEXT PRIMARY KEY,
    valeur  TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- 1. Hiérarchie : clan > grande famille > lignée > famille > membre
-- ---------------------------------------------------------------------
CREATE TABLE clans (
    id          INTEGER PRIMARY KEY,
    nom         TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT,
    cree_le     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE grandes_familles (
    id          INTEGER PRIMARY KEY,
    clan_id     INTEGER NOT NULL REFERENCES clans(id) ON DELETE RESTRICT,
    nom         TEXT NOT NULL COLLATE NOCASE,
    description TEXT,
    cree_le     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (clan_id, nom)
);

CREATE TABLE lignees (
    id                INTEGER PRIMARY KEY,
    grande_famille_id INTEGER NOT NULL
                      REFERENCES grandes_familles(id) ON DELETE RESTRICT,
    nom               TEXT NOT NULL COLLATE NOCASE,
    description       TEXT,
    cree_le           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (grande_famille_id, nom)
);

CREATE TABLE familles (
    id          INTEGER PRIMARY KEY,
    lignee_id   INTEGER NOT NULL REFERENCES lignees(id) ON DELETE RESTRICT,
    nom         TEXT NOT NULL COLLATE NOCASE,
    ordre       INTEGER,
    description TEXT,
    cree_le     TEXT NOT NULL DEFAULT (datetime('now'))
    -- PAS d'UNIQUE (lignee_id, nom) : l'historique contient deux familles
    -- homonymes dans une même lignée (lignées 18 et 32). Les fusionner ou
    -- les renommer serait une réparation silencieuse des données de l'adhérent.
    -- Le signalement de doublon se fait à la saisie, dans l'application.
);

CREATE TABLE membres (
    id             INTEGER PRIMARY KEY,
    famille_id     INTEGER NOT NULL REFERENCES familles(id) ON DELETE RESTRICT,
    -- parent généalogique DIRECT, obligatoirement dans la même famille.
    -- RESTRICT reproduit la règle « pas de suppression d'un membre ayant
    -- des descendants » sans trigger dédié.
    parent_id      INTEGER REFERENCES membres(id) ON DELETE RESTRICT,
    nom            TEXT NOT NULL,
    prenom         TEXT,
    telephone      TEXT,
    sexe           TEXT CHECK (sexe IN ('M', 'F')),
    ordre_fratrie  INTEGER CHECK (ordre_fratrie IS NULL OR ordre_fratrie >= 1),
    statut         TEXT NOT NULL DEFAULT 'actif'
                   CHECK (statut IN ('actif', 'inactif', 'decede', 'parti',
                                     'suspendu')),
    date_statut    TEXT,
    -- bornes de cotisation : permettent de calculer les échéances dues
    -- sans dépendre du seul statut courant
    date_entree    TEXT,
    date_sortie    TEXT,
    notes          TEXT,
    cree_le        TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (date_entree IS NULL OR date_entree IS date(date_entree)),
    CHECK (date_sortie IS NULL OR date_sortie IS date(date_sortie))
);
CREATE INDEX idx_membres_famille ON membres(famille_id);
CREATE INDEX idx_membres_parent  ON membres(parent_id);
CREATE INDEX idx_membres_statut  ON membres(statut);
CREATE INDEX idx_membres_nom     ON membres(nom, prenom);

-- ---------------------------------------------------------------------
-- 2. Exercices et échéances
-- ---------------------------------------------------------------------
-- Un exercice est défini par sa PÉRIODE, pas par une année étiquette :
-- 01/07/2025 -> 30/06/2026 est parfaitement légal, et deux exercices ne
-- peuvent pas se disputer le même mois (contrainte sur `echeances`).
CREATE TABLE exercices (
    id              INTEGER PRIMARY KEY,
    libelle         TEXT NOT NULL,
    date_debut      TEXT NOT NULL,
    date_fin        TEXT NOT NULL,
    montant_mensuel INTEGER NOT NULL CHECK (montant_mensuel > 0),
    devise          TEXT NOT NULL DEFAULT 'XOF',
    statut          TEXT NOT NULL DEFAULT 'ouverte'
                    CHECK (statut IN ('ouverte', 'fermee', 'archivee')),
    cree_le         TEXT NOT NULL DEFAULT (datetime('now')),
    -- « IS » et non « = » : date('10/11/2026') renvoie NULL, et un CHECK
    -- évalué à NULL est ACCEPTÉ par SQLite. Avec « IS », le NULL devient
    -- faux et la date non ISO est bien refusée.
    CHECK (date_debut IS date(date_debut)),
    CHECK (date_fin IS date(date_fin)),
    CHECK (date_fin >= date_debut),
    UNIQUE (date_debut, date_fin)
);

-- Une échéance = un mois civil d'un exercice, avec son montant dû figé.
-- Le montant est FIGÉ à la création de l'échéance : changer le tarif d'un
-- exercice ne réécrit pas l'historique.
CREATE TABLE echeances (
    id             INTEGER PRIMARY KEY,
    exercice_id    INTEGER NOT NULL REFERENCES exercices(id) ON DELETE CASCADE,
    annee          INTEGER NOT NULL CHECK (annee BETWEEN 2000 AND 2100),
    mois           INTEGER NOT NULL CHECK (mois BETWEEN 1 AND 12),
    date_echeance  TEXT NOT NULL,
    montant_du     INTEGER NOT NULL CHECK (montant_du >= 0),
    -- UN SEUL exercice par mois civil : supprime toute ambiguïté de calcul
    UNIQUE (annee, mois),
    CHECK (date_echeance IS date(date_echeance))
);
CREATE INDEX idx_echeances_exercice ON echeances(exercice_id, annee, mois);

-- ---------------------------------------------------------------------
-- 3. Paiements et affectations
-- ---------------------------------------------------------------------
CREATE TABLE paiements (
    id            INTEGER PRIMARY KEY,
    membre_id     INTEGER NOT NULL REFERENCES membres(id) ON DELETE RESTRICT,
    date_paiement TEXT NOT NULL,
    montant_total INTEGER NOT NULL CHECK (montant_total > 0),
    mode          TEXT NOT NULL DEFAULT 'especes'
                  CHECK (mode IN ('especes', 'mobile_money', 'virement',
                                  'cheque', 'autre')),
    reference     TEXT,
    observation   TEXT,
    saisi_par     TEXT,
    -- numéro attribué dans la MÊME transaction que le paiement ; jamais
    -- réattribué, y compris si le paiement est supprimé ensuite
    numero_recu   TEXT UNIQUE,
    cree_le       TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (date_paiement IS date(date_paiement))
);
CREATE INDEX idx_paiements_membre ON paiements(membre_id, date_paiement);
CREATE INDEX idx_paiements_date   ON paiements(date_paiement);

CREATE TABLE affectations (
    id          INTEGER PRIMARY KEY,
    paiement_id INTEGER NOT NULL
                REFERENCES paiements(id) ON DELETE CASCADE,
    echeance_id INTEGER NOT NULL
                REFERENCES echeances(id) ON DELETE RESTRICT,
    montant     INTEGER NOT NULL CHECK (montant > 0),
    UNIQUE (paiement_id, echeance_id)
);
CREATE INDEX idx_affectations_echeance ON affectations(echeance_id);
CREATE INDEX idx_affectations_paiement ON affectations(paiement_id);

-- ---------------------------------------------------------------------
-- 4. Numérotation des reçus (compteur monotone, par exercice civil)
-- ---------------------------------------------------------------------
CREATE TABLE sequences (
    nom     TEXT NOT NULL,          -- ex. 'recu'
    annee   INTEGER NOT NULL,
    dernier INTEGER NOT NULL DEFAULT 0 CHECK (dernier >= 0),
    PRIMARY KEY (nom, annee)
);

-- ---------------------------------------------------------------------
-- 5. Triggers d'intégrité métier
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_membre_parent_meme_famille_ins
BEFORE INSERT ON membres
WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,
        'Le parent doit appartenir à la même famille que le membre')
    WHERE (SELECT famille_id FROM membres WHERE id = NEW.parent_id)
          IS NOT NEW.famille_id;
END;

CREATE TRIGGER trg_membre_parent_meme_famille_upd
BEFORE UPDATE OF parent_id, famille_id ON membres
WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,
        'Le parent doit appartenir à la même famille que le membre')
    WHERE (SELECT famille_id FROM membres WHERE id = NEW.parent_id)
          IS NOT NEW.famille_id;
    SELECT RAISE(ABORT, 'Un membre ne peut pas être son propre parent')
    WHERE NEW.parent_id = NEW.id;
END;

CREATE TRIGGER trg_membre_parent_sans_cycle
BEFORE UPDATE OF parent_id ON membres
WHEN NEW.parent_id IS NOT NULL
BEGIN
    WITH RECURSIVE anc(id) AS (
        SELECT NEW.parent_id
        UNION
        SELECT m.parent_id
          FROM membres m
          JOIN anc ON m.id = anc.id
         WHERE m.parent_id IS NOT NULL
    )
    SELECT RAISE(ABORT,
        'Lien de parenté cyclique : ce parent descend du membre')
    WHERE NEW.id IN (SELECT id FROM anc);
END;

CREATE TRIGGER trg_echeance_dans_exercice
BEFORE INSERT ON echeances
BEGIN
    SELECT RAISE(ABORT, 'L''échéance sort de la période de l''exercice')
    WHERE date(NEW.date_echeance)
          < (SELECT date(date_debut) FROM exercices WHERE id = NEW.exercice_id)
       OR date(NEW.date_echeance)
          > (SELECT date(date_fin) FROM exercices WHERE id = NEW.exercice_id);
END;

-- =====================================================================
-- 6. Vues
-- =====================================================================

-- Chemin hiérarchique complet d'un membre
CREATE VIEW v_membre_complet AS
SELECT m.id             AS membre_id,
       m.nom            AS nom,
       m.prenom         AS prenom,
       m.telephone      AS telephone,
       m.ordre_fratrie  AS ordre_fratrie,
       m.statut         AS statut,
       m.date_entree    AS date_entree,
       m.date_sortie    AS date_sortie,
       f.id             AS famille_id,
       f.nom            AS famille,
       l.id             AS lignee_id,
       l.nom            AS lignee,
       gf.id            AS grande_famille_id,
       gf.nom           AS grande_famille,
       c.id             AS clan_id,
       c.nom            AS clan,
       TRIM(IFNULL(pa.nom, '') || ' ' || IFNULL(pa.prenom, '')) AS parent
  FROM membres m
  JOIN familles         f  ON f.id  = m.famille_id
  JOIN lignees          l  ON l.id  = f.lignee_id
  JOIN grandes_familles gf ON gf.id = l.grande_famille_id
  JOIN clans            c  ON c.id  = gf.clan_id
  LEFT JOIN membres     pa ON pa.id = m.parent_id;

-- Pour chaque échéance due par un membre actif : montant dû et montant payé.
-- C'est LA vue qui remplace `mois_payes` / `mois_echus` / `situation`.
CREATE VIEW v_echeance_membre AS
SELECT m.id            AS membre_id,
       TRIM(m.nom || ' ' || IFNULL(m.prenom, '')) AS membre,
       e.id            AS echeance_id,
       e.exercice_id   AS exercice_id,
       e.annee         AS annee,
       e.mois          AS mois,
       e.date_echeance AS date_echeance,
       e.montant_du    AS montant_du,
       IFNULL(pay.paye, 0) AS paye,
       MAX(e.montant_du - IFNULL(pay.paye, 0), 0) AS reste
  FROM membres m
  JOIN echeances e
    ON (m.date_entree IS NULL OR date(m.date_entree) <= date(e.date_echeance))
   AND (m.date_sortie IS NULL OR date(m.date_sortie) >= date(e.date_echeance))
  LEFT JOIN (
        SELECT p.membre_id AS membre_id,
               a.echeance_id AS echeance_id,
               SUM(a.montant) AS paye
          FROM affectations a
          JOIN paiements p ON p.id = a.paiement_id
         GROUP BY p.membre_id, a.echeance_id
       ) pay
    ON pay.echeance_id = e.id
   AND pay.membre_id  = m.id
 WHERE m.statut = 'actif';

-- Solde d'un membre sur un exercice : mois dus, dû, payé, reste.
CREATE VIEW v_solde_membre_exercice AS
SELECT membre_id,
       exercice_id,
       COUNT(*)                                        AS mois_dus,
       SUM(montant_du)                                 AS du,
       SUM(paye)                                       AS paye,
       SUM(reste)                                      AS reste,
       SUM(CASE WHEN reste = 0 THEN 1 ELSE 0 END)      AS mois_a_jour
  FROM v_echeance_membre
 GROUP BY membre_id, exercice_id;

-- Encaissements d'un exercice (indépendant de la notion de membre actif :
-- on lit les affectations, donc l'historique reste juste même si le membre
-- est passé « inactif » depuis).
CREATE VIEW v_encaisse_exercice AS
SELECT e.exercice_id   AS exercice_id,
       e.annee         AS annee,
       SUM(a.montant)  AS encaisse,
       COUNT(DISTINCT p.id)        AS versements,
       COUNT(DISTINCT p.membre_id) AS cotisants
  FROM affectations a
  JOIN echeances e  ON e.id = a.echeance_id
  JOIN paiements p  ON p.id = a.paiement_id
 GROUP BY e.exercice_id, e.annee;

-- Contrôle de cohérence : un paiement doit égaler la somme de ses
-- affectations. Cette vue doit rester VIDE. À exécuter après chaque
-- écriture (dans la transaction) et au démarrage.
CREATE VIEW v_paiements_incoherents AS
SELECT p.id            AS paiement_id,
       p.montant_total AS montant_total,
       IFNULL(SUM(a.montant), 0) AS somme_affectations
  FROM paiements p
  LEFT JOIN affectations a ON a.paiement_id = p.id
 GROUP BY p.id
HAVING p.montant_total <> IFNULL(SUM(a.montant), 0);

-- Contrôle de cohérence : aucun membre ne doit régler plus que le dû d'un
-- mois. Le regroupement se fait par (membre, échéance) : une échéance est
-- partagée par tous les membres de l'exercice, chacun devant son mensuel.
-- (Autorisé dans l'historique importé, mais signalé à l'utilisateur.)
CREATE VIEW v_affectations_depassement AS
SELECT p.membre_id    AS membre_id,
       a.echeance_id  AS echeance_id,
       e.annee        AS annee,
       e.mois         AS mois,
       SUM(a.montant) AS total_membre,
       e.montant_du   AS montant_du
  FROM affectations a
  JOIN paiements p ON p.id = a.paiement_id
  JOIN echeances e ON e.id = a.echeance_id
 GROUP BY p.membre_id, a.echeance_id
HAVING SUM(a.montant) > e.montant_du;
