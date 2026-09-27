"""Géo Cairn - Logiciel de gestion de traces GPX."""

#: Nom affiché : titre de la fenêtre, menus, installeur, fichiers GPX produits.
APP_NAME = "Géo Cairn"

#: Nom technique, sans accent ni espace : dossiers, exécutable, mutex Windows,
#: en-tête réseau. Un chemin ou un identifiant accentué se heurte tôt ou tard à
#: un outil qui le recode mal ; le nom affiché ne sert donc jamais de chemin.
APP_SLUG = "GeoCairn"

APP_VERSION = "0.4"

__all__ = ["APP_NAME", "APP_SLUG", "APP_VERSION"]
