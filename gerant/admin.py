from django.contrib import admin

from .models import DemandeGerant


@admin.register(DemandeGerant)
class DemandeGerantAdmin(admin.ModelAdmin):
    list_display = ['user', 'nom_complexe', 'quartier', 'statut', 'cree_le']
    list_filter = ['statut']
