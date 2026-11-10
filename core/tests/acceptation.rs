//! Tests d'acceptation du §5.2 de `PLAN_MIGRATION_RUST.md`.
//!
//! Chaque test travaille sur une **copie** de `cotisations_v2.db` : la base
//! migrée n'est jamais modifiée. Si elle manque, lancer `python migrer_v2.py`.

use std::path::PathBuf;

use chrono::{Datelike, NaiveDate};
use fonds_core::{db, erreur::Erreur, ventilation};
use rusqlite::{params, Connection};

struct Base {
    _dir: tempfile::TempDir,
    chemin: PathBuf,
}

fn base() -> Base {
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
    Base { _dir: dir, chemin }
}

fn ouvrir(b: &Base) -> Connection {
    db::ouvrir(&b.chemin).expect("ouverture de la base migrée")
}

fn jour(a: i32, m: u32, j: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(a, m, j).expect("date valide")
}

fn premiere_famille(con: &Connection) -> i64 {
    con.query_row("SELECT id FROM familles ORDER BY id LIMIT 1", [], |l| {
        l.get(0)
    })
    .unwrap()
}

fn creer_membre(
    con: &Connection,
    famille_id: i64,
    nom: &str,
    entree: Option<&str>,
    sortie: Option<&str>,
) -> i64 {
    con.execute(
        "INSERT INTO membres (famille_id, nom, prenom, statut, date_entree, date_sortie)
         VALUES (?1, ?2, 'Test', 'actif', ?3, ?4)",
        params![famille_id, nom, entree, sortie],
    )
    .unwrap();
    con.last_insert_rowid()
}

/// Crée un exercice et matérialise ses échéances, mois par mois.
fn creer_exercice(
    con: &Connection,
    libelle: &str,
    debut: NaiveDate,
    fin: NaiveDate,
    montant: i64,
) -> rusqlite::Result<i64> {
    con.execute(
        "INSERT INTO exercices (libelle, date_debut, date_fin, montant_mensuel)
         VALUES (?1, ?2, ?3, ?4)",
        params![libelle, debut.to_string(), fin.to_string(), montant],
    )?;
    let id = con.last_insert_rowid();

    let (mut annee, mut mois) = (debut.year(), debut.month());
    while (annee, mois) <= (fin.year(), fin.month()) {
        let premier = NaiveDate::from_ymd_opt(annee, mois, 1).unwrap();
        let date = if premier < debut { debut } else { premier };
        con.execute(
            "INSERT INTO echeances (exercice_id, annee, mois, date_echeance, montant_du)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, annee, mois, date.to_string(), montant],
        )?;
        mois += 1;
        if mois == 13 {
            mois = 1;
            annee += 1;
        }
    }
    Ok(id)
}

// ------------------------------------------------------------------
//  1. Les goldens de l'historique survivent-ils à la réécriture ?
// ------------------------------------------------------------------
#[test]
fn les_goldens_de_l_historique_sont_preserves() {
    let b = base();
    let con = ouvrir(&b);

    let compte = |table: &str| -> i64 {
        con.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |l| l.get(0))
            .unwrap()
    };
    assert_eq!(compte("clans"), 7);
    assert_eq!(compte("grandes_familles"), 46);
    assert_eq!(compte("lignees"), 46);
    assert_eq!(compte("familles"), 391);
    assert_eq!(compte("membres"), 599);
    assert_eq!(compte("paiements"), 227);
    assert_eq!(compte("affectations"), 1_805);

    let total: i64 = con
        .query_row("SELECT SUM(montant) FROM affectations", [], |l| l.get(0))
        .unwrap();
    assert_eq!(total, 1_807_000, "le total historique doit être intact");

    let incoherents: i64 = con
        .query_row("SELECT COUNT(*) FROM v_paiements_incoherents", [], |l| {
            l.get(0)
        })
        .unwrap();
    assert_eq!(incoherents, 0);
}

// ------------------------------------------------------------------
//  2. P01 : un exercice décalé crédite avril→novembre, et refuse
//     décembre→mars tant qu'ils ne sont pas échus.
// ------------------------------------------------------------------
#[test]
fn exercice_decale_credite_les_bons_mois() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2031-2032",
        jour(2031, 4, 1),
        jour(2032, 3, 31),
        1_000,
    )
    .expect("exercice créé");

    let membre = creer_membre(&con, famille, "ZZDECALE", Some("2030-12-01"), None);
    let paiement = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        8_000,
        jour(2031, 11, 10),
        "especes",
    )
    .expect("8 000 F = 8 mois échus");

    let mois: Vec<(i32, u32)> = paiement
        .affectations
        .iter()
        .map(|v| (v.annee, v.mois))
        .collect();
    assert_eq!(
        mois,
        vec![
            (2031, 4),
            (2031, 5),
            (2031, 6),
            (2031, 7),
            (2031, 8),
            (2031, 9),
            (2031, 10),
            (2031, 11)
        ],
        "les 8 premiers mois doivent être avril→novembre, pas janvier→août"
    );

    let autre = creer_membre(&con, famille, "ZZDECALE2", Some("2030-12-01"), None);
    match ventilation::ventiler(
        &mut con,
        autre,
        exercice,
        12_000,
        jour(2031, 11, 10),
        "especes",
    ) {
        Err(Erreur::Reliquat(total, reste)) => {
            assert_eq!((total, reste), (12_000, 4_000), "décembre→mars non échus");
        }
        autre_resultat => panic!("attendu Reliquat, obtenu {autre_resultat:?}"),
    }
}

