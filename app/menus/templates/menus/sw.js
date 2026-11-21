// Service worker de « Menus famille » : l'appli reste consultable sans réseau.
// - Pages et état des courses : réseau d'abord (toujours à jour), copie gardée
//   sur le téléphone ; sans réseau (ou s'il traîne plus de 4 s), on sert la copie.
// - Fichiers statiques et polices : copie d'abord (leurs noms changent à chaque version).
// Le nom du cache contient la version : une mise à jour efface les anciennes copies.
const CACHE = "menus-{{ version }}";
const ATTENTE_MAX = 4000;
const JAMAIS = ["/mcp", "/oauth/", "/.well-known/", "/admin/", "/export.json", "/connexion/", "/deconnexion/",
                "/plan/", "/sante/", "/sw.js"];

const PAGE_HORS_LIGNE = `<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Hors connexion · Menus</title>
<body style="font-family:system-ui,sans-serif;background:#f4f5f1;color:#1b211e;margin:0;padding:40px 16px;text-align:center">
<h1 style="color:#1f3d31;font-weight:400">Pas de réseau</h1>
<p>Cette page n'a pas encore été ouverte sur ce téléphone : elle n'est pas disponible hors connexion.</p>
<p><a href="/courses/" style="color:#c8611f;font-weight:700">Ouvrir la liste de courses</a> ·
<a href="/" style="color:#c8611f;font-weight:700">Menus du jour</a></p></body></html>`;

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const nom of await caches.keys()) {
      if (nom.startsWith("menus-") && nom !== CACHE) await caches.delete(nom);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const polices = url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com";
  if (url.origin !== self.location.origin && !polices) return;
  if (!polices && JAMAIS.some(debut => url.pathname.startsWith(debut))) return;
  if (polices || url.pathname.startsWith("/static/")) {
    event.respondWith(copieDabord(req));
  } else {
    event.respondWith(reseauDabord(req));
  }
});

async function copieDabord(req) {
  const cache = await caches.open(CACHE);
  const copie = await cache.match(req);
  if (copie) return copie;
  const reponse = await fetch(req);
  if (reponse.ok || reponse.type === "opaque") cache.put(req, reponse.clone());
  return reponse;
}

function marquer(copie) {
  // Indique à la page qu'il s'agit d'une copie (affichée « hors connexion »).
  const entetes = new Headers(copie.headers);
  entetes.set("X-Menus-Copie", "1");
  return new Response(copie.body, { status: copie.status, statusText: copie.statusText, headers: entetes });
}

async function reseauDabord(req) {
  const cache = await caches.open(CACHE);
  const reseau = fetch(req).then(async reponse => {
    const versConnexion = new URL(reponse.url || req.url).pathname.startsWith("/connexion/");
    if (reponse.ok && reponse.type === "basic" && !versConnexion) {
      if (reponse.redirected) {
        // Ex. « / » renvoie vers le jour actuel : on garde une copie « propre » sous « / »,
        // pour que l'appli installée s'ouvre aussi sans réseau.
        const corps = await reponse.clone().blob();
        await cache.put(req, new Response(corps, { status: 200, headers: reponse.headers }));
      } else {
        await cache.put(req, reponse.clone());
      }
    }
    return reponse;
  });
  reseau.catch(() => {});
  const copie = cache.match(req);
  try {
    return await Promise.race([
      reseau,
      new Promise(r => setTimeout(r, ATTENTE_MAX)).then(async () => {
        const c = await copie;
        return c ? marquer(c) : reseau;   // réseau trop lent : la copie si on l'a
      }),
    ]);
  } catch (erreur) {
    const c = (await copie) || (new URL(req.url).pathname === "/" ? await accueilHorsLigne(cache) : null);
    if (c) return marquer(c);
    if (req.mode === "navigate") {
      return new Response(PAGE_HORS_LIGNE, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }
    return Response.error();
  }
}

// « / » redirige vers le jour actuel : sans réseau, on ouvre la copie du jour,
// sinon celle du jour le plus proche, sinon la liste de courses.
async function accueilHorsLigne(cache) {
  const d = new Date();
  const aujourdhui = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const jour = await cache.match(`/jour/${aujourdhui}/`);
  if (jour) return jour;
  const jours = (await cache.keys()).map(r => new URL(r.url).pathname).filter(p => p.startsWith("/jour/")).sort();
  const proche = jours.find(p => p >= `/jour/${aujourdhui}/`) || jours[jours.length - 1];
  return (proche && await cache.match(proche)) || await cache.match("/courses/", { ignoreSearch: true });
}
