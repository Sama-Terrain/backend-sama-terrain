from django.contrib import admin

from .models import Creneau


@admin.register(Creneau)
class CreneauAdmin(admin.ModelAdmin):
    list_display = ['terrain', 'date', 'heure_debut', 'heure_fin', 'prix', 'statut']
    list_filter = ['statut', 'date']
