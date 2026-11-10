const { invoke } = window.__TAURI__.core;

const etat = {
  clan: null,
  grandeFamille: null,
  lignee: null,
  famille: null,
  exercices: [],
  exercice: null,
};

const MOIS = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];

const nf = new Intl.NumberFormat("fr-FR");
const $ = (id) => document.getElementById(id);
const fcf = (montant) => `${nf.format(montant)} F`;
const pluriel = (n, mot) => `${nf.format(n)} ${mot}${n > 1 ? "s" : ""}`;

let ligneSelectionnee = null;
let membreCourant = null;
// Un versement vient d'être enregistré dans cette feuille : le bouton reste
// désarmé tant que l'utilisateur n'a pas saisi un nouveau montant.
let enregistre = false;
// Exercice choisi dans la feuille, indépendant des puces du tableau.
let exerciceFeuille = null;

/* ------------------------------- erreurs ------------------------------- */
function afficherErreur(texte) {
  const bandeau = $("bandeau");
  bandeau.textContent = String(texte);
  bandeau.hidden = false;
}

function effacerErreur() {
  $("bandeau").hidden = true;
}

/* ------------------------------- outils -------------------------------- */
function vide(conteneur, texte) {
  conteneur.replaceChildren();
  const p = document.createElement("p");
  p.className = "vide";
  p.textContent = texte;
  conteneur.append(p);
}

function ligne(nom, detail, action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = "ligne";
  const titre = document.createElement("span");
  titre.className = "ligne-nom";
  titre.textContent = nom;
  bouton.append(titre);
  if (detail) {
    const petit = document.createElement("span");
    petit.className = "ligne-detail";
    petit.textContent = detail;
    bouton.append(petit);
  }
  bouton.addEventListener("click", () => action(bouton));
  return bouton;
}

function puce(texte, actif, action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = actif ? "puce actif" : "puce";
  bouton.textContent = texte;
  bouton.addEventListener("click", () => action());
  return bouton;
}

function remplir(idListe, elements, texteVide) {
  const conteneur = $(idListe);
  conteneur.replaceChildren();
  if (elements.length === 0) {
    vide(conteneur, texteVide);
    return;
  }
  for (const element of elements) conteneur.append(element);
}

function marquerActif(bouton) {
  const parent = bouton.parentElement;
  for (const autre of parent.querySelectorAll(".ligne.actif")) {
    autre.classList.remove("actif");
  }
  bouton.classList.add("actif");
}

/** Descend automatiquement les niveaux qui n'ont qu'un seul enfant. */
function unique(idListe) {
  const elements = $(idListe).querySelectorAll(".ligne");
  return elements.length === 1 ? elements[0] : null;
}

/**
 * Fil d'Ariane étiqueté par niveau. Deux niveaux consécutifs qui portent le
 * même nom sont fusionnés (« GF/Lignée · YAOCRE APPIA »).
 */
function fil() {
  const niveaux = [
    { etiquette: "Clan", valeur: etat.clan },
    { etiquette: "GF", valeur: etat.grandeFamille },
    { etiquette: "Lignée", valeur: etat.lignee },
    { etiquette: "Famille", valeur: etat.famille },
  ].filter((niveau) => niveau.valeur);

  const morceaux = [];
  for (const niveau of niveaux) {
    const dernier = morceaux[morceaux.length - 1];
    if (dernier && dernier.nom === niveau.valeur.nom) {
      dernier.etiquettes.push(niveau.etiquette);
    } else {
      morceaux.push({ nom: niveau.valeur.nom, etiquettes: [niveau.etiquette] });
    }
  }
  return morceaux.map((m) => `${m.etiquettes.join("/")} · ${m.nom}`).join("   ›   ");
}

function statut(texte) {
  const badge = document.createElement("span");
  const actif = texte === "actif";
  badge.className = actif ? "badge" : "badge inactif";
  badge.textContent = texte;
  return badge;
}

function cellule(texte, classe) {
  const td = document.createElement("td");
  td.textContent = texte ?? "—";
  if (classe) td.className = classe;
  return td;
}

function celluleBadge(texte) {
  const td = document.createElement("td");
  td.append(statut(texte));
  return td;
}

