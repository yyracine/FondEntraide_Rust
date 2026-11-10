//! Test de fumée de l'interface, sans dépendance : un DOM minimal, un pont
//! Tauri simulé, et le vrai `ui/app.js` exécuté dedans.
//!
//! Ce qu'il attrape : une fonction appelée mais non définie (le bug
//! `choisirExercice`), un identifiant absent de `index.html`, un handler qui
//! lève, un en-tête qui ne suit pas l'exercice choisi.
//!
//!     node tests/ui/fumee.mjs

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ici = path.dirname(fileURLToPath(import.meta.url));
const racine = path.resolve(ici, "..", "..");
const lire = (...morceaux) => fs.readFileSync(path.join(racine, ...morceaux), "utf8");

/* ------------------------------ DOM minimal ----------------------------- */
const erreurs = [];

class Element {
  constructor(balise) {
    this.balise = balise.toUpperCase();
    this.enfants = [];
    this.parentElement = null;
    this.ecouteurs = new Map();
    this.className = "";
    this._texte = "";
    this.hidden = false;
    this.value = "";
    this.type = "";
    this.colSpan = 1;
    this.dataset = {};
    const liste = () => this.className.split(/\s+/).filter(Boolean);
    this.classList = {
      add: (classe) => {
        if (!liste().includes(classe)) this.className = [...liste(), classe].join(" ");
      },
      remove: (classe) => {
        this.className = liste()
          .filter((c) => c !== classe)
          .join(" ");
      },
      contains: (classe) => liste().includes(classe),
    };
  }

  get children() {
    return this.enfants;
  }

  get firstElementChild() {
    return this.enfants[0] ?? null;
  }

  get textContent() {
    if (this.enfants.length > 0) {
      return this.enfants.map((enfant) => enfant.textContent).join("");
    }
    return this._texte;
  }

  set textContent(valeur) {
    this._texte = String(valeur);
    this.enfants = [];
  }

  append(...noeuds) {
    for (const noeud of noeuds) {
      noeud.parentElement = this;
      this.enfants.push(noeud);
    }
  }

  replaceChildren(...noeuds) {
    this.enfants = [];
    this._texte = "";
    this.append(...noeuds);
  }

  addEventListener(type, action) {
    if (!this.ecouteurs.has(type)) this.ecouteurs.set(type, []);
    this.ecouteurs.get(type).push(action);
  }

  /** Déclenche un clic comme un utilisateur ; toute exception est retenue. */
  click() {
    for (const action of this.ecouteurs.get("click") ?? []) {
      try {
        const resultat = action(this);
        if (resultat && typeof resultat.then === "function") {
          resultat.catch((e) => erreurs.push(e));
        }
      } catch (e) {
        erreurs.push(e);
      }
    }
  }

  correspond(selecteur) {
    const classes = this.className.split(/\s+/).filter(Boolean);
    return selecteur
      .split(".")
      .filter(Boolean)
      .every((classe) => classes.includes(classe));
  }

  querySelectorAll(selecteur) {
    const trouves = [];
    const parcourir = (noeud) => {
      for (const enfant of noeud.enfants) {
        if (enfant.correspond(selecteur)) trouves.push(enfant);
        parcourir(enfant);
      }
    };
    parcourir(this);
    return trouves;
  }
}

const html = lire("ui", "index.html");
const elements = new Map();
for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
  elements.set(id, new Element("div"));
}

const document = {
  createElement: (balise) => new Element(balise),
  getElementById: (id) => elements.get(id) ?? null,
};

/* --------------------------- pont Tauri simulé -------------------------- */
const appels = [];
const reponses = {
  resume: { clans: 7, familles: 391, membres: 599, encaisse: 1_807_000 },
  exercices: [
    { id: 1, libelle: "Campagne 2026", date_debut: "2026-01-01", date_fin: "2026-12-31", annee: 2026, statut: "ouverte", courant: true },
    { id: 2, libelle: "Campagne 2025", date_debut: "2025-01-01", date_fin: "2025-12-31", annee: 2025, statut: "fermee", courant: false },
    { id: 3, libelle: "Campagne 2024", date_debut: "2024-01-01", date_fin: "2024-12-31", annee: 2024, statut: "fermee", courant: false },
  ],
  clans: [{ id: 2, nom: "YAOCRE", description: null }],
  grandes_familles: [{ id: 7, nom: "YAOCRE APPIA", clan_id: 2 }],
  lignees: [{ id: 18, nom: "YAOCRE APPIA", grande_famille_id: 7 }],
  familles: [{ id: 180, nom: "Akesse Comoé", lignee_id: 18, ordre: null, membres: 1 }],
  membres: [
    {
      id: 180,
      nom: "Akesse",
      prenom: "Comoé",
      statut: "actif",
      ordre_fratrie: null,
      parent: null,
      du: 12_000,
      paye: 3_000,
      reste: 9_000,
      arrieres: 8_000,
    },
  ],
};

