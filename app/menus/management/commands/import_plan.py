"""Importer un plan en ligne de commande : python manage.py import_plan fichier.json"""
import json

from django.core.management.base import BaseCommand, CommandError

from menus.plan_io import PlanInvalide, importer_plan


class Command(BaseCommand):
    help = "Remplace le plan (menus, recettes, listes) par celui du fichier JSON."

    def add_arguments(self, parser):
        parser.add_argument("fichier")

    def handle(self, *args, fichier, **options):
        try:
            with open(fichier, encoding="utf-8") as f:
                resume = importer_plan(json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(f"Lecture impossible : {e}")
        except PlanInvalide as e:
            raise CommandError(f"Plan refusé : {e}")
        self.stdout.write(self.style.SUCCESS(
            "Importé : {recettes} recettes, {jours} jours, {listes} listes, {articles} articles.".format(**resume)))
