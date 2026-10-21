from django.core.management.base import BaseCommand

from notifications.services import DUREE_CONSERVATION_LUES_JOURS, supprimer_anciennes_lues


class Command(BaseCommand):
    help = f"Supprime les notifications lues depuis plus de {DUREE_CONSERVATION_LUES_JOURS} jours."

    def handle(self, *args, **options):
        nombre = supprimer_anciennes_lues()
        self.stdout.write(self.style.SUCCESS(f"{nombre} notification(s) supprimée(s)."))
