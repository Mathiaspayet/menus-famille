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