/* ------------------------------ compteurs ------------------------------ */
function compteur(valeur, libelle) {
  const boite = document.createElement("div");
  boite.className = "compteur";
  const v = document.createElement("span");
  v.className = "compteur-valeur";
  v.textContent = valeur;
  const l = document.createElement("span");
  l.className = "compteur-libelle";
  l.textContent = libelle;
  boite.append(v, l);
  return boite;
}

async function chargerResume() {
  const r = await invoke("resume");
  $("compteurs").replaceChildren(
    compteur(nf.format(r.clans), "clans"),
    compteur(nf.format(r.familles), "familles"),
    compteur(nf.format(r.membres), "membres"),
    compteur(fcf(r.encaisse), "encaissé total"),
  );
}

/* ------------------------------ exercices ------------------------------ */
/** « 2026 » pour une année civile, sinon le libellé complet. */
function nomExercice(exercice) {
  if (!exercice) return "tous exercices";
  const civile =
    exercice.date_debut.endsWith("-01-01") && exercice.date_fin.endsWith("-12-31");
  return civile ? String(exercice.annee) : exercice.libelle;
}

function dessinerAnnees() {
  const puces = [puce("Tous", etat.exercice === null, () => choisirExercice(null))];
  for (const exercice of etat.exercices) {
    puces.push(
      puce(nomExercice(exercice), etat.exercice?.id === exercice.id, () =>
        choisirExercice(exercice),
      ),
    );
  }
  $("annees").replaceChildren(...puces);
}

function majEntetes() {
  const suffixe = etat.exercice ? ` ${nomExercice(etat.exercice)}` : "";
  $("th-paye").textContent = `Payé${suffixe}`;
  $("th-reste").textContent = `Reste${suffixe}`;
  $("th-arrieres").textContent = `Arriérés${suffixe}`;
}

async function choisirExercice(exercice) {
  etat.exercice = exercice;
  dessinerAnnees();
  majEntetes();
  if (etat.famille) await chargerMembres();
  else afficherMembres([]);
}

async function chargerExercices() {
  etat.exercices = await invoke("exercices");
  etat.exercice = etat.exercices.find((e) => e.courant) ?? null;
  dessinerAnnees();
  majEntetes();
}

/* ------------------------------ navigation ----------------------------- */
function reinitialiserApres(niveau) {
  if (niveau === "clan") {
    etat.grandeFamille = null;
    etat.lignee = null;
    etat.famille = null;
    vide($("liste-gf"), "Sélectionnez un clan");
    vide($("liste-lignees"), "Sélectionnez une grande famille");
    vide($("liste-familles"), "Sélectionnez une lignée");
  }
  if (niveau === "grandeFamille") {
    etat.lignee = null;
    etat.famille = null;
    vide($("liste-lignees"), "Sélectionnez une grande famille");
    vide($("liste-familles"), "Sélectionnez une lignée");
  }
  if (niveau === "lignee") {
    etat.famille = null;
    vide($("liste-familles"), "Sélectionnez une lignée");
  }
  $("recherche").value = "";
  afficherMembres([]);
  $("fil").textContent = fil();
  $("titre-membres").textContent = etat.famille ? etat.famille.nom : "Membres";
}

async function choisirClan(bouton, clan) {
  marquerActif(bouton);
  etat.clan = clan;
  reinitialiserApres("clan");

  const familles = await invoke("grandes_familles", { clanId: clan.id });
  remplir(
    "liste-gf",
    familles.map((gf) => ligne(gf.nom, "", (b) => choisirGrandeFamille(b, gf))),
    "Aucune grande famille",
  );

  const seul = unique("liste-gf");
  if (seul) await choisirGrandeFamille(seul, familles[0]);
}

async function choisirGrandeFamille(bouton, gf) {
  marquerActif(bouton);
  etat.grandeFamille = gf;
  reinitialiserApres("grandeFamille");

  const lignees = await invoke("lignees", { grandeFamilleId: gf.id });
  remplir(
    "liste-lignees",
    lignees.map((l) => ligne(l.nom, "", (b) => choisirLignee(b, l))),
    "Aucune lignée",
  );

  const seule = unique("liste-lignees");
  if (seule) await choisirLignee(seule, lignees[0]);
}