// ------------------------------------------------------------------
//  3. Un mois civil ne peut pas appartenir à deux exercices.
// ------------------------------------------------------------------
#[test]
fn un_mois_ne_peut_appartenir_a_deux_exercices() {
    let b = base();
    let con = ouvrir(&b);
    // 2026 est déjà couvert par l'exercice civil migré.
    let resultat = creer_exercice(
        &con,
        "Chevauchement",
        jour(2026, 7, 1),
        jour(2027, 6, 30),
        1_000,
    );
    assert!(
        resultat.is_err(),
        "rattacher juillet 2026 à un second exercice doit être refusé"
    );
}

// ------------------------------------------------------------------
//  4. Mois partiel, puis solde.
// ------------------------------------------------------------------
#[test]
fn mois_partiel_puis_solde() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2030",
        jour(2030, 1, 1),
        jour(2030, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(&con, famille, "ZZPARTIEL", Some("2030-01-01"), None);

    let premier = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        600,
        jour(2030, 11, 10),
        "especes",
    )
    .expect("600 F acceptés");
    assert_eq!(premier.affectations.len(), 1);
    assert_eq!(premier.affectations[0].montant, 600);

    let solde = ventilation::solde(&con, membre, exercice)
        .unwrap()
        .expect("membre assujetti");
    assert_eq!(
        (solde.paye, solde.reste, solde.mois_a_jour),
        (600, 11_400, 0)
    );

    let second = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        400,
        jour(2030, 11, 10),
        "especes",
    )
    .expect("le complément solde le mois");
    assert_eq!(second.affectations[0].montant, 400);

    let solde = ventilation::solde(&con, membre, exercice).unwrap().unwrap();
    assert_eq!(
        (solde.paye, solde.reste, solde.mois_a_jour),
        (1_000, 11_000, 1)
    );
}

// ------------------------------------------------------------------
//  5. D4 : numéros stables, jamais réattribués.
// ------------------------------------------------------------------
#[test]
fn numeros_de_recu_stables_et_jamais_reutilises() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2033",
        jour(2033, 1, 1),
        jour(2033, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(&con, famille, "ZZRECU", Some("2033-01-01"), None);

    let premier = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2033, 11, 10),
        "especes",
    )
    .expect("paiement accepté");
    assert_eq!(premier.numero_recu, "RECU-2033-000001");

    // Deux impressions du même reçu portent le même numéro : il est en base.
    let relu: String = con
        .query_row(
            "SELECT numero_recu FROM paiements WHERE id = ?1",
            params![premier.id],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(relu, premier.numero_recu);

    con.execute("DELETE FROM paiements WHERE id = ?1", params![premier.id])
        .expect("suppression du versement");

    let second = ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2033, 11, 10),
        "especes",
    )
    .expect("nouveau paiement accepté");
    assert_eq!(
        second.numero_recu, "RECU-2033-000002",
        "le numéro du paiement supprimé ne doit pas être réutilisé"
    );
}

