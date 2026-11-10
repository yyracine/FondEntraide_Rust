use std::path::Path;

use rusqlite::Connection;

use crate::erreur::Erreur;

/// Version de schéma que ce crate sait lire et écrire.
pub const VERSION_SCHEMA: i64 = 2;

/// Ouvre la base, applique les PRAGMA et refuse un schéma inconnu.
///
/// `journal_mode = WAL` : les lectures ne bloquent pas l'écriture d'un reçu.
pub fn ouvrir(chemin: &Path) -> Result<Connection, Erreur> {
    let con = Connection::open(chemin)?;
    preparer(&con)?;
    Ok(con)
}

/// Ouvre une base déjà en mémoire et y applique les PRAGMA (tests unitaires).
pub fn preparer(con: &Connection) -> Result<(), Erreur> {
    con.execute_batch(
        "PRAGMA foreign_keys = ON;
         PRAGMA journal_mode = WAL;
         PRAGMA synchronous = NORMAL;",
    )?;
    let version: i64 = con.query_row("PRAGMA user_version", [], |l| l.get(0))?;
    if version != VERSION_SCHEMA {
        return Err(Erreur::SchemaIncompatible {
            trouve: version,
            attendu: VERSION_SCHEMA,
        });
    }
    Ok(())
}

/// Vérifications à faire au démarrage : intégrité, clés étrangères, et
/// l'invariant « montant total = somme des affectations ».
pub fn autodiagnostic(con: &Connection) -> Result<Vec<String>, Erreur> {
    let mut alertes = Vec::new();

    let integrite: String = con.query_row("PRAGMA integrity_check", [], |l| l.get(0))?;
    if integrite != "ok" {
        alertes.push(format!("intégrité de la base : {integrite}"));
    }

    let mut stmt = con.prepare("PRAGMA foreign_key_check")?;
    let orphelines = stmt.query_map([], |_| Ok(()))?.count();
    if orphelines > 0 {
        alertes.push(format!("{orphelines} clé(s) étrangère(s) orpheline(s)"));
    }
    drop(stmt);

    let incoherents: i64 =
        con.query_row("SELECT COUNT(*) FROM v_paiements_incoherents", [], |l| {
            l.get(0)
        })?;
    if incoherents > 0 {
        alertes.push(format!("{incoherents} paiement(s) incohérent(s)"));
    }

    let depassements: i64 =
        con.query_row("SELECT COUNT(*) FROM v_affectations_depassement", [], |l| {
            l.get(0)
        })?;
    if depassements > 0 {
        alertes.push(format!(
            "{depassements} mois réglé(s) au-delà du dû (historique importé)"
        ));
    }

    Ok(alertes)
}
