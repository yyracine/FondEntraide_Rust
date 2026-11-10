//! Lectures de la hiérarchie : clan → grande famille → lignée → famille →
//! membres. Chaque membre arrive avec son solde de cotisation, agrégé en SQL
//! (une requête par famille, jamais une requête par membre), et filtrable par
//! exercice pour ne jamais mélanger deux années.

use rusqlite::{params, Connection};
use serde::Serialize;

use crate::erreur::Erreur;

#[derive(Debug, Clone, Serialize)]
pub struct Resume {
    pub clans: i64,
    pub familles: i64,
    pub membres: i64,
    pub encaisse: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Clan {
    pub id: i64,
    pub nom: String,
    pub description: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct GrandeFamille {
    pub id: i64,
    pub nom: String,
    pub clan_id: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Lignee {
    pub id: i64,
    pub nom: String,
    pub grande_famille_id: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Famille {
    pub id: i64,
    pub nom: String,
    pub lignee_id: i64,
    pub ordre: Option<i64>,
    /// Nombre de membres, pour distinguer deux familles homonymes.
    pub membres: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Exercice {
    pub id: i64,
    pub libelle: String,
    pub date_debut: String,
    pub date_fin: String,
    /// Année de début, utilisée comme étiquette courte quand l'exercice
    /// couvre une année civile.
    pub annee: i32,
    pub statut: String,
    /// Vrai si la période contient la date du jour.
    pub courant: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct MembreResume {
    pub id: i64,
    pub nom: String,
    pub prenom: Option<String>,
    pub statut: String,
    pub ordre_fratrie: Option<i64>,
    pub parent: Option<String>,
    /// Total dû sur le périmètre demandé (un exercice, ou tous).
    pub du: i64,
    /// Total encaissé sur ce périmètre.
    pub paye: i64,
    /// Reste à payer (`du - paye`, jamais négatif).
    pub reste: i64,
    /// Part du reste correspondant à des échéances déjà échues.
    pub arrieres: i64,
}

pub fn resume(con: &Connection) -> Result<Resume, Erreur> {
    Ok(Resume {
        clans: con.query_row("SELECT COUNT(*) FROM clans", [], |l| l.get(0))?,
        familles: con.query_row("SELECT COUNT(*) FROM familles", [], |l| l.get(0))?,
        membres: con.query_row("SELECT COUNT(*) FROM membres", [], |l| l.get(0))?,
        encaisse: con.query_row(
            "SELECT IFNULL(SUM(montant), 0) FROM affectations",
            [],
            |l| l.get(0),
        )?,
    })
}

/// Exercices, du plus récent au plus ancien, avec l'indication de celui qui
/// contient la date du jour.
pub fn exercices(con: &Connection) -> Result<Vec<Exercice>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT id, libelle, date_debut, date_fin,
                CAST(substr(date_debut, 1, 4) AS INTEGER) AS annee,
                statut,
                date('now', 'localtime') BETWEEN date(date_debut) AND date(date_fin)
                    AS courant
           FROM exercices
          ORDER BY date_debut DESC",
    )?;
    let lignes = stmt.query_map([], |l| {
        Ok(Exercice {
            id: l.get(0)?,
            libelle: l.get(1)?,
            date_debut: l.get(2)?,
            date_fin: l.get(3)?,
            annee: l.get(4)?,
            statut: l.get(5)?,
            courant: l.get(6)?,
        })
    })?;
    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

pub fn clans(con: &Connection) -> Result<Vec<Clan>, Erreur> {
    let mut stmt =
        con.prepare("SELECT id, nom, description FROM clans ORDER BY nom COLLATE NOCASE")?;
    let lignes = stmt.query_map([], |l| {
        Ok(Clan {
            id: l.get(0)?,
            nom: l.get(1)?,
            description: l.get(2)?,
        })
    })?;
    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

pub fn grandes_familles(con: &Connection, clan_id: i64) -> Result<Vec<GrandeFamille>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT id, nom, clan_id FROM grandes_familles
          WHERE clan_id = ?1 ORDER BY nom COLLATE NOCASE",
    )?;
    let lignes = stmt.query_map(params![clan_id], |l| {
        Ok(GrandeFamille {
            id: l.get(0)?,
            nom: l.get(1)?,
            clan_id: l.get(2)?,
        })
    })?;
    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

pub fn lignees(con: &Connection, grande_famille_id: i64) -> Result<Vec<Lignee>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT id, nom, grande_famille_id FROM lignees
          WHERE grande_famille_id = ?1 ORDER BY nom COLLATE NOCASE",
    )?;
    let lignes = stmt.query_map(params![grande_famille_id], |l| {
        Ok(Lignee {
            id: l.get(0)?,
            nom: l.get(1)?,
            grande_famille_id: l.get(2)?,
        })
    })?;
    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

pub fn familles(con: &Connection, lignee_id: i64) -> Result<Vec<Famille>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT f.id, f.nom, f.lignee_id, f.ordre,
                (SELECT COUNT(*) FROM membres m WHERE m.famille_id = f.id) AS membres
           FROM familles f
          WHERE f.lignee_id = ?1
          ORDER BY f.ordre IS NULL, f.ordre, f.nom COLLATE NOCASE",
    )?;
    let lignes = stmt.query_map(params![lignee_id], |l| {
        Ok(Famille {
            id: l.get(0)?,
            nom: l.get(1)?,
            lignee_id: l.get(2)?,
            ordre: l.get(3)?,
            membres: l.get(4)?,
        })
    })?;
    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

/// Membres d'une famille, filtrables par nom ou prénom, avec leur solde.
///
/// `exercice_id` restreint les montants à un exercice : sans lui, les
/// colonnes additionnent toutes les années, ce qui doit rester un choix
/// explicite de l'utilisateur et non le comportement par défaut.
///
/// `date_reference` permet de figer « aujourd'hui » (tests) ; à `None`, la
/// base utilise la date locale de la machine.
pub fn membres(
    con: &Connection,
    famille_id: i64,
    recherche: Option<&str>,
    exercice_id: Option<i64>,
    date_reference: Option<&str>,
) -> Result<Vec<MembreResume>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT m.id, m.nom, m.prenom, m.statut, m.ordre_fratrie,
                NULLIF(TRIM(IFNULL(pa.nom, '') || ' ' || IFNULL(pa.prenom, '')), '') AS parent,
                IFNULL(s.du, 0)       AS du,
                IFNULL(s.paye, 0)     AS paye,
                IFNULL(s.reste, 0)    AS reste,
                IFNULL(s.arrieres, 0) AS arrieres
           FROM membres m
           LEFT JOIN membres pa ON pa.id = m.parent_id
           LEFT JOIN (
                 SELECT membre_id,
                        SUM(montant_du) AS du,
                        SUM(paye)       AS paye,
                        SUM(reste)      AS reste,
                        SUM(CASE
                              WHEN date(date_echeance)
                                   <= IFNULL(?4, date('now', 'localtime'))
                               AND reste > 0
                              THEN reste ELSE 0
                            END) AS arrieres
                   FROM v_echeance_membre
                  WHERE (?3 IS NULL OR exercice_id = ?3)
                  GROUP BY membre_id
                ) s ON s.membre_id = m.id
          WHERE m.famille_id = ?1
            AND (
                 ?2 IS NULL
                 OR m.nom LIKE '%' || ?2 || '%' COLLATE NOCASE
                 OR IFNULL(m.prenom, '') LIKE '%' || ?2 || '%' COLLATE NOCASE
                )
          ORDER BY m.ordre_fratrie IS NULL, m.ordre_fratrie,
                   m.nom COLLATE NOCASE, m.prenom COLLATE NOCASE",
    )?;
    let lignes = stmt.query_map(
        params![famille_id, recherche, exercice_id, date_reference],
        |l| {
            Ok(MembreResume {
                id: l.get(0)?,
                nom: l.get(1)?,
                prenom: l.get(2)?,
                statut: l.get(3)?,
                ordre_fratrie: l.get(4)?,
                parent: l.get(5)?,
                du: l.get(6)?,
                paye: l.get(7)?,
                reste: l.get(8)?,
                arrieres: l.get(9)?,
            })
        },
    )?;
    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

/// Membre retrouvé hors navigation, avec son chemin dans la hiérarchie : deux
/// homonymes se distinguent par leur famille, pas par un identifiant nu.
#[derive(Debug, Clone, Serialize)]
pub struct MembreTrouve {
    #[serde(flatten)]
    pub membre: MembreResume,
    pub chemin: String,
}

/// « clan › lignée › famille », en fusionnant deux niveaux consécutifs qui
/// portent le même nom (une GF et sa lignée homonymes, par exemple).
fn chemin(clan: &str, grande_famille: &str, lignee: &str, famille: &str) -> String {
    let mut noms: Vec<&str> = Vec::new();
    for nom in [clan, grande_famille, lignee, famille] {
        if noms.last().copied() != Some(nom) {
            noms.push(nom);
        }
    }
    noms.join(" › ")
}

/// Recherche par nom ou prénom **dans toute la base**, sans passer par
/// clan → grande famille → lignée → famille. Sert à encaisser un versement
/// pour quelqu'un qu'on identifie par son nom.
///
/// `membre_id` restreint à un membre précis (rafraîchissement après un
/// versement), `limite` borne le nombre de résultats affichés.
pub fn rechercher_membres(
    con: &Connection,
    membre_id: Option<i64>,
    recherche: Option<&str>,
    exercice_id: Option<i64>,
    date_reference: Option<&str>,
    limite: i64,
) -> Result<Vec<MembreTrouve>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT m.id, m.nom, m.prenom, m.statut, m.ordre_fratrie,
                NULLIF(TRIM(IFNULL(pa.nom, '') || ' ' || IFNULL(pa.prenom, '')), '') AS parent,
                IFNULL(s.du, 0), IFNULL(s.paye, 0), IFNULL(s.reste, 0), IFNULL(s.arrieres, 0),
                c.nom AS clan, gf.nom AS grande_famille, l.nom AS lignee, f.nom AS famille
           FROM membres m
           JOIN familles f          ON f.id = m.famille_id
           JOIN lignees l           ON l.id = f.lignee_id
           JOIN grandes_familles gf ON gf.id = l.grande_famille_id
           JOIN clans c             ON c.id = gf.clan_id
           LEFT JOIN membres pa     ON pa.id = m.parent_id
           LEFT JOIN (
                 SELECT membre_id,
                        SUM(montant_du) AS du,
                        SUM(paye)       AS paye,
                        SUM(reste)      AS reste,
                        SUM(CASE
                              WHEN date(date_echeance)
                                   <= IFNULL(?4, date('now', 'localtime'))
                               AND reste > 0
                              THEN reste ELSE 0
                            END) AS arrieres
                   FROM v_echeance_membre
                  WHERE (?3 IS NULL OR exercice_id = ?3)
                  GROUP BY membre_id
                ) s ON s.membre_id = m.id
          WHERE (?1 IS NULL OR m.id = ?1)
            AND (
                 ?2 IS NULL
                 OR m.nom LIKE '%' || ?2 || '%' COLLATE NOCASE
                 OR IFNULL(m.prenom, '') LIKE '%' || ?2 || '%' COLLATE NOCASE
                )
          ORDER BY m.nom COLLATE NOCASE, m.prenom COLLATE NOCASE, m.id
          LIMIT ?5",
    )?;