async function choisirLignee(bouton, lignee) {
  marquerActif(bouton);
  etat.lignee = lignee;
  reinitialiserApres("lignee");

  const familles = await invoke("familles", { ligneeId: lignee.id });

  // Deux familles homonymes dans la même lignée : on les distingue par leur
  // identifiant et leur effectif.
  const occurrences = new Map();
  for (const f of familles) {
    occurrences.set(f.nom, (occurrences.get(f.nom) ?? 0) + 1);
  }

  remplir(
    "liste-familles",
    familles.map((f) => {
      const detail = pluriel(f.membres, "membre");
      const suffixe = occurrences.get(f.nom) > 1 ? ` · #${f.id}` : "";
      return ligne(f.nom, detail + suffixe, (b) => choisirFamille(b, f));
    }),
    "Aucune famille",
  );

  const seule = unique("liste-familles");
  if (seule) await choisirFamille(seule, familles[0]);
}

async function choisirFamille(bouton, famille) {
  marquerActif(bouton);
  etat.famille = famille;
  reinitialiserApres("famille");
  await chargerMembres();
}

/* -------------------------------- membres ------------------------------ */
function afficherMembres(membres) {
  const corps = $("corps-membres");
  corps.replaceChildren();
  ligneSelectionnee = null;

  if (membres.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "vide-table";
    td.textContent = etat.famille
      ? "Aucun membre ne correspond à cette recherche."
      : "Sélectionnez un clan, puis descendez jusqu'à une famille pour afficher ses membres.";
    tr.append(td);
    corps.append(tr);
  }

  for (const membre of membres) {
    const tr = document.createElement("tr");
    tr.className = "cliquable";
    tr.append(
      cellule(membre.nom),
      cellule(membre.prenom, membre.prenom ? "" : "doux"),
      celluleBadge(membre.statut),
      cellule(fcf(membre.paye), "numerique"),
      cellule(fcf(membre.reste), membre.reste > 0 ? "numerique" : "numerique doux"),
      cellule(
        fcf(membre.arrieres),
        membre.arrieres > 0 ? "numerique alerte" : "numerique doux",
      ),
      cellule(membre.parent, membre.parent ? "" : "doux"),
    );
    tr.addEventListener("click", () => ouvrirFeuille(membre, tr));
    corps.append(tr);
  }

  if (!etat.famille) {
    $("compte-membres").textContent = "";
    return;
  }

  const paye = membres.reduce((somme, m) => somme + m.paye, 0);
  const reste = membres.reduce((somme, m) => somme + m.reste, 0);
  const perimetre = etat.exercice
    ? `Exercice ${nomExercice(etat.exercice)}`
    : "Tous exercices";
  $("compte-membres").textContent =
    `${perimetre}   ·   ${pluriel(membres.length, "membre")}` +
    ` affiché${membres.length > 1 ? "s" : ""}` +
    `   ·   payé ${fcf(paye)}   ·   reste ${fcf(reste)}`;
}

let minuterie = null;

async function chargerMembres() {
  if (!etat.famille) {
    afficherMembres([]);
    return null;
  }
  const recherche = $("recherche").value.trim();
  const membres = await invoke("membres", {
    familleId: etat.famille.id,
    recherche: recherche.length > 0 ? recherche : null,
    exerciceId: etat.exercice ? etat.exercice.id : null,
  });
  afficherMembres(membres);
  return membres;
}

$("recherche").addEventListener("input", () => {
  clearTimeout(minuterie);
  minuterie = setTimeout(() => {
    chargerMembres().catch((e) => afficherErreur(e));
  }, 150);
});

/* --------------------------- recherche globale -------------------------- */
let minuterieGlobale = null;

function effacerResultats() {
  $("resultats-membres").hidden = true;
  $("resultats-membres").replaceChildren();
}

/**
 * Encaisser sans parcourir la hiérarchie : on tape un nom, on clique le bon
 * membre (situé par son chemin) et la feuille s'ouvre directement.
 */
