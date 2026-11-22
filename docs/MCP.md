# Connecter Claude à l'appli (serveur MCP)

L'appli contient un **serveur MCP** : une porte d'entrée qui permet à Claude (sur le web,
l'ordinateur ou le téléphone) de **lire et modifier directement** les menus, les courses et
le frigo. Fini l'export / import du fichier JSON pour une petite modification.

Rien à payer en plus : Claude utilise ton abonnement habituel (pas de clé API).

## Ce qu'il faut avant

- L'appli est accessible en **HTTPS depuis Internet** (proxy inversé du NAS, voir le guide
  d'installation). Claude se connecte depuis les serveurs d'Anthropic, pas depuis ta maison.
- Un compte dans l'appli pour chaque personne qui veut utiliser Claude.

Dans la suite, `https://menu.exemple.synology.me` est à remplacer par l'adresse de ton appli.

## Ajouter le connecteur dans Claude (une fois par personne)

1. Sur [claude.ai](https://claude.ai), ouvre **Personnaliser → Connecteurs**
   (lien direct : <https://claude.ai/customize/connectors>).
2. Clique sur **Ajouter**, puis **Ajouter un connecteur personnalisé**
   (*Add custom connector*).
3. Nom : `Menus famille`. URL du serveur MCP : `https://menu.exemple.synology.me/mcp`
   (avec `/mcp` à la fin). Clique sur **Continuer**.
4. Pour l'authentification, **garde les options marquées « Détecté »** (connexion avec
   enregistrement automatique), puis clique sur **Ajouter**.
5. Clique sur **Connecter**. La page de connexion de l'appli s'ouvre : connecte-toi avec ton
   compte habituel, puis clique sur **Autoriser**.
6. C'est prêt. Le connecteur est aussi disponible dans l'appli Claude du téléphone.

Chaque parent ajoute le connecteur dans **son propre compte Claude** et se connecte avec
**son propre compte de l'appli** : les cases cochées par Claude affichent alors le bon prénom.

## Exemples de demandes

- « Qu'est-ce qu'on mange ce soir ? »
- « On saute le curry de mardi, il reste des courgettes : propose autre chose et mets la liste
  de courses à jour. »
- « J'ai acheté le poulet et les pommes, coche-les. »
- « Note au frigo : 300 g de riz cuit. »
- « Prépare les menus de la semaine prochaine sur le même principe, avec la liste de courses. »
- Dans une conversation où Claude a préparé un menu (artefact) : « Recopie ce menu dans l'appli
  avec le connecteur Menus famille : infos, petits-déjeuners, recettes, les semaines et les
  listes de courses. »

L'appli sert à **consulter** ; c'est Claude qui tient les menus à jour. Il travaille par
morceaux : un lot de recettes, une semaine ou une liste de courses à la fois.

Dans une conversation, le connecteur s'active ou se désactive avec le bouton **+** →
**Connecteurs**.

## Ce que Claude peut faire (outils)

| Outil | Rôle |
|---|---|
| `lire_infos_famille` | personnes, consignes (onglet Infos), formules de petit-déj, semaines, listes |
| `lire_semaine`, `lire_jour` | les menus, avec les recettes complètes pour un jour |
| `lister_recettes`, `lire_recette` | les recettes et les jours où elles sont prévues |
| `lire_courses`, `lire_frigo` | la liste de courses unique, triée par urgence (avec ce qui est coché, et par qui), les restes |
| `exporter_plan_complet` | tout le plan au format JSON |
| `enregistrer_recettes` | créer ou modifier des recettes (par lots de 10) |
| `modifier_jour` | remplacer un repas, changer le « À faire », la remarque… |
| `enregistrer_semaine` | créer ou mettre à jour les jours d'une semaine |
| `supprimer_jours` | retirer des jours (semaine passée ou annulée) |
| `enregistrer_petits_dejeuners` | créer ou modifier les formules de petit-déjeuner |
| `modifier_infos_famille` | personnes et consignes de l'onglet Infos (comptes « équipe ») |
| `cocher_articles` | cocher ou décocher des articles |
| `ajouter_article`, `retirer_article` | modifier une liste de courses |
| `remplacer_liste_courses` | créer ou recalculer un lot de courses, chaque article avec sa date d'utilisation (les cases déjà cochées sont gardées) |
| `supprimer_liste_courses` | retirer une liste |
| `ajouter_au_frigo`, `retirer_du_frigo` | gérer les restes |
| `importer_plan_complet` | remplacer tout le plan (comptes « équipe » uniquement) |

Dans Claude, chaque outil peut être réglé sur *Toujours autoriser*, *Demander* ou *Bloqué*
(page du connecteur → permissions des outils).

## Retirer l'accès à Claude

- **Dans Claude** : page des connecteurs → Menus famille → **Déconnecter** ou **Retirer**.
- **Dans l'appli** (compte « équipe ») : **Administration → Connexions de Claude**,
  supprimer la ligne. Claude devra se reconnecter.

Sans aucune utilisation pendant 90 jours, la connexion expire d'elle-même.

## En cas de problème

| Symptôme | Que faire |
|---|---|
| « Couldn't reach the MCP server » | L'adresse doit être en `https://` et finir par `/mcp`. Tester l'adresse dans un navigateur en 4G : une erreur 401 (« Connexion à l'appli nécessaire ») est **normale** et prouve que le serveur répond. |
| « Bad Request (400) » sur la page de connexion | Le domaine manque dans `DJANGO_ALLOWED_HOSTS` (fichier `.env` du NAS). |
| « Cette application n'est pas enregistrée » | Retirer le connecteur dans Claude et l'ajouter à nouveau. |
| Claude ne voit pas les nouveaux outils après une mise à jour | Dans Claude, déconnecter puis reconnecter le connecteur. |
| Claude demande la permission à chaque modification | Page du connecteur → permissions des outils → *Toujours autoriser* pour les outils de confiance. |

Les messages d'erreur détaillés sont dans le journal du conteneur `menus_famille`
(Container Manager → Conteneur → Journal).

## Pour les curieux : comment ça marche

- `/mcp` reçoit des messages JSON-RPC (transport « Streamable HTTP » de MCP, réponses JSON
  simples, sans session). Versions du protocole : 2025-03-26, 2025-06-18 et 2025-11-25.
- La connexion suit la spécification d'autorisation MCP (OAuth 2.1) : découverte par
  `/.well-known/oauth-protected-resource` et `/.well-known/oauth-authorization-server`,
  enregistrement automatique de Claude (`/oauth/enregistrer/`), code avec PKCE
  (`/oauth/autoriser/`), jetons renouvelés (`/oauth/jeton/`). Seule l'empreinte des jetons
  est enregistrée en base.
- Seules les adresses de retour de Claude sont acceptées (`https://claude.ai/api/mcp/auth_callback`,
  et une adresse locale pour Claude Code).
- Code : `app/menus/mcp.py` (le serveur), `app/menus/mcp_outils.py` (les outils),
  `app/menus/oauth.py` (la connexion).

### Avec Claude Code (facultatif)

```bash
claude mcp add --transport http menus-famille https://menu.exemple.synology.me/mcp
```

Puis, dans Claude Code, `/mcp` → `menus-famille` → s'authentifier.
