//! Sauvegarde et restauration de la base.
//!
//! La copie passe par `VACUUM INTO`, pas par une copie de fichier : avec le
//! journal `-wal`, un `cp` du seul `.db` produit une base incohérente — c'est
//! précisément ce qui a déjà rendu la base de travail illisible. La
//! restauration vérifie la copie (intégrité et version de schéma) **avant** de
//! toucher à la base vivante, puis écrit par l'API de sauvegarde de SQLite,
//! sans fermer la connexion de l'application.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::backup::Backup;
use rusqlite::{params, Connection, OpenFlags};
use serde::Serialize;

use crate::erreur::Erreur;

/// Version de schéma attendue dans un fichier restaurable (`schema_v2.sql`).
const SCHEMA_VERSION: i64 = 2;

/// Nombre de copies conservées. Au-delà, les plus anciennes sont effacées à
/// chaque nouvelle sauvegarde : le dossier ne grossit pas sans fin.
pub const COPIES_CONSERVEES: usize = 5;

/// Une copie de la base, telle que l'écran des sauvegardes la liste.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Sauvegarde {
    pub nom: String,
    pub chemin: String,
    pub octets: i64,
}

/// Dossier des sauvegardes : à côté de la base, jamais dans git.
pub fn dossier(base: &Path) -> PathBuf {
    base.parent()
        .unwrap_or_else(|| Path::new("."))
        .join("sauvegardes")
}

/// Vérifie qu'un nom désigne bien une sauvegarde du dossier, sans traversée de
/// chemin : le nom vient de l'interface.
pub fn chemin_de(base: &Path, nom: &str) -> Result<PathBuf, Erreur> {
    if nom.contains('/') || nom.contains('\\') || nom.contains("..") || !nom.ends_with(".db") {
        return Err(Erreur::RestaurationRefusee(format!(
            "nom de sauvegarde invalide : {nom}"
        )));
    }
    let chemin = dossier(base).join(nom);
    if !chemin.is_file() {
        return Err(Erreur::RestaurationRefusee(format!(
            "sauvegarde introuvable : {nom}"
        )));
    }
    Ok(chemin)
}

fn taille(chemin: &Path) -> i64 {
    fs::metadata(chemin)
        .map(|m| m.len() as i64)
        .unwrap_or_default()
}

/// Vrai pour les copies écrites par l'application :
/// `cotisations_AAAA-MM-JJ_HH-MM-SS.db`, avec un suffixe `_2`, `_3`… si deux
/// copies tombent dans la même seconde. Sert à ne jamais effacer un fichier
/// déposé là par un autre outil.
fn est_copie_de_l_application(nom: &str) -> bool {
    let Some(reste) = nom.strip_prefix("cotisations_") else {
        return false;
    };
    let Some(reste) = reste.strip_suffix(".db") else {
        return false;
    };
    let octets = reste.as_bytes();
    if octets.len() < 19 {
        return false;
    }
    for i in [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18] {
        if !octets[i].is_ascii_digit() {
            return false;
        }
    }
    if octets[4] != b'-'
        || octets[7] != b'-'
        || octets[10] != b'_'
        || octets[13] != b'-'
        || octets[16] != b'-'
    {
        return false;
    }
    let queue = &reste[19..];
    queue.is_empty()
        || (queue.starts_with('_')
            && queue.len() > 1
            && queue.as_bytes()[1..].iter().all(u8::is_ascii_digit))
}

/// Ouvre une copie en lecture seule et s'assure qu'elle est saine et au bon
/// format. Une sauvegarde abîmée ou issue de la base v1 est refusée.
fn verifier(chemin: &Path) -> Result<(), Erreur> {
    let con = Connection::open_with_flags(chemin, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|e| Erreur::RestaurationRefusee(format!("copie illisible : {e}")))?;

    let integrite: String = con
        .query_row("PRAGMA integrity_check", [], |l| l.get(0))
        .map_err(|e| Erreur::RestaurationRefusee(format!("vérification impossible : {e}")))?;
    if integrite != "ok" {
        return Err(Erreur::RestaurationRefusee(format!(
            "copie abîmée ({integrite})"
        )));
    }

    let version: i64 = con.query_row("PRAGMA user_version", [], |l| l.get(0))?;
    if version != SCHEMA_VERSION {
        return Err(Erreur::RestaurationRefusee(format!(
            "schéma {version} dans cette copie, {SCHEMA_VERSION} attendu — repassez par migrer_v2.py"
        )));
    }
    Ok(())
}