async function chercherMembre() {
  const texte = $("recherche-membre").value.trim();
  if (texte.length < 2) {
    effacerResultats();
    return;
  }

  const exercice = exercicePourPaiement();
  const trouves = await invoke("rechercher_membres", {
    recherche: texte,
    exerciceId: exercice ? exercice.id : null,
  });

  const boite = $("resultats-membres");
  boite.replaceChildren();
  if (trouves.length === 0) {
    const vide = document.createElement("p");
    vide.className = "vide";
    vide.textContent = "Aucun membre ne porte ce nom.";
    boite.append(vide);
  } else {
    for (const trouve of trouves) {
      const nom = trouve.prenom ? `${trouve.nom} ${trouve.prenom}` : trouve.nom;
      boite.append(
        ligne(nom, `${trouve.chemin} · reste ${fcf(trouve.reste)}`, () =>
          choisirPourCotisation(trouve),
        ),
      );
    }
  }
  boite.hidden = false;
}

function choisirPourCotisation(trouve) {
  $("recherche-membre").value = "";
  effacerResultats();
  ouvrirFeuille(trouve, null);
}

$("recherche-membre").addEventListener("input", () => {
  clearTimeout(minuterieGlobale);
  minuterieGlobale = setTimeout(() => {
    chercherMembre().catch((e) => afficherErreur(e));
  }, 150);
});

