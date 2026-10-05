from django.contrib import admin

from .models import DemandeGerant, Employe, JournalAction


@admin.register(DemandeGerant)
class DemandeGerantAdmin(admin.ModelAdmin):
    list_display = ['user', 'nom_complexe', 'quartier', 'statut', 'cree_le']
    list_filter = ['statut']


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display = ['user', 'proprietaire', 'ajoute_le']


@admin.register(JournalAction)
class JournalActionAdmin(admin.ModelAdmin):
    list_display = ['auteur_nom', 'action', 'description', 'proprietaire', 'mis_a_jour_le']
    list_filter = ['action']
