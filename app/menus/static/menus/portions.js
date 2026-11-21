// « Qui mange ? » sur la page du jour.
// 1. On touche un prénom pour le retirer (ou le remettre) : sa colonne disparaît
//    de tous les tableaux de portions de la page.
// 2. Chaque tableau gagne une colonne « Total » : la somme des parts des présents
//    (quand les valeurs s'additionnent : « 120 g », « 1 pavé », « ⅗ de pavé »…).
// 3. Sous chaque tableau, « À peser (cru) » additionne les lignes crues de la même
//    denrée, boîtes de demain comprises si le bouton « Boîtes de demain » est actif.
// Le choix est gardé sur ce téléphone, pour ce jour-là seulement.
(function () {
  const barre = document.getElementById("qui-mange");
  if (!barre) return;
  const cle = "qui-mange-" + barre.dataset.jour;
  const nbPersonnes = barre.querySelectorAll(".chip[data-p]").length;

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

  // --- lecture des quantités ---
  const FRACTIONS = { "½": .5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": .25, "¾": .75, "⅕": .2, "⅖": .4, "⅗": .6, "⅘": .8 };
  const VIDE = ["", "–", "-"];

  // « 120 g » → {n:120, u:"g"} ; « ⅗ de pavé » → {n:0.6, u:"pavé"} ; « 1½ » → {n:1.5, u:""}
  // Renvoie null si la case est vide, false si elle ne s'additionne pas.
  function lire(texte) {
    const t = texte.trim();
    if (VIDE.includes(t)) return null;
    const m = t.match(/^(\d+(?:[.,]\d+)?)?\s*([½⅓⅔¼¾⅕⅖⅗⅘])?\s*(.*)$/);
    if (!m || (m[1] === undefined && m[2] === undefined)) return false;
    let n = (m[1] ? parseFloat(m[1].replace(",", ".")) : 0) + (m[2] ? FRACTIONS[m[2]] : 0);
    let u = m[3].replace(/\(.*?\)/g, "").replace(/^(de |d')/, "").trim().toLowerCase();
    if (u === "%") return false;
    if (u === "kg") { n *= 1000; u = "g"; }
    if (u === "l") { n *= 1000; u = "ml"; }
    return { n, u: singulier(u) };
  }
  function singulier(u) {
    return u.split(" ").map(w => (w.length > 3 && /[sx]$/.test(w) && !/^(g|ml)$/.test(w)) ? w.slice(0, -1) : w).join(" ");
  }
  function ecrire(n, u) {
    let v = Math.round(n * 10) / 10;
    if (u === "g" && v >= 1000) return (Math.round(v / 10) / 100).toString().replace(".", ",") + " kg";
    if (u === "g" || u === "ml") v = Math.round(v);
    const nombre = v.toString().replace(".", ",");
    if (!u) return nombre;
    const pluriel = v > 1 && !/^(g|ml|cm)$/.test(u) && !/[sx]$/.test(u);
    return nombre + " " + (pluriel ? u.replace(/^(\S+)/, "$1s") : u);
  }
  // Additionne des quantités de même unité ; null si rien, false si impossible.
  function somme(valeurs) {
    let total = null;
    for (const v of valeurs) {
      if (v === null) continue;
      if (v === false) return false;
      if (total === null) total = { n: 0, u: v.u };
      else if (total.u !== v.u) return false;
      total.n += v.n;
    }
    return total;
  }

  // « Boîte de demain : nouilles crues » → « nouilles » ; « Porc cru » → « porc »
  function denreeCrue(libelle) {
    const l = libelle.toLowerCase().replace(/^bo[iî]tes? de demain\s*:\s*/, "");
    const m = l.match(/^(.*?)\s+(cru|crue|crus|crues)\b/);
    return m ? m[1].trim() : null;
  }
  const estBoite = libelle => /^bo[iî]tes? de demain/i.test(libelle.trim());

  // --- préparation des tableaux (une seule fois) ---
  const tableaux = Array.from(document.querySelectorAll("table.portions"));
  tableaux.forEach(table => {
    const tete = table.querySelector("thead tr");
    if (tete) tete.insertAdjacentHTML("beforeend", '<th class="tot">Total</th>');
    table.querySelectorAll("tbody tr").forEach(tr => {
      tr.insertAdjacentHTML("beforeend", '<td class="tot"></td>');
      if (estBoite(tr.querySelector("th").textContent)) tr.classList.add("ligne-boite");
    });
    table.closest(".tw").insertAdjacentHTML("afterend", '<p class="a-peser" hidden></p>');
  });

  function appliquer() {
    const present = i => !etat.absents.includes(i);
    barre.querySelectorAll(".chip[data-p]").forEach(b => b.setAttribute("aria-pressed", present(+b.dataset.p)));
    barre.querySelector(".chip[data-boites]").setAttribute("aria-pressed", etat.boites);

    tableaux.forEach(table => {
      table.querySelectorAll("[data-p]").forEach(c => { c.hidden = !present(+c.dataset.p); });
      const crus = new Map();   // denrée → [quantités]
      table.querySelectorAll("tbody tr").forEach(tr => {
        const boite = tr.classList.contains("ligne-boite");
        tr.hidden = boite && !etat.boites;
        const cases = Array.from(tr.querySelectorAll("td[data-p]")).filter(td => present(+td.dataset.p));
        const t = somme(cases.map(td => lire(td.textContent)));
        tr.querySelector("td.tot").textContent = t ? ecrire(t.n, t.u) : "–";
        const d = denreeCrue(tr.querySelector("th").textContent);
        if (d && t && !tr.hidden) { if (!crus.has(d)) crus.set(d, []); crus.get(d).push(t); }
      });
      const p = table.closest(".tw").nextElementSibling;
      const morceaux = [];
      crus.forEach((liste, d) => {
        const t = somme(liste);
        if (t) morceaux.push(`${d.charAt(0).toUpperCase() + d.slice(1)} : <b>${ecrire(t.n, t.u)}</b>`);
      });
      const absents = etat.absents.length;
      p.innerHTML = morceaux.length ? `À peser (cru${absents ? ", sans les absents" : ""}${table.querySelector(".ligne-boite") ? (etat.boites ? ", boîtes comprises" : ", sans boîtes") : ""}) : ` + morceaux.join(" · ") : "";
      p.hidden = !morceaux.length;
    });
    document.querySelectorAll(".note-boites").forEach(n => { n.hidden = !etat.boites; });
    barre.classList.toggle("modifie", etat.absents.length > 0 || !etat.boites);
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
