"""Administration : corrections à la main et gestion des comptes (/admin/)."""
from django.contrib import admin

from .models import Article, ClientOAuth, Jour, JetonOAuth, ListeCourses, PetitDej, Plan, Recette, ResteFrigo


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


@admin.register(JetonOAuth)
class JetonOAuthAdmin(admin.ModelAdmin):
    """Supprimer une ligne déconnecte Claude de ce compte (il faudra le reconnecter)."""
    list_display = ("utilisateur", "client", "cree_le", "utilise_le", "rafraichissement_expire_le")
    fields = ("utilisateur", "client", "cree_le", "utilise_le", "rafraichissement_expire_le")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False


@admin.register(ClientOAuth)
class ClientOAuthAdmin(admin.ModelAdmin):
    list_display = ("nom", "client_id", "cree_le")
    readonly_fields = ("nom", "client_id", "redirect_uris", "cree_le")

    def has_add_permission(self, request):
        return False
