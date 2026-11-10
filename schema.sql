-- =====================================================================
--  Base de données : Cotisations Fonds d'Entraide
--  Moteur  : SQLite 3
--  Devise  : FCFA (XOF)
--  Hiérarchie : Clan > Grande famille > Lignée > Famille > Membre
-- =====================================================================
--
--  RÈGLES MÉTIER STRUCTURANTES
--  ---------------------------
--  1. Un nom est unique dans son parent :
--       clan                : nom unique
--       grande famille      : unique dans le clan
--       lignée              : unique dans la grande famille
--       famille             : unique dans la lignée
--       membre              : pas d'unicité (deux homonymes peuvent exister)
--
--  2. Le parent d'un membre appartient OBLIGATOIREMENT à la même famille
--     que lui. Cette règle ne peut pas s'exprimer par une contrainte SQL
--     simple (FOREIGN KEY ne porte que sur une colonne) : elle est donc
--     garantie par un TRIGGER (voir §5).
--
--  3. Aucune suppression en cascade sur la hiérarchie : on ne supprime pas
--     un nœud qui a des descendants (ON DELETE RESTRICT). Les paiements
--     suivent leur membre (ON DELETE CASCADE) mais la suppression d'un
--     membre ayant payé est bloquée par le trigger de la §6.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. NIVEAU 1 : CLAN
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- 2. NIVEAU 2 : GRANDE FAMILLE
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grandes_familles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_id     INTEGER NOT NULL,
    nom         TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (clan_id, nom),
    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- 3. NIVEAU 3 : LIGNÉE
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lignees (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    grande_famille_id INTEGER NOT NULL,
    nom               TEXT NOT NULL,
    description       TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (grande_famille_id, nom),
    FOREIGN KEY (grande_famille_id) REFERENCES grandes_familles(id) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- 4. NIVEAU 4 : FAMILLE
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS familles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lignee_id  INTEGER NOT NULL,
    nom        TEXT NOT NULL,
    ordre      INTEGER,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (lignee_id, nom),
    FOREIGN KEY (lignee_id) REFERENCES lignees(id) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- 5. NIVEAU 5 : MEMBRE
--    Chaque membre est cotisant.
--    parent_id  = parent généalogique direct, DANS LA MÊME FAMILLE
--    famille_id = rattachement administratif
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS membres (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    famille_id     INTEGER NOT NULL,
    parent_id      INTEGER,
    nom            TEXT NOT NULL,
    prenom         TEXT,
    telephone      TEXT,
    ordre_fratrie  INTEGER,
    sexe           TEXT CHECK (sexe IN ('M','F')),
    statut         TEXT NOT NULL DEFAULT 'actif'
                   CHECK (statut IN ('actif','inactif','decede','parti','suspendu')),
    date_statut    TEXT,
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (famille_id) REFERENCES familles(id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_id)  REFERENCES membres(id)  ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- 6. CAMPAGNES
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campagnes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    libelle         TEXT NOT NULL UNIQUE,
    annee           INTEGER NOT NULL UNIQUE,
    montant_mensuel REAL NOT NULL DEFAULT 1000,
    devise          TEXT NOT NULL DEFAULT 'FCFA',
    date_debut      TEXT,
    date_fin        TEXT,
    statut          TEXT NOT NULL DEFAULT 'ouverte'
                    CHECK (statut IN ('ouverte','fermee','archivee')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- 7. PAIEMENTS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paiements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    membre_id     INTEGER NOT NULL,
    campagne_id   INTEGER NOT NULL,
    date_paiement TEXT NOT NULL,
    montant_total REAL NOT NULL CHECK (montant_total >= 0),
    mode          TEXT NOT NULL DEFAULT 'especes'
                  CHECK (mode IN ('especes','mobile_money','virement','cheque','autre')),
    reference     TEXT,
    saisi_par     TEXT,
    observation   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (membre_id)   REFERENCES membres(id)   ON DELETE CASCADE,
    FOREIGN KEY (campagne_id) REFERENCES campagnes(id) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- 8. AFFECTATIONS (un paiement couvre N mois)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS affectations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paiement_id INTEGER NOT NULL,
    annee       INTEGER NOT NULL,
    mois        INTEGER NOT NULL CHECK (mois BETWEEN 1 AND 12),
    montant     REAL NOT NULL CHECK (montant >= 0),
    UNIQUE (paiement_id, annee, mois),
    FOREIGN KEY (paiement_id) REFERENCES paiements(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- Index
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_gf_clan         ON grandes_familles(clan_id);
CREATE INDEX IF NOT EXISTS idx_lignees_gf      ON lignees(grande_famille_id);
CREATE INDEX IF NOT EXISTS idx_familles_lignee ON familles(lignee_id);
CREATE INDEX IF NOT EXISTS idx_membres_famille ON membres(famille_id);
CREATE INDEX IF NOT EXISTS idx_membres_parent  ON membres(parent_id);
CREATE INDEX IF NOT EXISTS idx_membres_statut  ON membres(statut);
CREATE INDEX IF NOT EXISTS idx_membres_nom     ON membres(nom, prenom);
CREATE INDEX IF NOT EXISTS idx_paiements_membre ON paiements(membre_id, campagne_id);
CREATE INDEX IF NOT EXISTS idx_affectations_periode ON affectations(annee, mois);

-- ---------------------------------------------------------------------
-- TRIGGER 1 : le parent d'un membre est dans la MÊME famille
--             (INSERT)
-- ---------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_membre_parent_meme_famille_ins
BEFORE INSERT ON membres
WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Le parent doit appartenir à la même famille que le membre')
    WHERE (SELECT famille_id FROM membres WHERE id = NEW.parent_id)
          IS NOT NEW.famille_id;
END;

-- ---------------------------------------------------------------------
-- TRIGGER 2 : idem, sur modification
-- ---------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_membre_parent_meme_famille_upd
BEFORE UPDATE OF parent_id, famille_id ON membres
WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Le parent doit appartenir à la même famille que le membre')
    WHERE (SELECT famille_id FROM membres WHERE id = NEW.parent_id)
          IS NOT NEW.famille_id;
    SELECT RAISE(ABORT, 'Un membre ne peut pas être son propre parent')
    WHERE NEW.parent_id = NEW.id;
END;

-- ---------------------------------------------------------------------
-- TRIGGER 3 : pas de cycle de parenté (A parent de B, B parent de A)
--             refus si le nouveau parent descend du membre modifié
-- ---------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_membre_parent_sans_cycle
BEFORE UPDATE OF parent_id ON membres
WHEN NEW.parent_id IS NOT NULL
BEGIN
    WITH RECURSIVE anc(id) AS (
        SELECT NEW.parent_id
        UNION
        SELECT m.parent_id FROM membres m JOIN anc ON m.id = anc.id
        WHERE m.parent_id IS NOT NULL
    )
    SELECT RAISE(ABORT, 'Lien de parenté cyclique : ce parent descend du membre')
    WHERE NEW.id IN (SELECT id FROM anc);
END;

-- ---------------------------------------------------------------------
-- TRIGGER 4 : on ne supprime pas un membre qui a des descendants
-- ---------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_membre_suppr_avec_enfants
BEFORE DELETE ON membres
BEGIN
    SELECT RAISE(ABORT, 'Ce membre a des descendants : supprimez-les d''abord')
    WHERE EXISTS (SELECT 1 FROM membres WHERE parent_id = OLD.id);
END;

-- ---------------------------------------------------------------------
-- TRIGGER 5 : on ne supprime pas un membre qui a des paiements
-- ---------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_membre_suppr_avec_paiements
BEFORE DELETE ON membres
BEGIN
    SELECT RAISE(ABORT, 'Ce membre a des paiements enregistrés : suppression refusée')
    WHERE EXISTS (SELECT 1 FROM paiements WHERE membre_id = OLD.id);
END;

-- =====================================================================
-- VUES
-- =====================================================================

-- Chemin hiérarchique complet d'un membre
CREATE VIEW IF NOT EXISTS v_membre_complet AS
SELECT
    m.id            AS membre_id,
    m.nom           AS nom,
    m.prenom        AS prenom,
    m.telephone     AS telephone,
    m.ordre_fratrie AS ordre_fratrie,
    m.statut        AS statut,
    f.id            AS famille_id,
    f.nom           AS famille,
    l.id            AS lignee_id,
    l.nom           AS lignee,
    gf.id           AS grande_famille_id,
    gf.nom          AS grande_famille,
    c.id            AS clan_id,
    c.nom           AS clan,
    (SELECT pa.nom || ' ' || COALESCE(pa.prenom,'')
       FROM membres pa WHERE pa.id = m.parent_id) AS parent
FROM membres m
JOIN familles         f  ON f.id  = m.famille_id
JOIN lignees          l  ON l.id  = f.lignee_id
JOIN grandes_familles gf ON gf.id = l.grande_famille_id
JOIN clans            c  ON c.id  = gf.clan_id;

-- Cotisations par membre / année / mois
CREATE VIEW IF NOT EXISTS v_cotisations_mensuelles AS
SELECT
    m.id                                  AS membre_id,
    m.nom || ' ' || COALESCE(m.prenom,'') AS membre,
    p.campagne_id,
    a.annee,
    a.mois,
    m.famille_id,
    SUM(a.montant)                        AS montant
FROM affectations a
JOIN paiements p ON p.id = a.paiement_id
JOIN membres   m ON m.id = p.membre_id
GROUP BY m.id, a.annee, a.mois;

-- Solde de chaque membre par campagne (calculé sur les AFFECTATIONS,
-- et non sur les paiements : un paiement peut couvrir plusieurs années)
CREATE VIEW IF NOT EXISTS v_solde_membre_campagne AS
SELECT
    m.id                            AS membre_id,
    m.nom || ' ' || COALESCE(m.prenom,'') AS membre,
    f.nom                           AS famille,
    c.annee                         AS annee,
    c.montant_mensuel * 12          AS attendu_annuel,
    COALESCE((SELECT SUM(a.montant) FROM affectations a
              JOIN paiements p ON p.id = a.paiement_id
              WHERE p.membre_id = m.id AND a.annee = c.annee), 0) AS verse,
    c.montant_mensuel * 12
      - COALESCE((SELECT SUM(a.montant) FROM affectations a
                  JOIN paiements p ON p.id = a.paiement_id
                  WHERE p.membre_id = m.id AND a.annee = c.annee), 0) AS solde
FROM membres m
JOIN familles f ON f.id = m.famille_id
CROSS JOIN campagnes c
WHERE m.statut = 'actif';
