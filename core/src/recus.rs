use rusqlite::{params, Connection};

use crate::erreur::Erreur;

/// Attribue le prochain numéro de reçu de l'année, dans la transaction en
/// cours. Le compteur ne redescend jamais : supprimer un paiement ne rend pas
/// son numéro disponible (décision D4).
pub fn numero_suivant(con: &Connection, annee: i32) -> Result<String, Erreur> {
    con.execute(
        "INSERT INTO sequences (nom, annee, dernier) VALUES ('recu', ?1, 0)
         ON CONFLICT(nom, annee) DO NOTHING",
        params![annee],
    )?;
    let suivant: i64 = con.query_row(
        "UPDATE sequences SET dernier = dernier + 1
          WHERE nom = 'recu' AND annee = ?1
      RETURNING dernier",
        params![annee],
        |l| l.get(0),
    )?;
    Ok(format!("RECU-{annee}-{suivant:06}"))
}
