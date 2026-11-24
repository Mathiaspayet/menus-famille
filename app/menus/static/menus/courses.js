// Liste de courses : une ligne par ingrédient, quantités additionnées sur la
// période choisie, du plus urgent au moins urgent.
// 1. Cocher une ligne coche tous les articles qu'elle regroupe (data-articles =
//    [[id, adresse], …]) ; la ligne quitte la liste « à acheter » après un instant.
//    Sans réseau, les cases restent cochées et partent au retour de la connexion
//    (file d'attente d'appli.js).
// 2. Toutes les 8 secondes, la page relit l'état pour afficher ce que l'autre
//    personne a coché, et met à jour les compteurs des magasins.
(function () {
  const ticket = document.getElementById("ticket");
  if (!ticket) return;
  const sync = document.getElementById("sync");
  const file = window.MenusHorsLigne;
  const { debut, fin } = ticket.dataset;
  const aAcheter = ticket.querySelector(".a-acheter");
  const lignes = Array.from(document.querySelectorAll(".item[data-articles]")).map(el => ({
    el, box: el.querySelector("input[type=checkbox]"), articles: JSON.parse(el.dataset.articles),
  }));

  function statut(texte, alerte) {
    sync.textContent = texte;
    sync.classList.toggle("alerte", !!alerte); // reste visible en bas de l'écran
  }
  function heure() {
    return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }

  // Les lignes cochées quittent la liste « à acheter » (sauf juste après le geste).
  function ranger() {
    if (!aAcheter) return;
    let visibles = 0;
    aAcheter.querySelectorAll(".item").forEach(el => {
      const visible = !el.classList.contains("done") || el.classList.contains("juste");
      el.hidden = !visible;
      if (visible) visibles++;
    });
    const fini = ticket.querySelector(".tout-fait");
    if (fini) fini.hidden = visibles > 0;
  }

  function afficher(ligne, coche) {
    ligne.box.checked = coche;
    ligne.el.classList.toggle("done", coche);
  }

  // Compteurs des magasins : nombre d'ingrédients à acheter sur la période.
  function majCompteurs(articles) {
    const reste = {};
    Object.values(articles).forEach(a => {
      if (!a.c && a.d >= debut && a.d <= fin) (reste[a.m] = reste[a.m] || new Set()).add(a.k);
    });
    document.querySelectorAll(".shops a[data-shop]").forEach(el => {
      const n = reste[el.dataset.shop] ? reste[el.dataset.shop].size : 0;
      el.querySelector("span").textContent = n ? `${n} à acheter` : "rien";
    });
  }

  function etatAttente() {
    const n = Object.keys(file.enAttente()).length;
    return n ? `${n} case${n > 1 ? "s" : ""} en attente, envoyée${n > 1 ? "s" : ""} dès le retour du réseau.` : "";
  }

  // État d'une ligne = tous ses articles cochés (les cases en attente priment sur le serveur).
  function appliquer(articles) {
    const attente = file.enAttente();
    lignes.forEach(ligne => {
      if (ligne.el.classList.contains("juste")) return;
      const coche = ligne.articles.every(([id]) =>
        attente[id] ? attente[id].coche : articles && articles[id] ? articles[id].c : ligne.box.checked);
      if (coche !== ligne.box.checked) afficher(ligne, coche);
    });
    if (articles) Object.entries(attente).forEach(([id, { coche }]) => { if (articles[id]) articles[id].c = coche; });
    ranger();
  }

  lignes.forEach(ligne => ligne.box.addEventListener("change", async () => {
    const coche = ligne.box.checked;
    ligne.el.classList.add("juste");
    setTimeout(() => { ligne.el.classList.remove("juste"); ranger(); }, 1500);
    afficher(ligne, coche);
    ligne.articles.forEach(([id, url]) => file.ajouter(String(id), url, coche));
    const { restants } = await file.envoyer();
    statut(restants ? "Hors connexion : " + etatAttente() : `Enregistré à ${heure()}`, restants);
    relire(); // compteurs des magasins à jour tout de suite
  }));

  let enCours = false;
  async function relire() {
    if (enCours || document.hidden) return;
    enCours = true;
    try {
      if (Object.keys(file.enAttente()).length) await file.envoyer();
      const r = await fetch(ticket.dataset.etat, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(r.status);
      const copie = r.headers.get("X-Menus-Copie") === "1";
      const { articles } = await r.json();
      appliquer(articles);
      majCompteurs(articles);
      const attente = etatAttente();
      if (copie) statut(`Hors connexion : liste enregistrée sur ce téléphone. ${attente}`, true);
      else if (attente) statut(`Connexion instable : ${attente}`, true);
      else statut(`À jour à ${heure()}`, false);
    } catch (err) {
      appliquer();
      statut(`Hors connexion : la liste reste utilisable. ${etatAttente()}`, true);
    } finally {
      enCours = false;
    }
  }

  appliquer();
  relire();
  setInterval(relire, 8000);
  window.addEventListener("online", relire);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) relire(); });
})();