// ------------------------------------------------------------------
//  6. D9 : suppressions protégées.
// ------------------------------------------------------------------
#[test]
fn suppressions_protegees() {
    let b = base();
    let mut con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2034",
        jour(2034, 1, 1),
        jour(2034, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(&con, famille, "ZZSUPPR", Some("2034-01-01"), None);

    ventilation::ventiler(
        &mut con,
        membre,
        exercice,
        1_000,
        jour(2034, 11, 10),
        "especes",
    )
    .expect("paiement accepté");

    assert!(
        con.execute("DELETE FROM membres WHERE id = ?1", params![membre])
            .is_err(),
        "un membre ayant des paiements ne peut pas être supprimé"
    );
    assert!(
        con.execute("DELETE FROM exercices WHERE id = ?1", params![exercice])
            .is_err(),
        "un exercice dont une échéance est réglée ne peut pas être supprimé"
    );
}

// ------------------------------------------------------------------
//  7. P05 : un parent hors de la famille est refusé, avec un message clair.
// ------------------------------------------------------------------
#[test]
fn parent_hors_de_la_famille_refuse() {
    let b = base();
    let con = ouvrir(&b);

    let mut stmt = con
        .prepare("SELECT id FROM familles ORDER BY id LIMIT 2")
        .unwrap();
    let familles: Vec<i64> = stmt
        .query_map([], |l| l.get(0))
        .unwrap()
        .map(|r| r.unwrap())
        .collect();
    drop(stmt);
    assert_eq!(familles.len(), 2);

    let pere = creer_membre(&con, familles[0], "ZZPERE", None, None);
    let enfant = creer_membre(&con, familles[1], "ZZENFANT", None, None);

    match con.execute(
        "UPDATE membres SET parent_id = ?1 WHERE id = ?2",
        params![pere, enfant],
    ) {
        Err(rusqlite::Error::SqliteFailure(_, Some(message))) => {
            assert!(
                message.contains("même famille"),
                "message inattendu : {message}"
            );
        }
        autre => panic!("un parent d'une autre famille doit être refusé : {autre:?}"),
    }
}

// ------------------------------------------------------------------
//  8. D7 : la date de sortie borne les échéances dues.
// ------------------------------------------------------------------
#[test]
fn date_de_sortie_borne_les_echeances_dues() {
    let b = base();
    let con = ouvrir(&b);
    let famille = premiere_famille(&con);
    let exercice = creer_exercice(
        &con,
        "Exercice 2035",
        jour(2035, 1, 1),
        jour(2035, 12, 31),
        1_000,
    )
    .expect("exercice créé");
    let membre = creer_membre(
        &con,
        famille,
        "ZZSORTI",
        Some("2035-01-01"),
        Some("2035-06-30"),
    );

    let solde = ventilation::solde(&con, membre, exercice)
        .unwrap()
        .expect("membre assujetti sur la période");
    assert_eq!(solde.mois_dus, 6, "janvier→juin seulement");
    assert_eq!(solde.du, 6_000);
}

// ------------------------------------------------------------------
//  9. L'autodiagnostic de démarrage ne signale que l'historique connu.
// ------------------------------------------------------------------
#[test]
fn autodiagnostic_ne_signale_que_les_depassements_historiques() {
    let b = base();
    let con = ouvrir(&b);
    let alertes = db::autodiagnostic(&con).expect("diagnostic");
    assert_eq!(alertes.len(), 1, "alertes inattendues : {alertes:?}");
    assert!(alertes[0].contains("au-delà du dû"), "{alertes:?}");
}

/// La répartition prévisionnelle annonce ce que le versement couvrirait, sans
/// écrire une seule ligne : c'est ce que la feuille affiche pendant la frappe.
#[test]
fn le_plan_annonce_les_mois_et_le_reliquat_sans_ecrire() {
    let b = base();
    let con = ouvrir(&b);
    let membre = creer_membre(
        &con,
        premiere_famille(&con),
        "Plan",
        Some("2027-01-01"),
        None,
    );
    // 2027 : les exercices 2024 à 2026 existent déjà dans la base, et leurs
    // bornes sont uniques.
    let exercice = creer_exercice(
        &con,
        "Plan 2027",
        jour(2027, 1, 1),
        jour(2027, 12, 31),
        1_000,
    )
    .expect("exercice de test");

    // Au 15 juillet 2027, sept mois sont échus : janvier → juillet.
    let date = jour(2027, 7, 15);
    let plan = ventilation::plan_ventilation(&con, membre, exercice, 5_500, date).unwrap();
    assert_eq!(
        plan.affectations.len(),
        6,
        "janvier à mai pleins, puis 500 F sur juin"
    );
    assert_eq!(plan.affectations[0].mois, 1);
    assert_eq!(plan.affectations[5].mois, 6);
    assert_eq!(plan.affectations[5].montant, 500);
    assert_eq!(plan.ventile, 5_500);
    assert_eq!(plan.reliquat, 0);

    // 9 000 F pour 7 000 F dus : 2 000 F resteraient sans imputation.
    let trop = ventilation::plan_ventilation(&con, membre, exercice, 9_000, date).unwrap();
    assert_eq!(trop.ventile, 7_000);
    assert_eq!(trop.reliquat, 2_000);

    // Rien n'a été écrit.
    let paiements: i64 = con
        .query_row(
            "SELECT COUNT(*) FROM paiements WHERE membre_id = ?1",
            params![membre],
            |l| l.get(0),
        )
        .unwrap();
    assert_eq!(paiements, 0, "le plan n'écrit aucun paiement");

    // Aucun mois échu : le cœur refuse de planifier.
    let rien = ventilation::plan_ventilation(&con, membre, exercice, 1_000, jour(2026, 12, 31));
    assert!(matches!(rien, Err(Erreur::AucuneEcheance)));
}
