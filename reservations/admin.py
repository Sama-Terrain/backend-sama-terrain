from django.contrib import admin

from .models import Commande, Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['id', 'amateur', 'creneau', 'statut', 'montant_total', 'cree_le']
    list_filter = ['statut']


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ['id', 'amateur', 'cree_le']
