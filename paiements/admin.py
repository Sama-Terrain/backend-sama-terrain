from django.contrib import admin

from .models import Abonnement, Paiement


@admin.register(Abonnement)
class AbonnementAdmin(admin.ModelAdmin):
    list_display = ['gerant', 'statut', 'date_fin_essai', 'date_fin_abonnement']


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['type', 'montant', 'moyen_paiement', 'cree_le']
    list_filter = ['type']
