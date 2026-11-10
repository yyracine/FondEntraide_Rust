//! Écriture des membres : création, modification, suppression.
//!
//! Ce que SQLite refuserait par une erreur brute (parent d'une autre famille,
//! suppression d'un membre chargé d'historique) est vérifié ici, pour que
//! l'interface affiche une phrase compréhensible plutôt que
//! `FOREIGN KEY constraint failed`.

use chrono::NaiveDate;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::erreur::Erreur;

/// Statuts admis par le schéma.
const STATUTS: [&str; 5] = ["actif", "inactif", "decede", "parti", "suspendu"];

/// Champs éditables d'un membre : le formulaire les lit pour se préremplir et
/// les renvoie pour enregistrer. Les dates sont en ISO (`AAAA-MM-JJ`).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FicheMembre {
    /// `None` à la création.
    pub id: Option<i64>,
    pub famille_id: i64,
    /// Parent généalogique direct, obligatoirement dans la même famille.
    pub parent_id: Option<i64>,
    pub nom: String,
    pub prenom: Option<String>,
    pub telephone: Option<String>,
    pub sexe: Option<String>,
    pub ordre_fratrie: Option<i64>,
    pub statut: String,
    pub date_entree: Option<String>,
    pub date_sortie: Option<String>,
    pub notes: Option<String>,
}

/// Parent proposé dans le formulaire : la liste reste bornée à la famille.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CandidatParent {
    pub id: i64,
    pub nom: String,
}

fn texte(valeur: Option<&str>) -> Option<String> {
    valeur
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_string)
}

fn date_lisible(valeur: Option<&str>) -> Result<Option<String>, Erreur> {
    let Some(brut) = texte(valeur) else {
        return Ok(None);
    };
    NaiveDate::parse_from_str(&brut, "%Y-%m-%d")
        .map_err(|_| Erreur::DateMalFormee(brut.clone()))?;
    Ok(Some(brut))
}

/// Vrai si `candidat` compte `ancetre` parmi ses parents, grands-parents, etc.
/// La boucle est bornée : une base corrompue ne doit pas figer l'application.
fn descend_de(con: &Connection, candidat: i64, ancetre: i64) -> Result<bool, Erreur> {
    let mut courant = Some(candidat);
    let mut garde = 0;
    while let Some(id) = courant {
        if id == ancetre {
            return Ok(true);
        }
        garde += 1;
        if garde > 100 {
            return Err(Erreur::ParentInvalide(
                "chaîne de parents suspecte (plus de 100 niveaux)".to_string(),
            ));
        }
        courant = con
            .query_row(
                "SELECT parent_id FROM membres WHERE id = ?1",
                params![id],
                |l| l.get::<_, Option<i64>>(0),
            )
            .optional()?
            .flatten();
    }
    Ok(false)
}

fn verifier(con: &Connection, fiche: &FicheMembre) -> Result<(), Erreur> {
    if fiche.nom.trim().is_empty() {
        return Err(Erreur::ChampRequis("le nom"));
    }
    if !STATUTS.contains(&fiche.statut.as_str()) {
        return Err(Erreur::StatutInvalide(fiche.statut.clone()));
    }
    if let Some(sexe) = fiche.sexe.as_deref() {
        if sexe != "M" && sexe != "F" {
            return Err(Erreur::SexeInvalide(sexe.to_string()));
        }
    }

    let existe: bool = con.query_row(
        "SELECT EXISTS (SELECT 1 FROM familles WHERE id = ?1)",
        params![fiche.famille_id],
        |l| l.get(0),
    )?;
    if !existe {
        return Err(Erreur::FamilleInconnue(fiche.famille_id));
    }

    let entree = date_lisible(fiche.date_entree.as_deref())?;
    let sortie = date_lisible(fiche.date_sortie.as_deref())?;
    if let (Some(debut), Some(fin)) = (&entree, &sortie) {
        if debut > fin {
            return Err(Erreur::ChampIncoherent(
                "la date de sortie précède la date d'entrée".to_string(),
            ));
        }
    }

    if let Some(parent) = fiche.parent_id {
        if fiche.id == Some(parent) {
            return Err(Erreur::ParentInvalide(
                "un membre ne peut pas être son propre parent".to_string(),
            ));
        }
        let famille: Option<i64> = con
            .query_row(
                "SELECT famille_id FROM membres WHERE id = ?1",
                params![parent],
                |l| l.get(0),
            )
            .optional()?;
        match famille {
            None => return Err(Erreur::MembreInconnu(parent)),
            Some(f) if f != fiche.famille_id => return Err(Erreur::ParentHorsFamille),
            Some(_) => {}
        }
        if let Some(id) = fiche.id {
            if descend_de(con, parent, id)? {
                return Err(Erreur::ParentInvalide(
                    "le parent choisi descend de ce membre : la généalogie formerait une boucle"
                        .to_string(),
                ));
            }
        }
    }
    Ok(())
}

