//! La base de démonstration doit être utilisable telle quelle : schéma v2,
//! montants cohérents, soldes lisibles, aucune clé étrangère orpheline.

use fonds_core::demo;

#[test]
fn la_base_de_demonstration_est_coherente() {
    let dir = tempfile::tempdir().expect("dossier temporaire");
    let chemin = dir.path().join("demo.db");
    let con = demo::creer(&chemin).expect("base de démonstration");

    let version: i64 = con
        .query_row("PRAGMA user_version", [], |l| l.get(0))
        .expect("version");
    assert_eq!(version, 2, "le schéma embarqué est celui de production");

    let integrite: String = con
        .query_row("PRAGMA integrity_check", [], |l| l.get(0))
        .expect("intégrité");
    assert_eq!(integrite, "ok");

    let compter = |table: &str| -> i64 {
        con.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |l| l.get(0))
            .expect("comptage")
    };

    assert_eq!(compter("clans"), 2);
    assert_eq!(compter("familles"), 5);
    assert!(compter("membres") >= 12, "une démo a de quoi cliquer");
    assert_eq!(compter("exercices"), 2);
    assert_eq!(compter("echeances"), 24);

    let mut stmt = con.prepare("PRAGMA foreign_key_check").expect("contrôle");
    assert_eq!(
        stmt.query_map([], |_| Ok(())).expect("lecture").count(),
        0,
        "aucune clé étrangère orpheline"
    );
    drop(stmt);

    assert_eq!(compter("v_paiements_incoherents"), 0);
    assert!(compter("paiements") >= 3, "des versements d'exemple");
    let total: i64 = con
        .query_row("SELECT SUM(montant_total) FROM paiements", [], |l| l.get(0))
        .expect("total");
    let affecte: i64 = con
        .query_row("SELECT SUM(montant) FROM affectations", [], |l| l.get(0))
        .expect("affectations");
    assert_eq!(total, affecte, "montant total = somme des affectations");

    // Les soldes se lisent : tout n'est pas payé, tout n'est pas dû non plus.
    let paye: i64 = con
        .query_row("SELECT SUM(paye) FROM v_echeance_membre", [], |l| l.get(0))
        .expect("payé");
    let reste: i64 = con
        .query_row("SELECT SUM(reste) FROM v_echeance_membre", [], |l| l.get(0))
        .expect("reste");
    assert!(paye > 0, "la démo montre des cotisations réglées");
    assert!(reste > 0, "et des restes à payer");
}
