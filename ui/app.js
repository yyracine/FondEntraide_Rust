const { invoke } = window.__TAURI__.core;

const etat = {
  clan: null,
  grandeFamille: null,
  lignee: null,
  famille: null,
  exercices: [],
  exercice: null,
};

const nf = new Intl.NumberFormat("fr-FR");
const $ = (id) => document.getElementById(id);
const fcf = (montant) => `${nf.format(montant)} F`;
const pluriel = (n, mot) => `${nf.format(n)} ${mot}${n > 1 ? "s" : ""}`;

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
  const puces = [
    puce("Tous", etat.exercice === null, () => choisirExercice(null)),
  ];
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
    return;
  }
  const recherche = $("recherche").value.trim();
  const membres = await invoke("membres", {
    familleId: etat.famille.id,
    recherche: recherche.length > 0 ? recherche : null,
    exerciceId: etat.exercice ? etat.exercice.id : null,
  });
  afficherMembres(membres);
}

$("recherche").addEventListener("input", () => {
  clearTimeout(minuterie);
  minuterie = setTimeout(() => {
    chargerMembres().catch((e) => afficherErreur(e));
  }, 150);
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
