//! Prépare les documents affichés par l'application :
//!
//! - `ui/aide/aide-memoire.html` : copie de la feuille A4, servie telle quelle ;
//! - `ui/aide/guide.html` : `GUIDE_UTILISATEUR.md` converti en page lisible.
//!
//! Les sources restent à la racine du dépôt : la feuille imprimable et le guide
//! Markdown. Relancer après toute modification :
//!
//!     node scripts/docs.mjs

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ici = path.dirname(fileURLToPath(import.meta.url));
const racine = path.resolve(ici, "..");
const sortie = path.join(racine, "ui", "aide");
fs.mkdirSync(sortie, { recursive: true });

/* ------------------------------ conversion ----------------------------- */

const echapper = (texte) =>
  texte.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const enligne = (texte) =>
  echapper(texte)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

const cellule = (ligne) =>
  ligne
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());

function tableau(lignes) {
  const entete = cellule(lignes[0]);
  const corps = lignes.slice(2).map(cellule);
  const th = entete.map((c) => `<th>${enligne(c)}</th>`).join("");
  const tr = corps
    .map((l) => `<tr>${l.map((c) => `<td>${enligne(c)}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

function convertir(markdown) {
  const lignes = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocs = [];
  const vide = (l) => l.trim() === "";
  const estTable = (l) => /^\|.*\|\s*$/.test(l.trim());
  const estPuces = (l) => /^(\d+\.|[-*])\s+/.test(l);
  let i = 0;

  while (i < lignes.length) {
    const ligne = lignes[i];

    if (vide(ligne)) {
      i++;
      continue;
    }

    if (ligne.startsWith("```")) {
      i++;
      const code = [];
      while (i < lignes.length && !lignes[i].startsWith("```")) {
        code.push(lignes[i]);
        i++;
      }
      i++;
      blocs.push(`<pre><code>${echapper(code.join("\n"))}</code></pre>`);
      continue;
    }

    if (/^---+$/.test(ligne.trim())) {
      blocs.push("<hr>");
      i++;
      continue;
    }

    if (ligne.startsWith(">")) {
      const texte = [];
      while (i < lignes.length && lignes[i].startsWith(">")) {
        texte.push(lignes[i].replace(/^>\s?/, ""));
        i++;
      }
      blocs.push(`<blockquote>${enligne(texte.join(" "))}</blockquote>`);
      continue;
    }

    const titre = ligne.match(/^(#{1,3})\s+(.*)$/);
    if (titre) {
      const niveau = titre[1].length;
      blocs.push(`<h${niveau}>${enligne(titre[2])}</h${niveau}>`);
      i++;
      continue;
    }

    if (estTable(ligne)) {
      const lignesTable = [];
      while (i < lignes.length && estTable(lignes[i])) {
        lignesTable.push(lignes[i]);
        i++;
      }
      blocs.push(tableau(lignesTable));
      continue;
    }

    if (estPuces(ligne)) {
      const ordonnee = /^\d+\.\s+/.test(ligne);
      const elements = [];
      while (i < lignes.length && !vide(lignes[i])) {
        const puce = lignes[i].match(/^(\d+\.|[-*])\s+(.*)$/);
        if (puce) {
          elements.push(puce[2]);
          i++;
          continue;
        }
        if (/^\s{2,}\S/.test(lignes[i]) && elements.length > 0) {
          elements[elements.length - 1] += " " + lignes[i].trim();
          i++;
          continue;
        }
        break;
      }
      const balise = ordonnee ? "ol" : "ul";
      const contenu = elements.map((t) => `<li>${enligne(t)}</li>`).join("");
      blocs.push(`<${balise}>${contenu}</${balise}>`);
      continue;
    }

    const paragraphe = [];
    while (
      i < lignes.length &&
      !vide(lignes[i]) &&
      !/^(#{1,3})\s|^```|^>|^\|/.test(lignes[i]) &&
      !estPuces(lignes[i])
    ) {
      paragraphe.push(lignes[i].trim());
      i++;
    }
    blocs.push(`<p>${enligne(paragraphe.join(" "))}</p>`);
  }

  return blocs.join("\n");
}

/* ------------------------------- gabarit ------------------------------- */

const style = `
:root {
  --encre: #1d2321;
  --doux: #5b6764;
  --vert: #2f6f5e;
  --trait: #d3dbd8;
  --fond: #f4f7f6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #eef1f0;
  color: var(--encre);
  font: 15px/1.6 "Segoe UI", system-ui, -apple-system, sans-serif;
}
.barre {
  position: sticky;
  top: 0;
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  padding: 8px 18px;
  background: #1d2321;
}
.barre button {
  padding: 6px 16px;
  border: 1px solid #7fb9a8;
  border-radius: 6px;
  background: transparent;
  color: #fff;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.barre span { margin-right: auto; color: #b9c6c2; font-size: 12.5px; }
main {
  max-width: 860px;
  margin: 0 auto;
  padding: 28px 32px 48px;
  background: #fff;
  min-height: 100vh;
}
h1 { margin: 0 0 4px; font-size: 26px; letter-spacing: 0.2px; }
h1 + p { margin-top: 0; color: var(--doux); }
h2 {
  margin: 30px 0 10px;
  padding-bottom: 5px;
  border-bottom: 1px solid var(--trait);
  font-size: 19px;
  color: var(--vert);
}
h3 { margin: 20px 0 8px; font-size: 16px; }
p { margin: 10px 0; }
ul, ol { margin: 10px 0; padding-left: 24px; }
li { margin: 5px 0; }
li > p { margin: 4px 0; }
code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--fond);
  font: 13.5px/1 ui-monospace, "Cascadia Mono", Consolas, monospace;
}
pre {
  padding: 12px 14px;
  border: 1px solid var(--trait);
  border-radius: 8px;
  background: var(--fond);
  overflow-x: auto;
}
pre code { padding: 0; background: none; }
blockquote {
  margin: 14px 0;
  padding: 10px 14px;
  border-left: 3px solid var(--vert);
  background: var(--fond);
}
blockquote p { margin: 0; }
table {
  width: 100%;
  margin: 14px 0;
  border-collapse: collapse;
  font-size: 14px;
}
th, td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--trait);
  text-align: left;
  vertical-align: top;
}
th { background: var(--fond); font-weight: 650; }
hr { margin: 26px 0; border: 0; border-top: 1px solid var(--trait); }
a { color: var(--vert); }
@media print {
  @page { size: A4; margin: 16mm; }
  body { background: #fff; font-size: 10.5pt; }
  .barre { display: none; }
  main { max-width: none; padding: 0; min-height: 0; }
  h2 { break-after: avoid; page-break-after: avoid; }
  pre, table, blockquote { break-inside: avoid; page-break-inside: avoid; }
}
`;

const guide = fs.readFileSync(path.join(racine, "GUIDE_UTILISATEUR.md"), "utf8");
const corps = convertir(guide);

const page = `<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Guide d'utilisation — Fonds d'Entraide</title>
    <style>${style}</style>
  </head>
  <body>
    <div class="barre">
      <span>Guide d'utilisation — Fonds d'Entraide</span>
      <button type="button" onclick="window.print()">Imprimer</button>
    </div>
    <main>
${corps}
    </main>
  </body>
</html>
`;

fs.writeFileSync(path.join(sortie, "guide.html"), page, "utf8");

const compte = (motif) => (corps.match(motif) ?? []).length;
console.log(
  `guide.html : ${compte(/<h2>/g)} sections, ${compte(/<table>/g)} tableaux, ` +
    `${compte(/<pre>/g)} blocs de code`,
);
