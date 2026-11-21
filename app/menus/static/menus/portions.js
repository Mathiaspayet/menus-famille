// « Pour 4 personnes » sur la page du jour.
// 1. On touche un prénom pour le retirer (ou le remettre) ; « Boîtes de demain »
//    retire ou remet les 2 boîtes du lendemain.
// 2. Dans chaque recette, les INGRÉDIENTS sont recalculés pour les présents :
//    la part de chacun est lue dans le tableau « Dans l'assiette » (ex. 330 g sur
//    980 g), boîtes du lendemain comprises si elles sont prévues.
// 3. Le tableau « Dans l'assiette » n'affiche plus que les présents.
// Le choix est gardé sur ce téléphone, pour ce jour-là seulement.
(function () {
  const barre = document.getElementById("qui-mange");
  if (!barre) return;
  const cle = "qui-mange-" + barre.dataset.jour;
  const puces = Array.from(barre.querySelectorAll(".chip[data-p]"));
  const nbPersonnes = puces.length;
  const noms = puces.map(b => b.textContent.trim());

  // --- état (présents + boîtes), enregistré dans le navigateur ---
  let etat = { absents: [], boites: true };
  try {
    const lu = JSON.parse(localStorage.getItem(cle) || "null");
    if (lu && Array.isArray(lu.absents)) etat = { absents: lu.absents.map(Number), boites: lu.boites !== false };
  } catch (e) { /* stockage indisponible : on garde l'état par défaut */ }
  function enregistrer() {
    try {
      if (!etat.absents.length && etat.boites) localStorage.removeItem(cle);
      else localStorage.setItem(cle, JSON.stringify(etat));
    } catch (e) { /* rien */ }
  }
  const present = i => !etat.absents.includes(i);

  // --- lecture des quantités du tableau ---
  const FRACTIONS = { "½": .5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": .25, "¾": .75, "⅕": .2, "⅖": .4, "⅗": .6, "⅘": .8 };
  const NOMBRE = /^(\d+(?:[.,]\d+)?)?\s*([½⅓⅔¼¾⅕⅖⅗⅘])?\s*([\s\S]*)$/;

  // « 120 g » → {n:120, u:"g"} ; « ⅗ de pavé » → {n:0.6, u:"pavé"} ; null si vide, false si non chiffré.
  function lire(texte) {
    const t = texte.trim();
    if (["", "–", "-"].includes(t)) return null;
    const m = t.match(NOMBRE);
    if (!m || (m[1] === undefined && m[2] === undefined)) return false;
    const n = (m[1] ? parseFloat(m[1].replace(",", ".")) : 0) + (m[2] ? FRACTIONS[m[2]] : 0);
    let u = m[3].replace(/\(.*?\)/g, "").replace(/^(de |d')/, "").trim().toLowerCase();
    if (u === "%") return false;
    if (u === "kg") return { n: n * 1000, u: "g" };
    return { n, u: u.replace(/s$/, "") };
  }
  const estBoite = libelle => /^bo[iî]tes? de demain/i.test(libelle.trim());
  const denree = libelle => libelle.toLowerCase().replace(/^bo[iî]tes? de demain\s*:\s*/, "").replace(/\(.*?\)/g, "").trim();
  const somme = (parts, garder) => parts.reduce((s, n, i) => s + (garder(i) ? n : 0), 0);

  // Part de la recette à cuisiner pour les présents (1 = recette entière).
  function facteur(body) {
    const table = body.querySelector("table.portions");
    if (!table) return 1;
    const plats = [], boites = [];
    table.querySelectorAll("tbody tr").forEach(tr => {
      const valeurs = Array.from(tr.querySelectorAll("td[data-p]")).map(td => lire(td.textContent));
      const chiffres = valeurs.filter(Boolean);
      if (valeurs.includes(false) || !chiffres.length || chiffres.some(v => v.u !== chiffres[0].u)) return;
      const ligne = { libelle: tr.querySelector("th").textContent, parts: valeurs.map(v => (v ? v.n : 0)) };
      if (somme(ligne.parts, () => true) > 0) (estBoite(ligne.libelle) ? boites : plats).push(ligne);
    });
    if (!plats.length) return 1;   // ex. « cantine », « 50 % » : on ne sait pas calculer
    // Assiettes : moyenne, ligne par ligne, de la part des présents.
    const assiettes = plats.reduce((s, l) => s + somme(l.parts, present) / somme(l.parts, () => true), 0) / plats.length;
    // Boîtes du lendemain, en proportion de l'assiette entière.
    let boitesTout = 0, boitesMaintenant = 0, n = 0;
    if (boites.length) {         // lignes « Boîte de demain : … » écrites dans le tableau
      boites.forEach(b => {
        const plat = plats.find(p => denree(p.libelle) === denree(b.libelle));
        if (!plat) return;
        const total = somme(plat.parts, () => true);
        n++;
        boitesTout += somme(b.parts, () => true) / total;
        if (etat.boites) boitesMaintenant += somme(b.parts, present) / total;
      });
    } else if (body.dataset.boites) {   // « 2 boîtes » = les parts des deux plus grandes assiettes (les adultes)
      plats.forEach(l => {
        const total = somme(l.parts, () => true);
        const adultes = l.parts.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 2).map(x => x[1]);
        n++;
        boitesTout += somme(l.parts, i => adultes.includes(i)) / total;
        if (etat.boites) boitesMaintenant += somme(l.parts, i => adultes.includes(i) && present(i)) / total;
      });
    }
    const k = n ? boitesTout / n : 0, km = n ? boitesMaintenant / n : 0;
    return (assiettes + km) / (1 + k);
  }

  // --- recalcul d'un ingrédient (« 625 g de poulet » × 0,66 → « 415 g de poulet ») ---
  const echapper = t => t.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const virgule = x => String(x).replace(".", ",");
  const demi = x => Math.max(.5, Math.round(x * 2) / 2);
  const quart = x => Math.max(.25, Math.round(x * 4) / 4);
  const enDemis = x => (Math.floor(x) || "") + ({ .25: "¼", .5: "½", .75: "¾" }[x % 1] || "") || "0";
  function grammes(g) {
    g = g < 20 ? Math.max(1, Math.round(g)) : g < 200 ? Math.round(g / 5) * 5 : Math.round(g / 10) * 10;
    return g >= 1000 ? virgule(Math.round(g / 100) / 10) + " kg" : g + " g";
  }
  // Volumes : on garde l'unité de la recette (cl reste en cl).
  function volume(ml, unite) {
    if (unite === "l" && ml >= 1000) return virgule(Math.round(ml / 100) / 10) + " l";
    if (unite !== "ml") return Math.max(1, Math.round(ml / 10)) + " cl";
    return (ml < 50 ? Math.max(5, Math.round(ml / 5) * 5) : Math.round(ml / 10) * 10) + " ml";
  }
  function ajuster(texte, f) {
    const m = texte.match(NOMBRE);
    if (!m || (m[1] === undefined && m[2] === undefined)) return null;   // « Thym », « Ketchup »…
    const n = (m[1] ? parseFloat(m[1].replace(",", ".")) : 0) + (m[2] ? FRACTIONS[m[2]] : 0);
    let reste = m[3], qte, u;
    if ((u = reste.match(/^(kg|g)\b\s*/))) {
      qte = grammes(n * f * (u[1] === "kg" ? 1000 : 1));
    } else if ((u = reste.match(/^(l|cl|ml)\b\s*/i))) {
      qte = volume(n * f * { l: 1000, cl: 10, ml: 1 }[u[1].toLowerCase()], u[1].toLowerCase());
    } else if ((u = reste.match(/^(c\. à soupe|c\. à café|c\. à c\.|cm)\s*/))) {
      qte = enDemis(demi(n * f)) + " " + u[1];
    } else {
      u = null;
      // À l'unité : au quart près pour 1 (¾ potimarron), à la moitié jusqu'à 3, sinon à l'unité.
      const v = n <= 1 ? quart(n * f) : n <= 3 ? demi(n * f) : Math.max(1, Math.round(n * f));
      qte = enDemis(v);
      if (v <= 1 && n > 1) reste = reste.replace(/^(\S{3,}?)[sx]\b/, "$1");   // « 2 gousses » → « 1 gousse »
    }
    if (u) reste = reste.slice(u[0].length);
    // « (≈ 1 kg) » suit la quantité ; « (1 boîte de 400 g) » reste tel quel (contenant à ouvrir).
    reste = reste.replace(/\(≈\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\)/, (_, x, unite) =>
      "(≈ " + grammes(parseFloat(x.replace(",", ".")) * (unite === "kg" ? 1000 : 1) * f) + ")");
    return `<b class="ajuste">${echapper(qte)}</b> ${echapper(reste.trim())}`;
  }

  // --- préparation des recettes (une seule fois) ---
  const recettes = Array.from(document.querySelectorAll(".body[data-ajuster]")).map(body => {
    const ing = body.querySelector("ul.ing");
    if (ing) ing.insertAdjacentHTML("beforebegin", '<p class="ajustement" hidden></p>');
    return { body, items: ing ? Array.from(ing.children).map(li => ({ li, texte: li.textContent })) : [] };
  });
  document.querySelectorAll("table.portions tbody tr").forEach(tr => {
    if (estBoite(tr.querySelector("th").textContent)) tr.classList.add("ligne-boite");
  });

  function resume() {
    const n = nbPersonnes - etat.absents.length;
    return `${n} personne${n > 1 ? "s" : ""}` + (etat.absents.length ? ` (sans ${etat.absents.map(i => noms[i]).join(", ")})` : "");
  }

  function appliquer() {
    puces.forEach(b => b.setAttribute("aria-pressed", present(+b.dataset.p)));
    barre.querySelector(".chip[data-boites]").setAttribute("aria-pressed", etat.boites);

    // Tableaux : seulement les présents, et les lignes de boîtes si on en fait.
    document.querySelectorAll("table.portions").forEach(table => {
      table.querySelectorAll("[data-p]").forEach(c => { c.hidden = !present(+c.dataset.p); });
      table.querySelectorAll("tr.ligne-boite").forEach(tr => { tr.hidden = !etat.boites; });
    });
    document.querySelectorAll(".note-boites").forEach(n => { n.hidden = !etat.boites; });

    // Ingrédients recalculés pour les présents.
    recettes.forEach(({ body, items }) => {
      const f = facteur(body);
      const ajuste = Math.abs(f - 1) > 0.01;
      items.forEach(({ li, texte }) => {
        const nouveau = ajuste ? ajuster(texte, f) : null;
        if (nouveau) li.innerHTML = nouveau; else li.textContent = texte;
      });
      const note = body.querySelector(".ajustement");
      if (note) {
        note.hidden = !ajuste;
        note.textContent = `Quantités pour ${resume()}${body.dataset.boites ? (etat.boites ? ", boîtes de demain comprises" : ", sans les boîtes") : ""}. Les étapes gardent celles de la recette entière.`;
      }
    });

    const modifie = etat.absents.length > 0 || !etat.boites;
    barre.classList.toggle("modifie", modifie);
    const r = document.getElementById("qui-resume");
    if (r) r.textContent = resume() + (etat.boites ? "" : " · sans les boîtes");
  }

  barre.addEventListener("click", e => {
    const b = e.target.closest(".chip");
    if (!b) return;
    if (b.hasAttribute("data-boites")) etat.boites = !etat.boites;
    else {
      const i = +b.dataset.p;
      if (etat.absents.includes(i)) etat.absents = etat.absents.filter(x => x !== i);
      else if (etat.absents.length < nbPersonnes - 1) etat.absents.push(i);   // au moins une personne
    }
    enregistrer();
    appliquer();
  });

  appliquer();
})();
