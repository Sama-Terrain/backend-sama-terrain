from django.contrib import admin

from .models import Terrain, TerrainPhoto


class TerrainPhotoInline(admin.TabularInline):
    """Permet de voir/ajouter les photos directement depuis la page du terrain."""
    model = TerrainPhoto
    extra = 1


@admin.register(Terrain)
class TerrainAdmin(admin.ModelAdmin):
    list_display = ['nom', 'ville', 'gerant', 'prix_heure', 'actif']
    list_filter = ['ville', 'type', 'actif']
    inlines = [TerrainPhotoInline]
