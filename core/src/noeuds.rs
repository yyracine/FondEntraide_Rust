//! Écriture de la hiérarchie : clan → grande famille → lignée → famille.
//!
//! Mêmes principes que pour les membres : un nom vide, un parent manquant, un
//! doublon ou une suppression qui laisserait des enfants sont refusés par une
//! `Erreur` lisible. Les noms de tables sont écrits en dur par branche, jamais
//! interpolés (P12 du registre des problèmes).

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::erreur::Erreur;

/// Niveau de la hiérarchie manipulé par le formulaire.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Niveau {
    Clan,
    GrandeFamille,
    Lignee,
    Famille,
}

impl Niveau {
    pub fn libelle(self) -> &'static str {
        match self {
            Niveau::Clan => "le clan",
            Niveau::GrandeFamille => "la grande famille",
            Niveau::Lignee => "la lignée",
            Niveau::Famille => "la famille",
        }
    }
}

fn compter(con: &Connection, requete: &str, id: i64) -> Result<i64, Erreur> {
    Ok(con.query_row(requete, params![id], |l| l.get(0))?)
}

fn existe(con: &Connection, requete: &str, id: i64) -> Result<bool, Erreur> {
    Ok(con.query_row(requete, params![id], |l| l.get(0))?)
}

/// Vrai si un frère porte déjà ce nom sous le même parent (comparaison sans
/// casse, comme les contraintes `UNIQUE ... COLLATE NOCASE` du schéma).
fn nom_pris(
    con: &Connection,
    niveau: Niveau,
    parent_id: Option<i64>,
    nom: &str,
    sauf: Option<i64>,
) -> Result<bool, Erreur> {
    let pris: bool = match niveau {
        Niveau::Clan => con.query_row(
            "SELECT EXISTS (SELECT 1 FROM clans
                             WHERE nom = ?1 COLLATE NOCASE AND id IS NOT ?2)",
            params![nom, sauf],
            |l| l.get(0),
        )?,
        Niveau::GrandeFamille => con.query_row(
            "SELECT EXISTS (SELECT 1 FROM grandes_familles
                             WHERE clan_id = ?1 AND nom = ?2 COLLATE NOCASE
                               AND id IS NOT ?3)",
            params![parent_id, nom, sauf],
            |l| l.get(0),
        )?,
        Niveau::Lignee => con.query_row(
            "SELECT EXISTS (SELECT 1 FROM lignees
                             WHERE grande_famille_id = ?1 AND nom = ?2 COLLATE NOCASE
                               AND id IS NOT ?3)",
            params![parent_id, nom, sauf],
            |l| l.get(0),
        )?,
        // L'historique contient deux familles homonymes dans une même lignée :
        // le schéma autorise les doublons, on ne les refuse donc pas ici.
        Niveau::Famille => false,
    };
    Ok(pris)
}

/// Crée un nœud sous `parent_id` (ignoré pour un clan) et renvoie son id.
pub fn creer(
    con: &mut Connection,
    niveau: Niveau,
    parent_id: Option<i64>,
    nom: &str,
) -> Result<i64, Erreur> {
    let nom = nom.trim();
    if nom.is_empty() {
        return Err(Erreur::ChampRequis(niveau.libelle()));
    }
    if nom_pris(con, niveau, parent_id, nom, None)? {
        return Err(Erreur::NomDejaPris(nom.to_string()));
    }

    let tx = con.transaction()?;
    let id = match niveau {
        Niveau::Clan => {
            tx.execute("INSERT INTO clans (nom) VALUES (?1)", params![nom])?;
            tx.last_insert_rowid()
        }
        Niveau::GrandeFamille => {
            let parent = parent_id.ok_or(Erreur::ChampRequis("le clan"))?;
            if !existe(
                &tx,
                "SELECT EXISTS (SELECT 1 FROM clans WHERE id = ?1)",
                parent,
            )? {
                return Err(Erreur::NoeudInconnu("le clan", parent));
            }
            tx.execute(
                "INSERT INTO grandes_familles (clan_id, nom) VALUES (?1, ?2)",
                params![parent, nom],
            )?;
            tx.last_insert_rowid()
        }
        Niveau::Lignee => {
            let parent = parent_id.ok_or(Erreur::ChampRequis("la grande famille"))?;
            if !existe(
                &tx,
                "SELECT EXISTS (SELECT 1 FROM grandes_familles WHERE id = ?1)",
                parent,
            )? {
                return Err(Erreur::NoeudInconnu("la grande famille", parent));
            }
            tx.execute(
                "INSERT INTO lignees (grande_famille_id, nom) VALUES (?1, ?2)",
                params![parent, nom],
            )?;
            tx.last_insert_rowid()
        }
        Niveau::Famille => {
            let parent = parent_id.ok_or(Erreur::ChampRequis("la lignée"))?;
            if !existe(
                &tx,
                "SELECT EXISTS (SELECT 1 FROM lignees WHERE id = ?1)",
                parent,
            )? {
                return Err(Erreur::NoeudInconnu("la lignée", parent));
            }
            tx.execute(
                "INSERT INTO familles (lignee_id, nom) VALUES (?1, ?2)",
                params![parent, nom],
            )?;
            tx.last_insert_rowid()
        }
    };
    tx.commit()?;
    Ok(id)
}