/// Crée une copie cohérente de la base ouverte et vérifie qu'elle se relit.
pub fn sauvegarder(con: &Connection, base: &Path) -> Result<Sauvegarde, Erreur> {
    let dossier = dossier(base);
    fs::create_dir_all(&dossier)
        .map_err(|e| Erreur::SauvegardeEchouee(format!("dossier impossible : {e}")))?;

    let instant: String = con.query_row(
        "SELECT strftime('%Y-%m-%d_%H-%M-%S', 'now', 'localtime')",
        [],
        |l| l.get(0),
    )?;
    let mut cible = dossier.join(format!("cotisations_{instant}.db"));
    let mut suffixe = 2;
    while cible.exists() {
        cible = dossier.join(format!("cotisations_{instant}_{suffixe}.db"));
        suffixe += 1;
    }

    let chemin = cible.to_string_lossy().to_string();
    con.execute("VACUUM INTO ?1", params![chemin])
        .map_err(|e| Erreur::SauvegardeEchouee(format!("copie impossible : {e}")))?;

    // Une copie qu'on ne sait pas relire ne vaut rien : on l'efface.
    if let Err(erreur) = verifier(&cible) {
        let _ = fs::remove_file(&cible);
        return Err(erreur);
    }

    Ok(Sauvegarde {
        nom: cible
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default(),
        chemin,
        octets: taille(&cible),
    })
}

/// Copies de l'application, de la plus récente à la plus ancienne.
///
/// Seules les copies au format de l'application sont listées : les archives
/// déposées dans le dossier par l'ancienne version Python relèvent d'un autre
/// schéma, ne peuvent pas être restaurées, et n'ont rien à faire à l'écran.
/// Le nom porte la date et l'heure : l'ordre alphabétique suffit.
pub fn lister(base: &Path) -> Result<Vec<Sauvegarde>, Erreur> {
    let dossier = dossier(base);
    let mut resultat = Vec::new();
    let Ok(entrees) = fs::read_dir(&dossier) else {
        return Ok(resultat);
    };

    for entree in entrees.flatten() {
        let nom = entree.file_name().to_string_lossy().to_string();
        if !est_copie_de_l_application(&nom) {
            continue;
        }
        let chemin = entree.path();
        resultat.push(Sauvegarde {
            nom,
            chemin: chemin.to_string_lossy().to_string(),
            octets: taille(&chemin),
        });
    }
    resultat.sort_by(|a, b| b.nom.cmp(&a.nom));
    Ok(resultat)
}

/// Efface les copies de l'application au-delà des plus récentes. Un fichier
/// déposé dans le dossier par un autre outil n'est jamais touché ; il n'est
/// même pas vu. Renvoie le nombre de fichiers effacés — un fichier encore
/// ouvert résiste, il reste.
pub fn purger(base: &Path) -> Result<usize, Erreur> {
    let mut effacees = 0;
    for copie in lister(base)?.into_iter().skip(COPIES_CONSERVEES) {
        if fs::remove_file(&copie.chemin).is_ok() {
            effacees += 1;
        }
    }
    Ok(effacees)
}

/// Restaure une copie dans la base vivante.
///
/// L'état actuel est d'abord sauvegardé : une restauration est une opération
/// qu'on ne doit pas pouvoir regretter sans filet. La copie est vérifiée avant
/// toute écriture, puis réinjectée par l'API de sauvegarde de SQLite.
pub fn restaurer(con: &mut Connection, chemin: &Path, base: &Path) -> Result<Sauvegarde, Erreur> {
    verifier(chemin)?;
    let secours = sauvegarder(con, base)?;

    let source = Connection::open_with_flags(chemin, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|e| Erreur::RestaurationRefusee(format!("copie illisible : {e}")))?;
    {
        let backup = Backup::new(&source, con)
            .map_err(|e| Erreur::RestaurationRefusee(format!("restauration impossible : {e}")))?;
        backup
            .run_to_completion(100, Duration::from_millis(0), None)
            .map_err(|e| Erreur::RestaurationRefusee(format!("écriture interrompue : {e}")))?;
    }
    drop(source);

    let integrite: String = con.query_row("PRAGMA integrity_check", [], |l| l.get(0))?;
    if integrite != "ok" {
        return Err(Erreur::RestaurationRefusee(format!(
            "la base restaurée ne passe pas l'intégrité ({integrite}) — copie de sécurité : {}",
            secours.nom
        )));
    }

    // Une restauration ajoute une copie (celle de sécurité) : on garde la
    // borne. Le fichier vient d'être refermé, il peut donc être effacé.
    let _ = purger(base);
    Ok(secours)
}