const invoke = async (commande, args) => {
  appels.push({ commande, args });
  if (!(commande in reponses)) throw new Error(`commande inconnue : ${commande}`);
  return reponses[commande];
};

process.on("unhandledRejection", (e) => erreurs.push(e));

/* ---------------------------- exécution réelle -------------------------- */
const contexte = {
  window: { __TAURI__: { core: { invoke } } },
  document,
  Intl,
  console,
  setTimeout,
  clearTimeout,
};
vm.createContext(contexte);
vm.runInContext(lire("ui", "app.js"), contexte, { filename: "ui/app.js" });

const attendre = async (ms = 30) => {
  await new Promise((r) => setTimeout(r, ms));
  await new Promise((r) => setTimeout(r, 0));
};

await attendre();

/* -------------------------------- contrôles ----------------------------- */
const $ = (id) => elements.get(id);
const fcf = (n) => `${new Intl.NumberFormat("fr-FR").format(n)} F`;
const jetons = () => $("annees").children.map((c) => c.textContent);
const actif = () => $("annees").children.find((c) => c.classList.contains("actif"))?.textContent;
const dernierAppel = (commande) => appels.filter((a) => a.commande === commande).pop();

assert.equal($("liste-clans").children.length, 1, "un clan affiché");
assert.deepEqual(jetons(), ["Tous", "2026", "2025", "2024"], "quatre puces d'exercice");
assert.equal(actif(), "2026", "l'exercice courant est sélectionné par défaut");
assert.equal($("th-paye").textContent, "Payé 2026", "l'en-tête porte l'année");
assert.equal($("fil").textContent, "", "aucun fil d'Ariane avant sélection");

// 1. clic sur le clan : la chaîne à enfant unique doit descendre jusqu'aux membres
$("liste-clans").children[0].click();
await attendre();

assert.ok(
  appels.some((a) => a.commande === "grandes_familles") &&
    appels.some((a) => a.commande === "lignees") &&
    appels.some((a) => a.commande === "familles"),
  "la descente automatique interroge chaque niveau",
);
assert.equal(dernierAppel("membres")?.args.exerciceId, 1, "membres interrogés sur 2026");
assert.equal($("titre-membres").textContent, "Akesse Comoé");
assert.match($("fil").textContent, /Clan · YAOCRE/);
assert.match($("fil").textContent, /GF\/Lignée · YAOCRE APPIA/);
assert.match($("fil").textContent, /Famille · Akesse Comoé/);

const ligne = $("corps-membres").children[0];
assert.equal(ligne.children[0].textContent, "Akesse");
assert.equal(ligne.children[1].textContent, "Comoé");
assert.equal(ligne.children[3].textContent, fcf(3_000), "payé");
assert.equal(ligne.children[4].textContent, fcf(9_000), "reste");
assert.equal(ligne.children[5].textContent, fcf(8_000), "arriérés");
assert.match($("compte-membres").textContent, /Exercice 2026/);

// 2. puce 2024 : l'en-tête et la requête doivent suivre
$("annees").children[3].click();
await attendre();

assert.equal(actif(), "2024");
assert.equal($("th-paye").textContent, "Payé 2024");
assert.equal($("th-arrieres").textContent, "Arriérés 2024");
assert.equal(dernierAppel("membres")?.args.exerciceId, 3, "membres interrogés sur 2024");
assert.match($("compte-membres").textContent, /Exercice 2024/);

// 3. puce « Tous » : retour au cumul, sans année dans l'en-tête
$("annees").children[0].click();
await attendre();

assert.equal(actif(), "Tous");
assert.equal($("th-paye").textContent, "Payé");
assert.equal(dernierAppel("membres")?.args.exerciceId, null, "aucun filtre d'exercice");
assert.match($("compte-membres").textContent, /Tous exercices/);

// 4. aucun handler n'a levé
assert.deepEqual(
  erreurs.map((e) => String(e)),
  [],
  "aucune erreur dans les handlers",
);

console.log("fumee UI : OK");
console.log(`  ${appels.length} appels Tauri simulés`);
console.log(`  puces : ${jetons().join(" · ")}`);
console.log("  scénario : clan → descendue automatique → membres → 2024 → Tous");
