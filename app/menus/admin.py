"""Administration : corrections à la main et gestion des comptes (/admin/)."""
from django.contrib import admin

from .models import Article, Jour, ListeCourses, PetitDej, Plan, Recette, ResteFrigo


@admin.register(Recette)
class RecetteAdmin(admin.ModelAdmin):
    list_display = ("titre", "cle", "duree", "boites")
    search_fields = ("titre", "cle")


@admin.register(Jour)
class JourAdmin(admin.ModelAdmin):
    list_display = ("date", "libelle", "semaine", "soir", "remarque")
    list_filter = ("semaine",)
    autocomplete_fields = ("midi_recette", "soir", "a_preparer")


class ArticleInline(admin.TabularInline):
    model = Article
    extra = 0
    fields = ("magasin", "categorie", "nom", "quantite", "commentaire", "congeler", "verifier", "coche")


@admin.register(ListeCourses)
class ListeCoursesAdmin(admin.ModelAdmin):
    list_display = ("libelle", "date_courses", "periode")
    inlines = [ArticleInline]


@admin.register(ResteFrigo)
class ResteFrigoAdmin(admin.ModelAdmin):
    list_display = ("nom", "quantite", "remarque", "ajoute_le", "ajoute_par")


admin.site.register(PetitDej)
admin.site.register(Plan)
