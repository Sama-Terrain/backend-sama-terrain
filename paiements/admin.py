from django.contrib import admin

from .models import Abonnement, Paiement, Portefeuille, Retrait


@admin.register(Abonnement)
class AbonnementAdmin(admin.ModelAdmin):
    list_display = ['gerant', 'statut', 'date_fin_essai', 'date_fin_abonnement']


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['type', 'montant', 'moyen_paiement', 'cree_le']
    list_filter = ['type']


@admin.register(Portefeuille)
class PortefeuilleAdmin(admin.ModelAdmin):
    list_display = ['gerant', 'operateur', 'numero', 'mis_a_jour_le']


@admin.register(Retrait)
class RetraitAdmin(admin.ModelAdmin):
    list_display = ['gerant', 'montant', 'operateur', 'numero', 'statut', 'cree_le', 'traite_le']
    list_filter = ['statut', 'operateur']