/* ------------------------------ cotisation ----------------------------- */
/** Année locale au format ISO, pour préremplir la date du versement. */
function aujourdhui() {
  const d = new Date();
  const mois = String(d.getMonth() + 1).padStart(2, "0");
  const jour = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mois}-${jour}`;
}

/**
 * Un versement doit toujours viser un exercice : celui sélectionné dans les
 * puces, sinon l'exercice en cours. En mode « Tous », on ne peut pas deviner
 * l'année d'un encaissement, donc on retombe sur l'exercice courant.
 */
function exercicePourPaiement() {
  if (etat.exercice) return etat.exercice;
  return etat.exercices.find((e) => e.courant) ?? etat.exercices[0] ?? null;
}

/** L'exercice choisi **dans la feuille** prime sur celui du tableau. */
function exerciceDuPaiement() {
  return exerciceFeuille ?? exercicePourPaiement();
}

function dessinerAnneesFeuille() {
  $("annees-feuille").replaceChildren(
    ...etat.exercices.map((exercice) =>
      puce(nomExercice(exercice), exerciceFeuille?.id === exercice.id, () =>
        choisirExerciceFeuille(exercice),
      ),
    ),
  );
}

function majPerimetre() {
  const exercice = exerciceDuPaiement();
  if (!membreCourant || !exercice) {
    $("feuille-perimetre").textContent = "Aucun exercice disponible";
    return;
  }
  $("feuille-perimetre").textContent =
    `Exercice ${nomExercice(exercice)} · ` +
    `${pluriel(membreCourant.du, "franc")} dus sur le périmètre`;
}

/**
 * Changer d'année dans la feuille change le périmètre du versement : on relit
 * les soldes de cet exercice au lieu de garder ceux de l'année précédente.
 */
async function choisirExerciceFeuille(exercice) {
  if (!membreCourant || exerciceFeuille?.id === exercice.id) return;
  exerciceFeuille = exercice;
  dessinerAnneesFeuille();

  enregistre = false;
  $("montant").value = "";
  $("recu").hidden = true;
  $("recu").replaceChildren();
  $("repartition").hidden = true;
  $("repartition").replaceChildren();
  armerBouton();

  const aJour = await invoke("membre", {
    membreId: membreCourant.id,
    exerciceId: exercice.id,
  });
  if (aJour) {
    membreCourant = { ...membreCourant, ...aJour };
    majSoldes(membreCourant);
  }
  majPerimetre();
  $("note").textContent =
    membreCourant.reste > 0
      ? "La ventilation suit l'ordre des mois échus : le plus ancien d'abord."
      : "Ce membre est à jour sur cet exercice.";
}

function blocSolde(libelle, valeur, alerte) {
  const boite = document.createElement("div");
  boite.className = "solde";
  const v = document.createElement("span");
  v.className = alerte ? "solde-valeur alerte" : "solde-valeur";
  v.textContent = fcf(valeur);
  const l = document.createElement("span");
  l.className = "solde-libelle";
  l.textContent = libelle;
  boite.append(v, l);
  return boite;
}

/**
 * Le bouton d'encaissement ne doit jamais rester armé sur un montant déjà
 * enregistré : sans cela, un second clic renvoie un reliquat au lieu de
 * proposer un nouveau versement.
 */
function armerBouton() {
  const bouton = $("encaisser");
  const montant = Number($("montant").value);
  const saisi = Number.isInteger(montant) && montant > 0;
  bouton.disabled = enregistre && !saisi;
  bouton.textContent =
    enregistre && !saisi ? "Versement enregistré" : "Enregistrer le versement";
}

function majSoldes(membre) {
  $("feuille-soldes").replaceChildren(
    blocSolde("Payé", membre.paye, false),
    blocSolde("Reste", membre.reste, false),
    blocSolde("Arriérés", membre.arrieres, membre.arrieres > 0),
  );
}

function ouvrirFeuille(membre, ligneTableau) {
  membreCourant = membre;

  if (ligneSelectionnee) ligneSelectionnee.classList.remove("selection");
  // Une feuille ouverte depuis la recherche n'a pas de ligne de tableau.
  ligneSelectionnee = ligneTableau ?? null;
  ligneTableau?.classList.add("selection");

  exerciceFeuille = exercicePourPaiement();
  dessinerAnneesFeuille();

  const nom = membre.prenom ? `${membre.nom} ${membre.prenom}` : membre.nom;
  $("feuille-titre").textContent = nom;
  majPerimetre();
  $("feuille-chemin").textContent = membre.chemin ?? fil();

  majSoldes(membre);

  enregistre = false;
  $("montant").value = "";
  armerBouton();
  $("date-paiement").value = aujourdhui();
  $("mode").value = "especes";
  $("note").textContent =
    membre.reste > 0
      ? "La ventilation suit l'ordre des mois échus : le plus ancien d'abord."
      : "Ce membre est à jour sur cet exercice.";

  $("repartition").hidden = true;
  $("repartition").replaceChildren();
  $("recu").hidden = true;
  $("recu").replaceChildren();
  $("voile").hidden = false;
  $("montant").focus?.();
}

function fermerFeuille() {
  $("voile").hidden = true;
  $("repartition").hidden = true;
  enregistre = false;
  armerBouton();
  membreCourant = null;
  exerciceFeuille = null;
  if (ligneSelectionnee) {
    ligneSelectionnee.classList.remove("selection");
    ligneSelectionnee = null;
  }
}

/**
 * Ce que le versement en cours de saisie va couvrir : les mois, leur année, et
 * la part qui déborderait du dû (annoncée avant validation, pas après).
 */
function afficherApercu(plan) {
  const boite = $("repartition");
  boite.replaceChildren();

  const exercice = exerciceDuPaiement();
  const titre = document.createElement("p");
  titre.className = "repartition-titre";
  titre.textContent =
    `Imputé sur l'exercice ${nomExercice(exercice)} · ` +
    `${fcf(plan.ventile)} de ${fcf(membreCourant.du)} dus` +
    (plan.affectations.length === 0 ? " · aucun mois échu" : "");
  boite.append(titre);

  const date = $("date-paiement").value;
  const anneePaie = Number(date.slice(0, 4));
  const moisPaie = Number(date.slice(5, 7));

  if (plan.affectations.length > 0) {
    const liste = document.createElement("ul");
    for (const part of plan.affectations) {
      const li = document.createElement("li");
      const arriere =
        part.annee < anneePaie || (part.annee === anneePaie && part.mois < moisPaie);
      if (arriere) li.className = "arriere";
      li.textContent = `${MOIS[part.mois - 1]} ${part.annee} · ${fcf(part.montant)}`;
      liste.append(li);
    }
    boite.append(liste);
  }

  if (plan.reliquat > 0) {
    const reste = document.createElement("p");
    reste.className = "repartition-reliquat";
    reste.textContent =
      `${fcf(plan.reliquat)} ne peuvent pas être imputés : ` +
      "aucun mois échu ne reste à régler sur cet exercice. Baissez le montant ou choisissez l'année concernée.";
    boite.append(reste);
  }

  boite.hidden = false;
}

