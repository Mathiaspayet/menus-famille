"""Tests : python manage.py test (lancés aussi par GitHub Actions avant de construire l'image)."""
import copy
import io
import json

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Article, Jour, ResteFrigo
from .plan_io import PlanInvalide, exporter_plan, importer_plan

PLAN = {
    "version": 1,
    "personnes": ["Parent 1", "Parent 2", "Enfant 1", "Enfant 2"],
    "debut": "2026-11-16",
    "recettes": {
        "curry": {"t": "Curry de poulet", "time": "25 min", "boxes": True, "ing": ["poulet"], "steps": ["Cuire."],
                  "por": [["Curry", "330 g", "410 g", "140 g", "100 g"]], "des": "1 clémentine chacun"},
        "soupe": {"t": "Soupe", "time": "20 min", "ing": [], "steps": [], "por": []},
    },
    "petits_dejeuners": {"A": {"t": "Tartines", "days": "lundi", "rows": [["Pain", "50 g", "60 g", "50 g", "35 g"]]}},
    "semaines": [{"n": 1, "label": "16 – 22 nov.", "days": [
        {"iso": "2026-11-16", "full": "Lundi 16 nov.", "todo": [], "pdj": "A", "midi": {"lbl": "Repas habituel"},
         "gouter": None, "soir": "curry"},
        {"iso": "2026-11-17", "full": "Mardi 17 nov.", "todo": ["Sortir le poisson"], "pdj": None,
         "midi": {"lbl": "Boîte", "sub": "reste du curry", "r": "curry", "box": True}, "gouter": "1 pomme", "soir": "soupe"},
    ]}],
    "listes": [{"label": "Lun. 16 nov.", "shop": "2026-11-16", "range": "du lun. au lun.", "shops": {
        "primeur": [{"c": "Fruits", "items": [["Pommes", "6", "", 0, 0], ["Kiwis", "4", "", 0, 0]]}],
        "boucher": [{"c": "Volaille", "items": [["Poulet", "625 g", "À congeler", 1, 0]]}],
    }}],
    "infos_html": "<div class='card'>Infos</div>",
}


class ImportExportTests(TestCase):
    def test_import_puis_export_aller_retour(self):
        resume = importer_plan(copy.deepcopy(PLAN))
        self.assertEqual(resume, {"recettes": 2, "jours": 2, "listes": 1, "articles": 3})
        export = exporter_plan()
        importer_plan(export)  # le fichier exporté est réimportable tel quel
        self.assertEqual(Jour.objects.count(), 2)
        self.assertEqual(Article.objects.count(), 3)

    def test_les_cases_cochees_survivent_a_un_nouvel_import(self):
        importer_plan(copy.deepcopy(PLAN))
        Article.objects.filter(nom="Pommes").update(coche=True)
        importer_plan(copy.deepcopy(PLAN))
        self.assertTrue(Article.objects.get(nom="Pommes").coche)
        self.assertFalse(Article.objects.get(nom="Kiwis").coche)

    def test_recette_inconnue_refusee_sans_rien_casser(self):
        importer_plan(copy.deepcopy(PLAN))
        mauvais = copy.deepcopy(PLAN)
        mauvais["semaines"][0]["days"][0]["soir"] = "n_existe_pas"
        with self.assertRaises(PlanInvalide):
            importer_plan(mauvais)
        self.assertEqual(Jour.objects.count(), 2)  # l'ancien plan est intact

    def test_frigo_remplace_si_present_dans_le_fichier(self):
        importer_plan(copy.deepcopy(PLAN))
        ResteFrigo.objects.create(nom="Courgettes")
        importer_plan(copy.deepcopy(PLAN))  # pas de clé "frigo" : on n'y touche pas
        self.assertEqual(ResteFrigo.objects.count(), 1)
        avec = copy.deepcopy(PLAN)
        avec["frigo"] = [{"nom": "Carottes", "quantite": "300 g"}]
        importer_plan(avec)
        self.assertEqual(list(ResteFrigo.objects.values_list("nom", flat=True)), ["Carottes"])


