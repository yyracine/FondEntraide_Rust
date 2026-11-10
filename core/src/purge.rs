//! Purge de la base : repartir d'un état vide, sans jamais perdre ce qui a été
//! sauvegardé.
//!
//! Trois portées, toutes confirmées deux fois dans l'interface et toujours
//! précédées d'une copie de sécurité (`sauvegardes::sauvegarder`) :
//! * `Cotisations` : efface versements et affectations ; la hiérarchie et les
//!   exercices restent, toutes les échéances redeviennent dues ;
//! * `Hierarchie` : efface membres, familles, lignées, grandes familles et
//!   clans — donc leurs versements, que les clés étrangères interdiraient de
//!   laisser derrière ;
//! * `Tout` : les deux.
//!
//! Ce qui n'est **jamais** effacé : les exercices et leurs échéances (le
//! calendrier et les tarifs restent), et les compteurs de reçus déjà consommés
//! — la décision D4 interdit de réattribuer un numéro, même après une purge.
//!
//! Un seul membre doit être supprimé avant son parent : la clé étrangère
//! `parent_id` est en `RESTRICT`, donc on détache d'abord les liens de
//! parenté, puis on vide la table en une fois.

use rusqlite::{Connection, Transaction};
use serde::Serialize;

use crate::erreur::Erreur;
use crate::sauvegardes::Sauvegarde;

/// Ce que la purge doit effacer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Portee {
    Cotisations,
    Hierarchie,
    Tout,
}

impl Portee {
    /// Lit la portée envoyée par l'interface. Toute autre valeur est refusée :
    /// une faute de frappe ne doit pas vider la mauvaise chose.
    pub fn depuis(texte: &str) -> Result<Self, Erreur> {
        match texte {
            "cotisations" => Ok(Self::Cotisations),
            "hierarchie" => Ok(Self::Hierarchie),
            "tout" => Ok(Self::Tout),
            autre => Err(Erreur::PurgeRefusee(format!(
                "portée de purge inconnue : {autre}"
            ))),
        }
    }
}

/// Nombre de lignes effacées, par table. On ne dit pas « purge effectuée » :
/// on dit ce qui est parti, pour que l'utilisateur puisse le vérifier.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Bilan {
    pub paiements: i64,
    pub affectations: i64,
    pub membres: i64,
    pub familles: i64,
    pub lignees: i64,
    pub grandes_familles: i64,
    pub clans: i64,
}

/// Une purge et la copie de sécurité prise juste avant.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Purge {
    pub copie: Sauvegarde,
    pub bilan: Bilan,
}

fn compter(tx: &Transaction<'_>, table: &str) -> Result<i64, Erreur> {
    // `table` vient d'une liste fermée de ce module, jamais de l'interface.
    Ok(tx.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |l| l.get(0))?)
}

/// Efface la portée demandée dans une seule transaction : soit tout part, soit
/// rien ne bouge. Le bilan compte les lignes réellement supprimées.
pub fn purger(con: &Connection, portee: Portee) -> Result<Bilan, Erreur> {
    let tx = con.unchecked_transaction()?;

    // Les trois portées effacent les versements : une hiérarchie ne peut pas
    // partir avant eux (`paiements.membre_id` est en RESTRICT).
    let affectations = compter(&tx, "affectations")?;
    let paiements = compter(&tx, "paiements")?;
    tx.execute("DELETE FROM affectations", [])?;
    tx.execute("DELETE FROM paiements", [])?;

    let (membres, familles, lignees, grandes_familles, clans) =
        if matches!(portee, Portee::Hierarchie | Portee::Tout) {
            let comptes = (
                compter(&tx, "membres")?,
                compter(&tx, "familles")?,
                compter(&tx, "lignees")?,
                compter(&tx, "grandes_familles")?,
                compter(&tx, "clans")?,
            );

            // Un parent ne peut pas partir avant ses descendants (RESTRICT) :
            // on détache les liens, puis la table se vide d'un coup.
            tx.execute("UPDATE membres SET parent_id = NULL", [])?;
            tx.execute("DELETE FROM membres", [])?;
            tx.execute("DELETE FROM familles", [])?;
            tx.execute("DELETE FROM lignees", [])?;
            tx.execute("DELETE FROM grandes_familles", [])?;
            tx.execute("DELETE FROM clans", [])?;
            comptes
        } else {
            (0, 0, 0, 0, 0)
        };

    tx.commit()?;
    Ok(Bilan {
        paiements,
        affectations,
        membres,
        familles,
        lignees,
        grandes_familles,
        clans,
    })
}

/// Copie de sécurité, puis purge. La copie est écrite et **vérifiée** avant
/// toute suppression : si elle échoue, la base reste intacte.
pub fn purger_apres_copie(
    con: &Connection,
    base: &std::path::Path,
    portee: Portee,
) -> Result<Purge, Erreur> {
    let copie = crate::sauvegardes::sauvegarder(con, base)?;
    let bilan = purger(con, portee)?;
    Ok(Purge { copie, bilan })
}