async function rafraichirApercu() {
  const boite = $("repartition");
  const exercice = exerciceDuPaiement();
  const montant = Number($("montant").value);

  if (!membreCourant || !exercice || !Number.isInteger(montant) || montant <= 0) {
    boite.hidden = true;
    boite.replaceChildren();
    return;
  }

  try {
    const plan = await invoke("previsualiser", {
      membreId: membreCourant.id,
      exerciceId: exercice.id,
      montant,
      datePaiement: $("date-paiement").value,
    });
    afficherApercu(plan);
  } catch (erreur) {
    boite.replaceChildren();
    const message = document.createElement("p");
    message.className = "repartition-reliquat";
    message.textContent = String(erreur);
    boite.append(message);
    boite.hidden = false;
  }
}

function afficherRecu(paiement) {
  const boite = $("recu");
  boite.replaceChildren();

  const numero = document.createElement("p");
  numero.className = "recu-numero";
  numero.textContent = `${paiement.numero_recu} · ${fcf(paiement.montant_total)}`;
  boite.append(numero);

  const liste = document.createElement("ul");
  for (const part of paiement.affectations) {
    const li = document.createElement("li");
    li.textContent = `${MOIS[part.mois - 1]} ${part.annee} — ${fcf(part.montant)}`;
    liste.append(li);
  }
  boite.append(liste);
  boite.hidden = false;
}

async function encaisser() {
  if (!membreCourant) return;

  const exercice = exerciceDuPaiement();
  const montant = Number($("montant").value);
  if (!Number.isInteger(montant) || montant <= 0) {
    $("note").textContent = "Montant invalide : un nombre entier de francs, supérieur à zéro.";
    return;
  }
  if (!exercice) {
    $("note").textContent = "Aucun exercice ouvert : impossible d'imputer le versement.";
    return;
  }

  const bouton = $("encaisser");
  bouton.disabled = true;
  bouton.textContent = "Enregistrement…";
  try {
    const paiement = await invoke("enregistrer_paiement", {
      membreId: membreCourant.id,
      exerciceId: exercice.id,
      montant,
      datePaiement: $("date-paiement").value,
      mode: $("mode").value,
    });
    afficherRecu(paiement);
    enregistre = true;
    $("montant").value = "";
    $("note").textContent = "";
    $("repartition").hidden = true;
    $("repartition").replaceChildren();

    // Les soldes doivent suivre l'encaissement. On relit le membre lui-même :
    // la feuille peut avoir été ouverte par la recherche, donc hors de la
    // famille actuellement affichée.
    const id = membreCourant.id;
    await chargerMembres();
    const aJour = await invoke("membre", {
      membreId: id,
      exerciceId: exercice.id,
    });
    if (aJour) {
      membreCourant = { ...membreCourant, ...aJour };
      majSoldes(membreCourant);
    }
    await chargerResume();
  } catch (erreur) {
    $("note").textContent = String(erreur);
  } finally {
    // `armerBouton` et non `disabled = false` : après un succès, le bouton doit
    // rester désarmé jusqu'à la prochaine saisie.
    armerBouton();
  }
}

for (const id of ["montant", "date-paiement"]) {
  $(id).addEventListener("input", () => {
    if (id === "montant") {
      // Nouvelle saisie = nouveau versement : le reçu précédent s'efface et le
      // bouton se réarme.
      enregistre = false;
      $("recu").hidden = true;
    }
    armerBouton();
    rafraichirApercu().catch((e) => afficherErreur(e));
  });
  $(id).addEventListener("change", () => {
    armerBouton();
    rafraichirApercu().catch((e) => afficherErreur(e));
  });
}

$("fermer-feuille").addEventListener("click", fermerFeuille);
$("encaisser").addEventListener("click", () => {
  encaisser().catch((e) => afficherErreur(e));
});
$("voile").addEventListener("click", (evenement) => {
  if (evenement.target === $("voile")) fermerFeuille();
});

/* -------------------------------- départ ------------------------------- */
async function demarrer() {
  try {
    effacerErreur();
    await chargerResume();
    await chargerExercices();
    const clans = await invoke("clans");
    remplir(
      "liste-clans",
      clans.map((c) => ligne(c.nom, c.description ?? "", (b) => choisirClan(b, c))),
      "Aucun clan",
    );
    vide($("liste-gf"), "Sélectionnez un clan");
    vide($("liste-lignees"), "Sélectionnez une grande famille");
    vide($("liste-familles"), "Sélectionnez une lignée");
    afficherMembres([]);
  } catch (erreur) {
    afficherErreur(erreur);
  }
}

demarrer();
