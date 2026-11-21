// Liste de courses partagée.
// 1. Cocher une case l'enregistre tout de suite sur le serveur (NAS).
// 2. Toutes les 8 secondes, la page relit l'état pour afficher ce que
//    l'autre personne a coché de son côté.
(function () {
  const ticket = document.getElementById("ticket");
  if (!ticket) return;
  const csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
  const sync = document.getElementById("sync");
  const magasin = ticket.dataset.magasin;

  function heure() {
    return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
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

  function afficher(box, coche) {
    box.checked = coche;
    box.closest(".item").classList.toggle("done", coche);
  }

  ticket.addEventListener("change", async e => {
    const box = e.target;
    if (box.type !== "checkbox") return;
    afficher(box, box.checked);
    try {
      const r = await fetch(box.dataset.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ coche: box.checked }),
      });
      if (!r.ok) throw new Error(r.status);
      sync.textContent = `Enregistré à ${heure()}`;
      relire();
    } catch (err) {
      afficher(box, !box.checked); // on annule : rien n'a été enregistré
      sync.textContent = "Pas de connexion au serveur : la case n'a pas été enregistrée.";
    }
  });

  let enCours = false;
  async function relire() {
    if (enCours || document.hidden) return;
    enCours = true;
    try {
      const r = await fetch(ticket.dataset.etat, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(r.status);
      const { articles } = await r.json();
      Object.entries(articles).forEach(([id, a]) => {
        const box = document.getElementById("a" + id);
        if (box && box.checked !== a.c) afficher(box, a.c);
      });
      majCompteurs(articles);
      sync.textContent = `À jour à ${heure()}`;
    } catch (err) {
      sync.textContent = "Hors ligne : nouvel essai dans quelques secondes…";
    } finally {
      enCours = false;
    }
  }

  setInterval(relire, 8000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) relire(); });
})();
