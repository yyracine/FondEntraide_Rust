//! Base de démonstration : une base neuve, remplie de données fictives, pour
//! essayer l'application sans approcher les données réelles.
//!
//! Le schéma utilisé est celui de `schema_v2.sql`, embarqué à la compilation :
//! la démonstration ne peut pas dériver du schéma de production. Les versements
//! passent par `ventilation::ventiler`, donc la démo respecte exactement les
//! mêmes règles d'argent (cascade, plafond du dû, numéro de reçu) que la base
//! réelle — une démonstration qui mentirait sur les soldes ne servirait à rien.

use std::path::Path;

use chrono::NaiveDate;
use rusqlite::{params, Connection, Transaction};

use crate::erreur::Erreur;

/// Le schéma de production, embarqué : une seule source de vérité.
const SCHEMA: &str = include_str!("../../schema_v2.sql");

/// Crée une base de démonstration neuve à `chemin` (le fichier doit être
/// absent) et la remplit. Renvoie la connexion ouverte, prête pour l'app.
pub fn creer(chemin: &Path) -> Result<Connection, Erreur> {
    let mut con = Connection::open(chemin)?;
    con.execute_batch(SCHEMA)?;
    remplir(&mut con)?;
    crate::db::preparer(&con)?;
    Ok(con)
}

fn clan(tx: &Transaction<'_>, nom: &str) -> Result<i64, Erreur> {
    tx.execute("INSERT INTO clans (nom) VALUES (?1)", params![nom])?;
    Ok(tx.last_insert_rowid())
}

fn grande_famille(tx: &Transaction<'_>, clan_id: i64, nom: &str) -> Result<i64, Erreur> {
    tx.execute(
        "INSERT INTO grandes_familles (clan_id, nom) VALUES (?1, ?2)",
        params![clan_id, nom],
    )?;
    Ok(tx.last_insert_rowid())
}

fn lignee(tx: &Transaction<'_>, grande_famille_id: i64, nom: &str) -> Result<i64, Erreur> {
    tx.execute(
        "INSERT INTO lignees (grande_famille_id, nom) VALUES (?1, ?2)",
        params![grande_famille_id, nom],
    )?;
    Ok(tx.last_insert_rowid())
}

fn famille(tx: &Transaction<'_>, lignee_id: i64, nom: &str) -> Result<i64, Erreur> {
    tx.execute(
        "INSERT INTO familles (lignee_id, nom) VALUES (?1, ?2)",
        params![lignee_id, nom],
    )?;
    Ok(tx.last_insert_rowid())
}

fn membre(
    tx: &Transaction<'_>,
    famille_id: i64,
    nom: &str,
    prenom: Option<&str>,
    parent: Option<i64>,
) -> Result<i64, Erreur> {
    tx.execute(
        "INSERT INTO membres (famille_id, parent_id, nom, prenom, statut)
         VALUES (?1, ?2, ?3, ?4, 'actif')",
        params![famille_id, parent, nom, prenom],
    )?;
    Ok(tx.last_insert_rowid())
}

/// Un exercice sur l'année civile, avec ses douze échéances au 1er du mois.
fn exercice(tx: &Transaction<'_>, libelle: &str, annee: i32, montant: i64) -> Result<i64, Erreur> {
    tx.execute(
        "INSERT INTO exercices (libelle, date_debut, date_fin, montant_mensuel)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            libelle,
            format!("{annee}-01-01"),
            format!("{annee}-12-31"),
            montant
        ],
    )?;
    let id = tx.last_insert_rowid();

    for mois in 1..=12 {
        tx.execute(
            "INSERT INTO echeances (exercice_id, annee, mois, date_echeance, montant_du)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, annee, mois, format!("{annee}-{mois:02}-01"), montant],
        )?;
    }
    Ok(id)
}

fn jour(annee: i32, mois: u32, jour: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(annee, mois, jour).expect("date de démonstration valide")
}

/// Hiérarchie, exercices, membres, puis quelques versements réels.
fn remplir(con: &mut Connection) -> Result<(), Erreur> {
    let (chef, epouse, akesse, ex_2025, ex_2026) = {
        let tx = con.transaction()?;

        let adjoua = clan(&tx, "ADJOUA MALA")?;
        let yaocre = clan(&tx, "YAOCRE")?;

        let ablan = grande_famille(&tx, adjoua, "ABLAN BREMA")?;
        let sewa = grande_famille(&tx, adjoua, "ADJOUA SEWA")?;
        let appia = grande_famille(&tx, yaocre, "YAOCRE APPIA")?;

        let l_ablan = lignee(&tx, ablan, "ABLAN BREMA")?;
        let l_sewa = lignee(&tx, sewa, "ADJOUA SEWA")?;
        let l_appia = lignee(&tx, appia, "YAOCRE APPIA")?;

        let f_ablan = famille(&tx, l_ablan, "Ablan")?;
        let f_cadets = famille(&tx, l_ablan, "Ablan cadets")?;
        let f_sewa = famille(&tx, l_sewa, "Sewa")?;
        let f_akesse = famille(&tx, l_appia, "Akesse Comoé")?;
        let f_mian = famille(&tx, l_appia, "Mian Faustine")?;

        // Des liens de parenté réels : la fiche a quelque chose à montrer.
        let chef = membre(&tx, f_ablan, "Ablan", Some("Kouadio"), None)?;
        let epouse = membre(&tx, f_ablan, "Ablan", Some("Adjoua"), None)?;
        membre(&tx, f_ablan, "Ablan", Some("Yao"), Some(chef))?;
        membre(&tx, f_ablan, "Ablan", Some("Akissi"), Some(chef))?;
        membre(&tx, f_ablan, "Ablan", Some("Konan"), Some(epouse))?;
        membre(&tx, f_cadets, "Ablan", Some("Sylvain"), None)?;
        membre(&tx, f_cadets, "Ablan", None, None)?;
        membre(&tx, f_sewa, "Adjoua", Some("Séwa"), None)?;
        membre(&tx, f_sewa, "Adjoua", Some("Mariam"), None)?;
        let akesse = membre(&tx, f_akesse, "Akesse", Some("Comoé"), None)?;
        membre(&tx, f_akesse, "Akesse", Some("Béatrice"), Some(akesse))?;
        membre(&tx, f_akesse, "Akesse", Some("Jean"), Some(akesse))?;
        membre(&tx, f_mian, "Mian", Some("Faustine"), None)?;
        membre(&tx, f_mian, "Mian", Some("Serge"), None)?;
        membre(&tx, f_mian, "Mian", None, None)?;

        let ex_2025 = exercice(&tx, "Campagne 2025", 2025, 1_000)?;
        let ex_2026 = exercice(&tx, "Campagne 2026", 2026, 1_000)?;

        tx.commit()?;
        (chef, epouse, akesse, ex_2025, ex_2026)
    };

    // Trois profils : à jour, en retard, partiellement payé.
    crate::ventilation::ventiler(con, chef, ex_2025, 12_000, jour(2025, 12, 15), "especes")?;
    crate::ventilation::ventiler(
        con,
        epouse,
        ex_2025,
        5_000,
        jour(2025, 11, 20),
        "mobile_money",
    )?;
    crate::ventilation::ventiler(con, akesse, ex_2025, 3_000, jour(2025, 10, 5), "especes")?;
    crate::ventilation::ventiler(con, chef, ex_2026, 2_000, jour(2026, 3, 5), "especes")?;
    crate::ventilation::ventiler(con, akesse, ex_2026, 1_000, jour(2026, 2, 10), "virement")?;

    Ok(())
}
