"""
Modèle de données.

On sépare deux choses :
- LE PLAN : recettes, petits-déjeuners, jours, listes de courses. Il est
  remplacé en bloc à chaque import (fichier JSON produit avec Claude).
- L'ÉTAT : articles cochés, restes au frigo, remarques. C'est ce que la
  famille modifie au quotidien ; un nouvel import conserve les cases cochées.
"""
from django.conf import settings
from django.db import models


class Plan(models.Model):
    """Réglages généraux du plan importé (une seule ligne en base)."""

    personnes = models.JSONField(default=list, help_text="Ordre des colonnes des tableaux de portions.")
    debut = models.DateField(null=True, blank=True)
    infos_html = models.TextField(blank=True, help_text="Contenu de l'onglet Infos (HTML).")
    importe_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "plan"

    def __str__(self):
        return f"Plan importé le {self.importe_le:%d/%m/%Y}" if self.importe_le else "Plan"

    @classmethod
    def actuel(cls):
        plan, _ = cls.objects.get_or_create(pk=1)
        return plan


class Recette(models.Model):
    cle = models.SlugField(max_length=80, unique=True, help_text="Identifiant court, ex. curry_poulet.")
    titre = models.CharField(max_length=200)
    duree = models.CharField(max_length=80, blank=True)
    boites = models.BooleanField(default=False, help_text="Cuisiner 2 parts de plus pour les boîtes du lendemain.")
    boite_prep = models.BooleanField(default=False)
    feu = models.CharField("pot du feu", max_length=120, blank=True)
    dessert = models.CharField(max_length=300, blank=True)
    note = models.TextField(blank=True)
    ingredients = models.JSONField(default=list)
    etapes = models.JSONField(default=list)
    portions = models.JSONField(default=list, help_text="Lignes [aliment, part pers. 1, part pers. 2, ...].")

    class Meta:
        ordering = ["titre"]

    def __str__(self):
        return self.titre

    @property
    def dessert_court(self):
        return "Dessert : " + self.dessert.split(" (")[0] if self.dessert else ""


class PetitDej(models.Model):
    code = models.CharField(max_length=4, unique=True)
    titre = models.CharField(max_length=200)
    jours = models.CharField(max_length=200, blank=True)
    lignes = models.JSONField(default=list)
    preparation = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "formule de petit-déjeuner"
        verbose_name_plural = "formules de petit-déjeuner"

    def __str__(self):
        return f"{self.code} · {self.titre}"


class Jour(models.Model):
    date = models.DateField(unique=True)
    semaine = models.PositiveSmallIntegerField()
    semaine_libelle = models.CharField(max_length=60, blank=True)
    libelle = models.CharField(max_length=60, help_text="Ex. Lundi 16 nov.")
    a_faire = models.JSONField(default=list, blank=True)
    petit_dej = models.ForeignKey(PetitDej, null=True, blank=True, on_delete=models.SET_NULL)
    midi_texte = models.CharField(max_length=200, blank=True)
    midi_detail = models.CharField(max_length=300, blank=True)
    midi_recette = models.ForeignKey(Recette, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    midi_boite = models.BooleanField(default=False)
    gouter = models.CharField(max_length=300, blank=True)
    soir = models.ForeignKey(Recette, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    a_preparer = models.ForeignKey(Recette, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                   help_text="Recette à préparer ce soir pour le lendemain (boîte du lundi).")
    remarque = models.TextField(blank=True, help_text="Note libre : repas sauté, invités, etc.")

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return self.libelle


class ListeCourses(models.Model):
    libelle = models.CharField(max_length=60)
    date_courses = models.DateField(unique=True)
    periode = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["date_courses"]
        verbose_name = "liste de courses"
        verbose_name_plural = "listes de courses"

    def __str__(self):
        return f"Liste du {self.libelle}"


class Article(models.Model):
    MAGASINS = [("boucher", "Boucher"), ("primeur", "Primeur"), ("leclerc", "Leclerc")]

    liste = models.ForeignKey(ListeCourses, on_delete=models.CASCADE, related_name="articles")
    magasin = models.CharField(max_length=20, choices=MAGASINS)
    categorie = models.CharField(max_length=80, blank=True)
    ordre = models.PositiveIntegerField(default=0)
    nom = models.CharField(max_length=200)
    quantite = models.CharField(max_length=80, blank=True)
    commentaire = models.CharField(max_length=200, blank=True)
    congeler = models.BooleanField(default=False)
    verifier = models.BooleanField(default=False, help_text="Lire l'étiquette (allergène).")
    coche = models.BooleanField(default=False)
    coche_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    coche_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["liste", "magasin", "ordre"]

    def __str__(self):
        return f"{self.nom} ({self.quantite})"


class ResteFrigo(models.Model):
    nom = models.CharField(max_length=200)
    quantite = models.CharField(max_length=80, blank=True)
    remarque = models.CharField(max_length=200, blank=True)
    ajoute_le = models.DateTimeField(auto_now_add=True)
    ajoute_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-ajoute_le"]
        verbose_name = "reste au frigo"
        verbose_name_plural = "restes au frigo"

    def __str__(self):
        return f"{self.nom} {self.quantite}".strip()
