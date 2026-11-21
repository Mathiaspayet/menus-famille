// Liste de courses partagée.
// 1. Cocher une case l'enregistre tout de suite sur le serveur (NAS).
//    Sans réseau (au fond du magasin…), la case reste cochée et part dès que
//    la connexion revient (file d'attente d'appli.js).
// 2. Toutes les 8 secondes, la page relit l'état pour afficher ce que
//    l'autre personne a coché de son côté.
(function () {
  const ticket = document.getElementById("ticket");
  if (!ticket) return;
  const sync = document.getElementById("sync");
  const file = window.MenusHorsLigne;

  function statut(texte, alerte) {
    sync.textContent = texte;
    sync.classList.toggle("alerte", !!alerte); // reste visible en bas de l'écran
  }

  function heure() {
    return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }

  function afficher(box, coche) {
    box.checked = coche;
    box.closest(".item").classList.toggle("done", coche);
  }

  function majCompteurs(articles) {
    const total = {}, faits = {};
    Object.values(articles).forEach(a => {
      total[a.m] = (total[a.m] || 0) + 1;
      if (a.c) faits[a.m] = (faits[a.m] || 0) + 1;
    });
    document.querySelectorAll(".shops a[data-shop]").forEach(el => {
      const m = el.dataset.shop;
      el.querySelector("span").textContent = `${faits[m] || 0} / ${total[m] || 0}`;
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

  ticket.addEventListener("change", async e => {
    const box = e.target;
    if (box.type !== "checkbox") return;
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
        if (box && box.checked !== a.c) afficher(box, a.c);
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

  // « Tout décocher » demande le réseau : on prévient au lieu d'afficher une erreur du navigateur.
  ticket.querySelectorAll("form").forEach(f => f.addEventListener("submit", e => {
    if (!navigator.onLine) {
      e.preventDefault();
      statut("Pas de réseau : « Tout décocher » sera possible une fois la connexion revenue.", true);
    }
  }));

  appliquerAttente();
  relire();
  setInterval(relire, 8000);
  window.addEventListener("online", relire);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) relire(); });
})();
