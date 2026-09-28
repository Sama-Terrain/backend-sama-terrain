from django.db.models import Avg, Count


def recalculer_note_terrain(terrain):
    """
    Recalcule note_moyenne et nombre_avis d'un terrain à partir de ses
    avis visibles, et sauvegarde le résultat.

    On stocke ces valeurs directement sur Terrain (plutôt que de les
    recalculer à chaque affichage) pour que la liste des terrains reste
    rapide à charger, même avec beaucoup d'avis.
    """
    stats = terrain.avis.filter(visible=True).aggregate(moyenne=Avg('note'), total=Count('id'))

    # On arrondit la note moyenne à 1 chiffre après la virgule pour l'affichage.
    terrain.note_moyenne = round(stats['moyenne'] or 0, 1)
    terrain.nombre_avis = stats['total']
    terrain.save()