/// Crée un membre (`id = None`) ou met à jour celui qui existe, et renvoie son
/// identifiant. Une seule transaction : aucun champ à moitié écrit.
pub fn enregistrer(con: &mut Connection, fiche: &FicheMembre) -> Result<i64, Erreur> {
    verifier(con, fiche)?;

    let nom = fiche.nom.trim().to_string();
    let prenom = texte(fiche.prenom.as_deref());
    let telephone = texte(fiche.telephone.as_deref());
    let notes = texte(fiche.notes.as_deref());
    let sexe = texte(fiche.sexe.as_deref());
    let entree = date_lisible(fiche.date_entree.as_deref())?;
    let sortie = date_lisible(fiche.date_sortie.as_deref())?;

    let tx = con.transaction()?;
    let id = match fiche.id {
        Some(id) => {
            let modifies = tx.execute(
                "UPDATE membres
                    SET famille_id = ?2, parent_id = ?3, nom = ?4, prenom = ?5,
                        telephone = ?6, sexe = ?7, ordre_fratrie = ?8, statut = ?9,
                        date_entree = ?10, date_sortie = ?11, notes = ?12
                  WHERE id = ?1",
                params![
                    id,
                    fiche.famille_id,
                    fiche.parent_id,
                    nom,
                    prenom,
                    telephone,
                    sexe,
                    fiche.ordre_fratrie,
                    fiche.statut,
                    entree,
                    sortie,
                    notes
                ],
            )?;
            if modifies == 0 {
                return Err(Erreur::MembreInconnu(id));
            }
            id
        }
        None => {
            tx.execute(
                "INSERT INTO membres (famille_id, parent_id, nom, prenom, telephone,
                                      sexe, ordre_fratrie, statut, date_entree,
                                      date_sortie, notes)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
                params![
                    fiche.famille_id,
                    fiche.parent_id,
                    nom,
                    prenom,
                    telephone,
                    sexe,
                    fiche.ordre_fratrie,
                    fiche.statut,
                    entree,
                    sortie,
                    notes
                ],
            )?;
            tx.last_insert_rowid()
        }
    };
    tx.commit()?;
    Ok(id)
}

/// Champs complets d'un membre, pour préremplir le formulaire. La fiche
/// résumée du tableau ne contient ni téléphone, ni dates, ni notes.
pub fn edition(con: &Connection, membre_id: i64) -> Result<FicheMembre, Erreur> {
    let mut stmt = con.prepare(
        "SELECT id, famille_id, parent_id, nom, prenom, telephone, sexe,
                ordre_fratrie, statut, date_entree, date_sortie, notes
           FROM membres
          WHERE id = ?1",
    )?;
    stmt.query_row(params![membre_id], |l| {
        Ok(FicheMembre {
            id: Some(l.get(0)?),
            famille_id: l.get(1)?,
            parent_id: l.get(2)?,
            nom: l.get(3)?,
            prenom: l.get(4)?,
            telephone: l.get(5)?,
            sexe: l.get(6)?,
            ordre_fratrie: l.get(7)?,
            statut: l.get(8)?,
            date_entree: l.get(9)?,
            date_sortie: l.get(10)?,
            notes: l.get(11)?,
        })
    })
    .optional()?
    .ok_or(Erreur::MembreInconnu(membre_id))
}

/// Parents possibles dans une famille. Le cycle éventuel est refusé à
/// l'enregistrement, avec un message qui dit pourquoi.
pub fn candidats_parent(
    con: &Connection,
    famille_id: i64,
    exclure: Option<i64>,
) -> Result<Vec<CandidatParent>, Erreur> {
    let mut stmt = con.prepare(
        "SELECT id, TRIM(nom || ' ' || IFNULL(prenom, ''))
           FROM membres
          WHERE famille_id = ?1
            AND (?2 IS NULL OR id <> ?2)
          ORDER BY nom, prenom",
    )?;
    let lignes = stmt.query_map(params![famille_id, exclure], |l| {
        Ok(CandidatParent {
            id: l.get(0)?,
            nom: l.get(1)?,
        })
    })?;

    let mut resultat = Vec::new();
    for ligne in lignes {
        resultat.push(ligne?);
    }
    Ok(resultat)
}

/// Supprime un membre sans historique. Un membre qui a des descendants ou des
/// versements est refusé : l'historique financier ne doit pas disparaître par
/// accident (voir `suppressions_protegees`).
pub fn supprimer(con: &mut Connection, membre_id: i64) -> Result<(), Erreur> {
    let tx = con.transaction()?;

    let existe: bool = tx.query_row(
        "SELECT EXISTS (SELECT 1 FROM membres WHERE id = ?1)",
        params![membre_id],
        |l| l.get(0),
    )?;
    if !existe {
        return Err(Erreur::MembreInconnu(membre_id));
    }

    let descendants: i64 = tx.query_row(
        "SELECT COUNT(*) FROM membres WHERE parent_id = ?1",
        params![membre_id],
        |l| l.get(0),
    )?;
    if descendants > 0 {
        return Err(Erreur::SuppressionRefusee(format!(
            "ce membre a {descendants} descendant(s) : rattachez-les d'abord"
        )));
    }

    let versements: i64 = tx.query_row(
        "SELECT COUNT(*) FROM paiements WHERE membre_id = ?1",
        params![membre_id],
        |l| l.get(0),
    )?;
    if versements > 0 {
        return Err(Erreur::SuppressionRefusee(format!(
            "ce membre a {versements} versement(s) : annulez-les d'abord"
        )));
    }

    tx.execute("DELETE FROM membres WHERE id = ?1", params![membre_id])?;
    tx.commit()?;
    Ok(())
}
