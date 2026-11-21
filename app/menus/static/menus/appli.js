// Commun à toutes les pages : appli installable et utilisable sans réseau.
// 1. Active le service worker (/sw.js) qui garde une copie des pages ouvertes.
// 2. File d'attente des cases cochées sans réseau : elles sont envoyées dès
//    que la connexion revient (même si on a changé de page entre-temps).
// 3. Copie à l'avance les autres jours de la semaine et les autres magasins.
// 4. Propose d'installer l'appli sur l'écran d'accueil.
(function () {
  "use strict";

  // ------------------------------------------------------------ service worker
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  // ------------------------------------------------------------ file d'attente
  const CLE = "menus-en-attente";
  function lire() {
    try { return JSON.parse(localStorage.getItem(CLE) || "{}"); } catch (e) { return {}; }
  }
  function ecrire(file) {
    try { localStorage.setItem(CLE, JSON.stringify(file)); } catch (e) { /* stockage indisponible */ }
  }
  function jeton() {
    // Le cookie d'abord : une page gardée en copie peut porter un jeton périmé.
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    const champ = document.querySelector("input[name=csrfmiddlewaretoken]");
    return champ ? champ.value : "";
  }

  let envoiEnCours = null;
  async function envoyer() {
    if (envoiEnCours) return envoiEnCours;
    envoiEnCours = (async () => {
      const file = lire();
      let envoyes = 0, refuses = 0;
      for (const [id, { url, coche }] of Object.entries(file)) {
        let r;
        try {
          r = await fetch(url, {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": jeton() },
            body: JSON.stringify({ coche }),
          });
        } catch (e) {
          break; // toujours pas de réseau : on réessaiera plus tard
        }
        const json = (r.headers.get("Content-Type") || "").includes("json");
        if (r.ok && json) envoyes++;
        else if (r.status === 404 || r.status === 400) refuses++; // article retiré de la liste entre-temps
        else break; // session expirée, serveur indisponible… : on garde la case et on réessaiera
        const actuelle = lire();
        if (actuelle[id] && actuelle[id].coche === coche) { delete actuelle[id]; ecrire(actuelle); }
      }
      return { envoyes, refuses, restants: Object.keys(lire()).length };
    })();
    try { return await envoiEnCours; } finally { envoiEnCours = null; }
  }

  window.MenusHorsLigne = {
    ajouter(id, url, coche) { const f = lire(); f[id] = { url, coche }; ecrire(f); },
    enAttente: lire,
    envoyer,
  };

  window.addEventListener("online", envoyer);
  if (navigator.onLine && Object.keys(lire()).length) envoyer();

  // ------------------------------------------------------------ copies à l'avance
  // Les autres jours de la semaine affichée et les autres magasins de la liste,
  // pour pouvoir les ouvrir au supermarché même sans réseau.
  async function copierALAvance() {
    if (!navigator.onLine || !("caches" in window) || !navigator.serviceWorker || !navigator.serviceWorker.controller) return;
    const liens = [...document.querySelectorAll(".days a[href], .shops a[href]")].map(a => a.href)
      .filter(h => h !== location.href);
    for (const url of liens) {
      try {
        const copie = await caches.match(url);
        const date = copie && Date.parse(copie.headers.get("Date") || "");
        if (date && Date.now() - date < 30 * 60 * 1000) continue; // copie récente
        await fetch(url, { credentials: "same-origin" });
      } catch (e) { return; }
    }
  }
  window.addEventListener("load", () => setTimeout(copierALAvance, 1500));

  // ------------------------------------------------------------ installation
  const MASQUE = "menus-installation-masquee";
  const installee = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  function masqueeRecemment() {
    try { return Date.now() - Number(localStorage.getItem(MASQUE) || 0) < 30 * 86400000; } catch (e) { return false; }
  }
  function bandeau(html, action) {
    const nav = document.querySelector("nav.tabs");
    if (!nav || installee || masqueeRecemment() || document.getElementById("installer")) return;
    const div = document.createElement("div");
    div.id = "installer";
    div.className = "installer";
    div.innerHTML = html + '<button type="button" class="x" data-fermer>Plus tard</button>';
    div.addEventListener("click", async e => {
      if (e.target.closest("[data-fermer]")) {
        try { localStorage.setItem(MASQUE, String(Date.now())); } catch (err) { /* rien */ }
        div.remove();
      } else if (e.target.closest("[data-installer]") && action) {
        await action();
        div.remove();
      }
    });
    document.querySelector("main").prepend(div);
  }

  // Android (Chrome) : le navigateur propose lui-même l'installation.
  window.addEventListener("beforeinstallprompt", e => {
    e.preventDefault();
    bandeau('<span>Installez l\'appli sur ce téléphone : une icône, en plein écran, et la liste de courses même sans réseau.</span>' +
            '<button type="button" class="btn" data-installer>Installer</button>',
            async () => { e.prompt(); await e.userChoice; });
  });

  // iPhone (Safari) : pas de bouton possible, on explique le geste.
  const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent) && !/CriOS|FxiOS|EdgiOS/.test(navigator.userAgent);
  if (iphone && !installee) {
    bandeau('<span>Pour installer l\'appli : touchez <b>Partager</b> <span aria-hidden="true">⬆︎</span> puis ' +
            '<b>Sur l\'écran d\'accueil</b>.</span>');
  }
})();
