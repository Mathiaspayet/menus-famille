from django.urls import path

from . import mcp, oauth, views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("sante/", views.sante, name="sante"),
    path("jour/<str:date>/", views.jour, name="jour"),
    path("jour/<str:date>/remarque/", views.jour_remarque, name="jour_remarque"),
    path("petit-dej/", views.petit_dej, name="petit_dej"),
    path("courses/", views.courses, name="courses"),
    path("courses/<int:liste_id>/", views.courses, name="courses_liste"),
    path("courses/<int:liste_id>/etat/", views.courses_etat, name="courses_etat"),
    path("courses/<int:liste_id>/decocher/", views.courses_decocher, name="courses_decocher"),
    path("article/<int:article_id>/cocher/", views.article_cocher, name="article_cocher"),
    path("frigo/", views.frigo, name="frigo"),
    path("frigo/<int:reste_id>/retirer/", views.frigo_retirer, name="frigo_retirer"),
    path("infos/", views.infos, name="infos"),
    path("export.json", views.exporter, name="exporter"),
    path("plan/", views.plan, name="plan"),
    # Serveur MCP pour Claude, et sa connexion OAuth (voir docs/MCP.md)
    path("mcp", mcp.point_mcp, name="mcp"),
    path("mcp/", mcp.point_mcp),
    path(".well-known/oauth-protected-resource", oauth.metadonnees_ressource),
    path(".well-known/oauth-protected-resource/mcp", oauth.metadonnees_ressource),
    path(".well-known/oauth-authorization-server", oauth.metadonnees_serveur),
    path("oauth/enregistrer/", oauth.enregistrer, name="oauth_enregistrer"),
    path("oauth/autoriser/", oauth.autoriser, name="oauth_autoriser"),
    path("oauth/jeton/", oauth.jeton, name="oauth_jeton"),
]