    let lignes = stmt.query_map(
        params![membre_id, recherche, exercice_id, date_reference, limite],
        |l| {
            let clan: String = l.get(10)?;
            let grande_famille: String = l.get(11)?;
            let lignee: String = l.get(12)?;
            let famille: String = l.get(13)?;
            Ok(MembreTrouve {
                membre: MembreResume {
                    id: l.get(0)?,
                    nom: l.get(1)?,
                    prenom: l.get(2)?,
                    statut: l.get(3)?,
                    ordre_fratrie: l.get(4)?,
                    parent: l.get(5)?,
                    du: l.get(6)?,
                    paye: l.get(7)?,
                    reste: l.get(8)?,
                    arrieres: l.get(9)?,
                },
                chemin: chemin(&clan, &grande_famille, &lignee, &famille),
            })
        },
    )?;

    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

/// Soldes d'un membre précis : la feuille s'en sert pour se remettre à jour
/// après un versement, même si le membre a été trouvé par la recherche et non
/// dans le tableau d'une famille.
pub fn membre(
    con: &Connection,
    membre_id: i64,
    exercice_id: Option<i64>,
    date_reference: Option<&str>,
) -> Result<Option<MembreResume>, Erreur> {
    Ok(
        rechercher_membres(con, Some(membre_id), None, exercice_id, date_reference, 1)?
            .into_iter()
            .next()
            .map(|trouve| trouve.membre),
    )
}
