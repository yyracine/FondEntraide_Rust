//! La purge doit vider exactement la portée demandée, laisser les exercices et
//! leurs tarifs en place, ne jamais réattribuer un numéro de reçu, et toujours
//! partir d'une copie de sécurité vérifiée.

use std::path::PathBuf;

use fonds_core::{db, purge, sauvegardes, Erreur};
use rusqlite::Connection;

fn base() -> (tempfile::TempDir, Connection) {
    let dir = tempfile::tempdir().expect("dossier temporaire");
    let chemin = dir.path().join("cotisations.db");
    let source = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("racine du projet")
        .join("cotisations_v2.db");
    std::fs::copy(&source, &chemin).unwrap_or_else(|e| {
        panic!(
            "copie de {} impossible ({e}) : lancer `python migrer_v2.py` d'abord",
            source.display()
        )
    });
    (dir, db::ouvrir(&chemin).expect("ouverture"))
}

fn compte(con: &Connection, table: &str) -> i64 {
    con.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |l| l.get(0))
        .expect("comptage")
}

#[test]
fn purger_les_cotisations_garde_hierarchie_et_exercices() {
    let (_dir, con) = base();
    let reçus = compte(&con, "sequences");

    let bilan = purge::purger(&con, purge::Portee::Cotisations).expect("purge");

    assert_eq!(bilan.paiements, 227, "tous les versements de l'historique");
    assert!(
        bilan.affectations >= bilan.paiements,
        "les affectations partent avec"
    );
    assert_eq!((bilan.membres, bilan.clans), (0, 0), "la hiérarchie reste");

    assert_eq!(compte(&con, "paiements"), 0);
    assert_eq!(compte(&con, "affectations"), 0);
    assert_eq!(compte(&con, "membres"), 599);
    assert_eq!(compte(&con, "familles"), 391);
    assert_eq!(compte(&con, "clans"), 7);
    assert_eq!(compte(&con, "exercices"), 3, "les exercices restent");
    assert_eq!(compte(&con, "echeances"), 36, "les échéances restent");
    assert_eq!(
        compte(&con, "sequences"),
        reçus,
        "les numéros de reçus restent consommés"
    );

    let encore_reglees: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM v_echeance_membre WHERE paye > 0",
            [],
            |l| l.get(0),
        )
        .expect("soldes");
    assert_eq!(encore_reglees, 0, "toutes les échéances redeviennent dues");

    let orphelines: i64 = con
        .query_row("SELECT COUNT(*) FROM v_paiements_incoherents", [], |l| {
            l.get(0)
        })
        .expect("cohérence");
    assert_eq!(orphelines, 0);
}

#[test]
fn purger_la_hierarchie_efface_aussi_les_versements() {
    let (_dir, con) = base();
    let reçus = compte(&con, "sequences");

    let bilan = purge::purger(&con, purge::Portee::Hierarchie).expect("purge");
    assert_eq!(bilan.membres, 599);
    assert_eq!(bilan.clans, 7);
    assert!(
        bilan.paiements > 0,
        "les versements partent avec leurs membres"
    );

    for table in [
        "membres",
        "familles",
        "lignees",
        "grandes_familles",
        "clans",
        "paiements",
        "affectations",
    ] {
        assert_eq!(compte(&con, table), 0, "{table} doit être vide");
    }
    assert_eq!(compte(&con, "exercices"), 3, "le calendrier reste");
    assert_eq!(compte(&con, "sequences"), reçus, "aucun reçu réattribué");

    let mut stmt = con.prepare("PRAGMA foreign_key_check").expect("contrôle");
    assert_eq!(stmt.query_map([], |_| Ok(())).expect("lecture").count(), 0);
}

#[test]
fn purger_tout_laisse_une_base_vide_mais_utilisable() {
    let (_dir, con) = base();

    let bilan = purge::purger(&con, purge::Portee::Tout).expect("purge");
    assert_eq!((bilan.membres, bilan.clans), (599, 7));
    assert_eq!(bilan.paiements, 227);

    assert_eq!(compte(&con, "membres"), 0);
    assert_eq!(compte(&con, "paiements"), 0);
    assert_eq!(compte(&con, "exercices"), 3);
    assert_eq!(compte(&con, "echeances"), 36);

    let integrite: String = con
        .query_row("PRAGMA integrity_check", [], |l| l.get(0))
        .expect("intégrité");
    assert_eq!(integrite, "ok");
}

#[test]
fn purger_apres_copie_ecrit_une_sauvegarde_verifiee() {
    let (dir, con) = base();
    let chemin = dir.path().join("cotisations.db");

    let faite = purge::purger_apres_copie(&con, &chemin, purge::Portee::Cotisations)
        .expect("purge avec copie");

    assert!(faite.copie.nom.starts_with("cotisations_"));
    assert!(faite.copie.octets > 0);
    let copies = sauvegardes::lister(&chemin).expect("liste des copies");
    assert_eq!(copies.len(), 1, "la copie précède la purge");
    assert_eq!(compte(&con, "paiements"), 0, "la purge a bien eu lieu");
}

#[test]
fn portee_inconnue_refusee() {
    let erreur = purge::Portee::depuis("tout_effacer").expect_err("portée refusée");
    assert!(matches!(erreur, Erreur::PurgeRefusee(_)));
}