class EcransTests(TestCase):
    def setUp(self):
        importer_plan(copy.deepcopy(PLAN))
        self.parent1 = User.objects.create_user("parent1", password="motdepasse-test")
        self.parent2 = User.objects.create_user("parent2", password="motdepasse-test", is_staff=True)

    def test_connexion_obligatoire(self):
        self.assertEqual(self.client.get("/courses/").status_code, 302)
        self.assertEqual(self.client.get("/sante/").status_code, 200)

    def test_pages_principales(self):
        self.client.force_login(self.parent1)
        for url in ["/jour/2026-11-16/", "/jour/2026-11-17/", "/petit-dej/", "/courses/", "/frigo/", "/infos/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get("/jour/2026-11-16/"), "Curry de poulet")
        self.assertEqual(self.client.get("/jour/pas-une-date/").status_code, 404)

    def test_cocher_partage_entre_deux_personnes(self):
        a = Article.objects.get(nom="Pommes")
        self.client.force_login(self.parent1)
        r = self.client.post(f"/article/{a.id}/cocher/", data=json.dumps({"coche": True}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.client.force_login(self.parent2)
        etat = self.client.get(f"/courses/{a.liste_id}/etat/").json()["articles"]
        self.assertTrue(etat[str(a.id)]["c"])
        self.assertEqual(Article.objects.get(pk=a.id).coche_par, self.parent1)

    def test_frigo_ajout_et_retrait(self):
        self.client.force_login(self.parent1)
        self.client.post("/frigo/", {"nom": "Courgettes", "quantite": "300 g"})
        r = ResteFrigo.objects.get()
        self.assertContains(self.client.get("/frigo/"), "Courgettes")
        self.client.post(f"/frigo/{r.id}/retirer/")
        self.assertFalse(ResteFrigo.objects.exists())

    def test_import_reserve_a_l_equipe(self):
        self.client.force_login(self.parent1)
        self.assertEqual(self.client.get("/plan/").status_code, 302)
        self.client.force_login(self.parent2)
        fichier = io.BytesIO(json.dumps(PLAN).encode())
        fichier.name = "plan.json"
        r = self.client.post("/plan/", {"fichier": fichier})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/export.json").json()["version"], 1)


# ---------------------------------------------------------------------------
# Version affichée et serveur MCP
# ---------------------------------------------------------------------------
import base64  # noqa: E402
import hashlib  # noqa: E402
from urllib.parse import parse_qs, urlsplit  # noqa: E402

from django.test import override_settings  # noqa: E402

from .models import JetonOAuth, ListeCourses  # noqa: E402

RETOUR = "https://claude.ai/api/mcp/auth_callback"
VERIFICATEUR = "v" * 50
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFICATEUR.encode()).digest()).rstrip(b"=").decode()


class VersionTests(TestCase):
    @override_settings(BUILD_VERSION="0123456789abcdef", BUILD_DATE="2026-11-21T08:30:00Z")
    def test_version_en_bas_de_page(self):
        u = User.objects.create_user("parent1", password="motdepasse-test")
        self.client.force_login(u)
        importer_plan(copy.deepcopy(PLAN))
        r = self.client.get("/jour/2026-11-16/")
        self.assertContains(r, "Version du 21 novembre 2026 à 09:30")  # heure de Paris
        self.assertContains(r, "0123456")


class McpTests(TestCase):
    def setUp(self):
        importer_plan(copy.deepcopy(PLAN))
        self.parent1 = User.objects.create_user("parent1", password="motdepasse-test", first_name="Parent 1")
        self.parent2 = User.objects.create_user("parent2", password="motdepasse-test", is_staff=True)

    # --- parcours de connexion, comme le fait Claude ---------------------------
    def connecter(self, utilisateur):
        """Enregistrement → autorisation → échange du code. Renvoie les jetons."""
        meta = self.client.get("/.well-known/oauth-authorization-server").json()
        r = self.client.post(urlsplit(meta["registration_endpoint"]).path, data=json.dumps(
            {"client_name": "Claude", "redirect_uris": [RETOUR], "token_endpoint_auth_method": "none"}),
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        client_id = r.json()["client_id"]
        params = {"response_type": "code", "client_id": client_id, "redirect_uri": RETOUR, "state": "xyz",
                  "code_challenge": CHALLENGE, "code_challenge_method": "S256", "scope": "menus"}
        self.client.force_login(utilisateur)
        page = self.client.get("/oauth/autoriser/", params)
        self.assertContains(page, "Autoriser Claude ?")
        r = self.client.post("/oauth/autoriser/", {**params, "decision": "autoriser"})
        self.client.logout()
        retour = urlsplit(r["Location"])
        self.assertEqual(f"{retour.scheme}://{retour.netloc}{retour.path}", RETOUR)
        q = parse_qs(retour.query)
        self.assertEqual(q["state"], ["xyz"])
        r = self.client.post("/oauth/jeton/", {"grant_type": "authorization_code", "code": q["code"][0],
                                               "redirect_uri": RETOUR, "client_id": client_id,
                                               "code_verifier": VERIFICATEUR})
        self.assertEqual(r.status_code, 200, r.content)
        return {**r.json(), "client_id": client_id}

    def rpc(self, jeton, methode, params=None, id_=1):
        r = self.client.post("/mcp", data=json.dumps({"jsonrpc": "2.0", "id": id_, "method": methode,
                                                      "params": params or {}}),
                             content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {jeton}")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def outil(self, jeton, nom_outil, **arguments):
        resultat = self.rpc(jeton, "tools/call", {"name": nom_outil, "arguments": arguments})["result"]
        texte = resultat["content"][0]["text"]
        return resultat["isError"], (texte if resultat["isError"] else json.loads(texte))

    # --- tests ------------------------------------------------------------------
    def test_sans_jeton_claude_est_invite_a_se_connecter(self):
        r = self.client.post("/mcp", data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 401)
        self.assertIn('resource_metadata="https://testserver/.well-known/oauth-protected-resource/mcp"',
                      r["WWW-Authenticate"])
        meta = self.client.get("/.well-known/oauth-protected-resource/mcp").json()
        self.assertEqual(meta["resource"], "https://testserver/mcp")
        r = self.client.post("/mcp", data="{}", content_type="application/json", HTTP_AUTHORIZATION="Bearer faux")
        self.assertEqual(r.status_code, 401)
        self.assertIn('error="invalid_token"', r["WWW-Authenticate"])

    def test_parcours_complet_et_liste_des_outils(self):
        jetons = self.connecter(self.parent1)
        init = self.rpc(jetons["access_token"], "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                               "clientInfo": {"name": "test", "version": "1"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        r = self.client.post("/mcp", data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                             content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {jetons['access_token']}")
        self.assertEqual(r.status_code, 202)
        noms = {t["name"] for t in self.rpc(jetons["access_token"], "tools/list")["result"]["tools"]}
        self.assertTrue({"lire_jour", "modifier_jour", "cocher_articles", "remplacer_liste_courses",
                         "ajouter_au_frigo"} <= noms)
        erreur, jour = self.outil(jetons["access_token"], "lire_jour", date="2026-11-16")
        self.assertFalse(erreur)
        self.assertEqual(jour["soir"]["titre"], "Curry de poulet")

    def test_renouvellement_du_jeton(self):
        jetons = self.connecter(self.parent1)
        r = self.client.post("/oauth/jeton/", {"grant_type": "refresh_token", "refresh_token": jetons["refresh_token"],
                                               "client_id": jetons["client_id"]})
        self.assertEqual(r.status_code, 200)
        nouveaux = r.json()
        self.rpc(nouveaux["access_token"], "ping")
        # L'ancien jeton de renouvellement ne sert plus, l'ancien accès non plus.
        r = self.client.post("/oauth/jeton/", {"grant_type": "refresh_token", "refresh_token": jetons["refresh_token"],
                                               "client_id": jetons["client_id"]})
        self.assertEqual(r.json()["error"], "invalid_grant")
        r = self.client.post("/mcp", data="{}", content_type="application/json",
                             HTTP_AUTHORIZATION=f"Bearer {jetons['access_token']}")
        self.assertEqual(r.status_code, 401)

    def test_code_refuse_sans_le_bon_verificateur_pkce(self):
        meta = self.client.post("/oauth/enregistrer/", data=json.dumps({"redirect_uris": [RETOUR]}),
                                content_type="application/json").json()
        params = {"response_type": "code", "client_id": meta["client_id"], "redirect_uri": RETOUR,
                  "code_challenge": CHALLENGE, "code_challenge_method": "S256", "decision": "autoriser"}
        self.client.force_login(self.parent1)
        code = parse_qs(urlsplit(self.client.post("/oauth/autoriser/", params)["Location"]).query)["code"][0]
        r = self.client.post("/oauth/jeton/", {"grant_type": "authorization_code", "code": code, "redirect_uri": RETOUR,
                                               "client_id": meta["client_id"], "code_verifier": "w" * 50})
        self.assertEqual(r.json()["error"], "invalid_grant")
        self.assertFalse(JetonOAuth.objects.exists())

    def test_adresse_de_retour_etrangere_refusee(self):
        r = self.client.post("/oauth/enregistrer/", data=json.dumps({"redirect_uris": ["https://pirate.example/cb"]}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_autorisation_demande_la_connexion_et_peut_etre_refusee(self):
        meta = self.client.post("/oauth/enregistrer/", data=json.dumps({"redirect_uris": [RETOUR]}),
                                content_type="application/json").json()
        params = {"response_type": "code", "client_id": meta["client_id"], "redirect_uri": RETOUR, "state": "s",
                  "code_challenge": CHALLENGE, "code_challenge_method": "S256"}
        r = self.client.get("/oauth/autoriser/", params)
        self.assertTrue(r["Location"].startswith("/connexion/?next="))
        self.client.force_login(self.parent1)
        r = self.client.post("/oauth/autoriser/", {**params, "decision": "refuser"})
        self.assertIn("error=access_denied", r["Location"])

    def test_remplacer_un_repas_et_cocher(self):
        jeton = self.connecter(self.parent1)["access_token"]
        erreur, message = self.outil(jeton, "modifier_jour", date="2026-11-16", soir="inconnue")
        self.assertTrue(erreur)
        self.assertIn("n'existe pas", message)
        erreur, _ = self.outil(jeton, "enregistrer_recette", cle="omelette", titre="Omelette", ingredients=["6 œufs"],
                               etapes=["Battre", "Cuire"], portions=[["Omelette", "2", "2", "1", "1"]])
        self.assertFalse(erreur)
        erreur, _ = self.outil(jeton, "modifier_jour", date="2026-11-16", soir="omelette", remarque="curry reporté")
        self.assertFalse(erreur)
        self.assertEqual(Jour.objects.get(date="2026-11-16").soir.titre, "Omelette")

        pommes = Article.objects.get(nom="Pommes")
        erreur, _ = self.outil(jeton, "cocher_articles", ids=[pommes.id])
        self.assertFalse(erreur)
        pommes.refresh_from_db()
        self.assertTrue(pommes.coche)
        self.assertEqual(pommes.coche_par, self.parent1)
        _, liste = self.outil(jeton, "lire_courses", date_courses="2026-11-16", magasin="primeur")
        self.assertEqual(liste["magasins"]["primeur"]["faits"], 1)
        self.assertEqual(liste["magasins"]["primeur"]["rayons"][0]["articles"][0]["coche_par"], "Parent 1")

    def test_ajouter_un_article_dans_son_rayon(self):
        jeton = self.connecter(self.parent1)["access_token"]
        self.outil(jeton, "ajouter_article", date_courses="2026-11-16", magasin="primeur", nom="Poires",
                   quantite="4", rayon="Fruits")
        noms = list(Article.objects.filter(magasin="primeur").values_list("nom", flat=True))
        self.assertEqual(noms, ["Pommes", "Kiwis", "Poires"])
        erreur, message = self.outil(jeton, "ajouter_article", date_courses="2026-11-16", magasin="epicier", nom="x")
        self.assertTrue(erreur)

    def test_regenerer_une_liste_garde_les_cases_cochees(self):
        jeton = self.connecter(self.parent1)["access_token"]
        Article.objects.filter(nom="Pommes").update(coche=True)
        erreur, resultat = self.outil(jeton, "remplacer_liste_courses", date_courses="2026-11-16", magasins={
            "primeur": [{"rayon": "Fruits", "articles": [{"nom": "Pommes", "quantite": "8"}, {"nom": "Clémentines"}]}]})
        self.assertFalse(erreur, resultat)
        self.assertEqual(Article.objects.count(), 2)
        self.assertTrue(Article.objects.get(nom="Pommes").coche)
        self.assertEqual(Article.objects.get(nom="Pommes").quantite, "8")
        # Nouvelle liste : le libellé est obligatoire
        erreur, _ = self.outil(jeton, "remplacer_liste_courses", date_courses="2026-11-23", magasins={})
        self.assertTrue(erreur)
        erreur, _ = self.outil(jeton, "remplacer_liste_courses", date_courses="2026-11-23", libelle="Lun. 23 nov.",
                               magasins={"boucher": []})
        self.assertFalse(erreur)
        self.assertTrue(ListeCourses.objects.filter(date_courses="2026-11-23").exists())

    def test_frigo(self):
        jeton = self.connecter(self.parent1)["access_token"]
        _, ajout = self.outil(jeton, "ajouter_au_frigo", nom="Courgettes", quantite="300 g")
        _, frigo = self.outil(jeton, "lire_frigo")
        self.assertEqual(frigo[0]["ajoute_par"], "Parent 1")
        self.outil(jeton, "retirer_du_frigo", id=ajout["id"])
        self.assertFalse(ResteFrigo.objects.exists())

    def test_remplacer_tout_le_plan_reserve_a_l_equipe(self):
        jeton1 = self.connecter(self.parent1)["access_token"]
        erreur, _ = self.outil(jeton1, "importer_plan_complet", plan=copy.deepcopy(PLAN))
        self.assertTrue(erreur)
        jeton2 = self.connecter(self.parent2)["access_token"]
        _, export = self.outil(jeton2, "exporter_plan_complet")
        export["semaines"][0]["days"][0]["remarque"] = "modifié par Claude"
        erreur, _ = self.outil(jeton2, "importer_plan_complet", plan=export)
        self.assertFalse(erreur)
        self.assertEqual(Jour.objects.get(date="2026-11-16").remarque, "modifié par Claude")

    def test_parametres_invalides_et_outil_inconnu(self):
        jeton = self.connecter(self.parent1)["access_token"]
        erreur, message = self.outil(jeton, "lire_jour", date="demain")
        self.assertTrue(erreur)
        erreur, message = self.outil(jeton, "lire_jour", jour="2026-11-16")
        self.assertIn("inconnu", message)
        self.assertEqual(self.rpc(jeton, "tools/call", {"name": "nexiste_pas"})["error"]["code"], -32602)
        self.assertEqual(self.rpc(jeton, "resources/list")["error"]["code"], -32601)

    def test_origine_etrangere_refusee(self):
        jeton = self.connecter(self.parent1)["access_token"]
        r = self.client.post("/mcp", data="{}", content_type="application/json", HTTP_ORIGIN="https://pirate.example",
                             HTTP_AUTHORIZATION=f"Bearer {jeton}")
        self.assertEqual(r.status_code, 403)