/// Renomme un nœud. Le niveau ne change pas : déplacer une famille de lignée
/// serait une autre opération, avec ses propres conséquences.
pub fn renommer(con: &mut Connection, niveau: Niveau, id: i64, nom: &str) -> Result<(), Erreur> {
    let nom = nom.trim();
    if nom.is_empty() {
        return Err(Erreur::ChampRequis(niveau.libelle()));
    }
    let parent_id: Option<i64> = match niveau {
        Niveau::Clan => None,
        Niveau::GrandeFamille => con
            .query_row(
                "SELECT clan_id FROM grandes_familles WHERE id = ?1",
                params![id],
                |l| l.get(0),
            )
            .optional()?,
        Niveau::Lignee => con
            .query_row(
                "SELECT grande_famille_id FROM lignees WHERE id = ?1",
                params![id],
                |l| l.get(0),
            )
            .optional()?,
        Niveau::Famille => con
            .query_row(
                "SELECT lignee_id FROM familles WHERE id = ?1",
                params![id],
                |l| l.get(0),
            )
            .optional()?,
    };
    if niveau != Niveau::Clan && parent_id.is_none() {
        return Err(Erreur::NoeudInconnu(niveau.libelle(), id));
    }
    if nom_pris(con, niveau, parent_id, nom, Some(id))? {
        return Err(Erreur::NomDejaPris(nom.to_string()));
    }

    let modifies = match niveau {
        Niveau::Clan => con.execute("UPDATE clans SET nom = ?2 WHERE id = ?1", params![id, nom])?,
        Niveau::GrandeFamille => con.execute(
            "UPDATE grandes_familles SET nom = ?2 WHERE id = ?1",
            params![id, nom],
        )?,
        Niveau::Lignee => con.execute(
            "UPDATE lignees SET nom = ?2 WHERE id = ?1",
            params![id, nom],
        )?,
        Niveau::Famille => con.execute(
            "UPDATE familles SET nom = ?2 WHERE id = ?1",
            params![id, nom],
        )?,
    };
    if modifies == 0 {
        return Err(Erreur::NoeudInconnu(niveau.libelle(), id));
    }
    Ok(())
}

/// Supprime un nœud vide. Un clan qui porte encore des grandes familles, une
/// famille qui porte encore des membres : refus, avec le décompte.
pub fn supprimer(con: &mut Connection, niveau: Niveau, id: i64) -> Result<(), Erreur> {
    let tx = con.transaction()?;

    let (enfants, quoi) = match niveau {
        Niveau::Clan => (
            compter(
                &tx,
                "SELECT COUNT(*) FROM grandes_familles WHERE clan_id = ?1",
                id,
            )?,
            "grande(s) famille(s)",
        ),
        Niveau::GrandeFamille => (
            compter(
                &tx,
                "SELECT COUNT(*) FROM lignees WHERE grande_famille_id = ?1",
                id,
            )?,
            "lignée(s)",
        ),
        Niveau::Lignee => (
            compter(
                &tx,
                "SELECT COUNT(*) FROM familles WHERE lignee_id = ?1",
                id,
            )?,
            "famille(s)",
        ),
        Niveau::Famille => (
            compter(
                &tx,
                "SELECT COUNT(*) FROM membres WHERE famille_id = ?1",
                id,
            )?,
            "membre(s)",
        ),
    };
    if enfants > 0 {
        return Err(Erreur::SuppressionRefusee(format!(
            "{} contient encore {enfants} {quoi}",
            niveau.libelle()
        )));
    }

    let supprimes = match niveau {
        Niveau::Clan => tx.execute("DELETE FROM clans WHERE id = ?1", params![id])?,
        Niveau::GrandeFamille => {
            tx.execute("DELETE FROM grandes_familles WHERE id = ?1", params![id])?
        }
        Niveau::Lignee => tx.execute("DELETE FROM lignees WHERE id = ?1", params![id])?,
        Niveau::Famille => tx.execute("DELETE FROM familles WHERE id = ?1", params![id])?,
    };
    if supprimes == 0 {
        return Err(Erreur::NoeudInconnu(niveau.libelle(), id));
    }
    tx.commit()?;
    Ok(())
}
