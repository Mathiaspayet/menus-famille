// Liste de courses unique, triée par urgence.
// 1. Cocher une case l'enregistre tout de suite sur le serveur (NAS) ; l'article
//    quitte la liste « à acheter » après un instant (on peut se raviser).
//    Sans réseau (au fond du magasin…), la case reste cochée et part dès que
//    la connexion revient (file d'attente d'appli.js).
// 2. Toutes les 8 secondes, la page relit l'état pour afficher ce que
//    l'autre personne a coché de son côté, et met à jour les compteurs.
(function () {
  const ticket = document.getElementById("ticket");
  if (!ticket) return;
  const sync = document.getElementById("sync");
  const file = window.MenusHorsLigne;
  const { debut, fin } = ticket.dataset;
  const aAcheter = ticket.querySelector(".a-acheter");

  function statut(texte, alerte) {
    sync.textContent = texte;
    sync.classList.toggle("alerte", !!alerte); // reste visible en bas de l'écran
  }
  function heure() {
    return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }

  // Les articles cochés quittent la liste « à acheter » ; un jour sans article disparaît aussi.
  function ranger() {
    if (!aAcheter) return;
    let titre = null, visibles = 0;
    const finJour = () => { if (titre) titre.hidden = titre._visibles === 0; };
    aAcheter.querySelectorAll(".cat, .item").forEach(el => {
      if (el.classList.contains("cat")) { finJour(); titre = el; titre._visibles = 0; return; }
      const visible = !el.classList.contains("done") || el.classList.contains("juste");
      el.hidden = !visible;
      if (visible) { visibles++; if (titre) titre._visibles++; }
    });
    finJour();
    const fini = ticket.querySelector(".tout-fait");
    if (fini) fini.hidden = visibles > 0;
  }

  function afficher(box, coche) {
    box.checked = coche;
    box.closest(".item").classList.toggle("done", coche);
    ranger();
  }

  // Compteurs des magasins : ce qui reste à acheter d'ici la fin de l'horizon.
  function majCompteurs(articles) {
    const reste = {};
    Object.values(articles).forEach(a => {
      if (!a.c && a.d >= debut && a.d <= fin) reste[a.m] = (reste[a.m] || 0) + 1;
    });
    document.querySelectorAll(".shops a[data-shop]").forEach(el => {
      const n = reste[el.dataset.shop] || 0;
      el.querySelector("span").textContent = n ? `${n} à acheter` : "rien";
    });
  }

  function etatAttente() {
    const n = Object.keys(file.enAttente()).length;
    return n ? `${n} case${n > 1 ? "s" : ""} en attente, envoyée${n > 1 ? "s" : ""} dès le retour du réseau.` : "";
  }

  // Les cases en attente gardent leur état local, quoi que dise le serveur.
  function appliquerAttente(articles) {
    Object.entries(file.enAttente()).forEach(([id, { coche }]) => {
      const box = document.getElementById("a" + id);
      if (box) afficher(box, coche);
      if (articles && articles[id]) articles[id].c = coche;
    });
  }

  document.addEventListener("change", async e => {
    const box = e.target;
    if (box.type !== "checkbox" || !box.dataset.url) return;
    const item = box.closest(".item");
    item.classList.add("juste");
    setTimeout(() => { item.classList.remove("juste"); ranger(); }, 1500);
    afficher(box, box.checked);
    file.ajouter(box.id.slice(1), box.dataset.url, box.checked);
    const { restants } = await file.envoyer();
    statut(restants ? "Hors connexion : " + etatAttente() : `Enregistré à ${heure()}`, restants);
    relire(); // compteurs des magasins à jour tout de suite
  });

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
      Object.entries(articles).forEach(([id, a]) => {
        const box = document.getElementById("a" + id);
        const item = box && box.closest(".item");
        if (box && box.checked !== a.c && !item.classList.contains("juste")) afficher(box, a.c);
      });
      appliquerAttente(articles);
      majCompteurs(articles);
      const attente = etatAttente();
      if (copie) statut(`Hors connexion : liste enregistrée sur ce téléphone. ${attente}`, true);
      else if (attente) statut(`Connexion instable : ${attente}`, true);
      else statut(`À jour à ${heure()}`, false);
    } catch (err) {
      appliquerAttente();
      statut(`Hors connexion : la liste reste utilisable. ${etatAttente()}`, true);
    } finally {
      enCours = false;
    }
  }

  ranger();
  appliquerAttente();
  relire();
  setInterval(relire, 8000);
  window.addEventListener("online", relire);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) relire(); });
})();
