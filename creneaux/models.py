from django.db import models
from django.utils import timezone

from terrains.models import Terrain


class Creneau(models.Model):
    """
    Un créneau horaire réservable pour un terrain donné, à une date et
    une heure précises (ex: "Elite Arena, le 15/03/2026, 18h-19h").
    """

    class Statut(models.TextChoices):
        # Personne n'a réservé ce créneau, ou une réservation a expiré/été annulée.
        DISPONIBLE = 'disponible', 'Disponible'
        # Une réservation vient d'être créée, en attente du paiement de l'avance.
        EN_ATTENTE = 'en_attente', 'En attente de paiement'
        # Le paiement de l'avance a été confirmé par PayTech.
        CONFIRME = 'confirme', 'Confirmé'

    terrain = models.ForeignKey(Terrain, on_delete=models.CASCADE, related_name='creneaux')

    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()

    # Chaque créneau a son propre prix (permet au gérant de faire varier
    # les tarifs selon l'heure : prix week-end, heures de pointe, etc.)
    prix = models.PositiveIntegerField(help_text="Prix en FCFA")

    # Champs remplis par le service IA (FastAPI, voir /api/ia/predictions/)
    # à partir des vraies statistiques de réservation. Vides tant qu'aucune
    # analyse n'a encore été demandée pour ce terrain.
    class NiveauDemande(models.TextChoices):
        FAIBLE = 'faible', 'Faible'
        MOYEN = 'moyen', 'Moyen'
        ELEVE = 'eleve', 'Élevé'

    niveau_demande = models.CharField(
        max_length=10, choices=NiveauDemande.choices, null=True, blank=True,
    )
    prix_recommande_ia = models.PositiveIntegerField(null=True, blank=True)
    derniere_maj_ia = models.DateTimeField(null=True, blank=True)

    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.DISPONIBLE)

    # Partie du terrain louée par ce créneau.
    # 0 = le terrain complet : c'est le cas de tous les terrains simples
    #     (et de tous les créneaux créés avant l'ajout des portions).
    # 1, 2, 3... = une portion d'un terrain divisible.
    portion = models.PositiveSmallIntegerField(default=0)

    class Meta:
        # Un terrain ne peut pas avoir deux fois le même créneau : même date,
        # même heure ET même portion (le terrain complet et la portion 1 de
        # 20h sont deux créneaux différents).
        unique_together = ['terrain', 'date', 'heure_debut', 'portion']
        ordering = ['date', 'heure_debut', 'portion']

    def __str__(self):
        texte = f"{self.terrain.nom} - {self.date} {self.heure_debut}-{self.heure_fin}"
        if self.libelle_portion:
            texte += f" ({self.libelle_portion})"
        return texte

    @property
    def libelle_portion(self):
        """
        Texte montré aux utilisateurs : "Terrain complet" ou "Portion 2".
        Vide pour un terrain simple : il n'y a rien à préciser.
        """
        if self.terrain.nombre_portions <= 1:
            return ''
        if self.portion == 0:
            return 'Terrain complet'
        return f'Portion {self.portion}'

    def creneaux_en_conflit(self):
        """
        Créneaux du même terrain, à la même date et à la même heure, qui ne
        peuvent pas être loués en même temps que celui-ci :

        - Le terrain complet occupe toute la surface : il est en conflit
          avec chacune des portions.
        - Une portion n'occupe qu'une partie du terrain : elle n'est en
          conflit qu'avec le terrain complet. Les autres portions restent
          libres, d'autres joueurs peuvent les louer.

        Pour un terrain simple, il n'existe qu'un seul créneau à cette heure :
        la liste est vide, rien ne change par rapport à avant.
        """
        meme_heure = Creneau.objects.filter(
            terrain_id=self.terrain_id, date=self.date, heure_debut=self.heure_debut,
        ).exclude(pk=self.pk)

        if self.portion == 0:
            return meme_heure
        return meme_heure.filter(portion=0)

    def est_reservable(self):
        """
        True si ce créneau peut être réservé maintenant : il est libre lui-même
        ET aucun créneau en conflit n'est déjà pris (en attente de paiement
        ou confirmé).

        Exemple : si la portion 1 est réservée, le terrain complet n'est plus
        réservable (il a besoin de toutes les portions), mais les portions 2
        et 3 le restent.
        """
        if self.statut != self.Statut.DISPONIBLE:
            return False
        return not self.creneaux_en_conflit().exclude(statut=self.Statut.DISPONIBLE).exists()

    def creer_ou_mettre_a_jour_portions(self):
        """
        Pour le créneau "terrain complet" d'un terrain divisible, crée (ou met
        à jour) un créneau par portion, à la même date et à la même heure.

        Ainsi le gérant continue de créer ses créneaux comme avant, sans
        s'occuper des portions : elles suivent automatiquement, au prix
        d'une portion qu'il a choisi sur la fiche du terrain (prix_portion).
        """
        nombre_portions = self.terrain.nombre_portions
        if self.portion != 0 or nombre_portions <= 1:
            return

        prix_portion = self.terrain.prix_portion

        for numero in range(1, nombre_portions + 1):
            creneau_portion, cree = Creneau.objects.get_or_create(
                terrain=self.terrain, date=self.date, heure_debut=self.heure_debut, portion=numero,
                defaults={'heure_fin': self.heure_fin, 'prix': prix_portion},
            )
            # On ne modifie jamais une portion déjà réservée : son prix a été
            # annoncé au joueur au moment de sa réservation.
            if not cree and creneau_portion.statut == self.Statut.DISPONIBLE:
                creneau_portion.heure_fin = self.heure_fin
                creneau_portion.prix = prix_portion
                creneau_portion.save()


def adapter_portions_futures(terrain):
    """
    Appelée quand le gérant change le nombre de portions d'un terrain :
    adapte ses créneaux à venir qui sont encore libres.
    Les créneaux déjà réservés ne sont jamais touchés.
    """
    a_venir = Creneau.objects.filter(terrain=terrain, date__gte=timezone.localdate())

    # Portions qui n'existent plus (ex: passage de 3 à 2 portions, ou terrain
    # redevenu simple) : on supprime celles qui sont encore libres.
    derniere_portion = terrain.nombre_portions if terrain.nombre_portions > 1 else 0
    a_venir.filter(portion__gt=derniere_portion, statut=Creneau.Statut.DISPONIBLE).delete()

    # Nouvelles portions éventuelles, créées à partir du terrain complet.
    for creneau_complet in a_venir.filter(portion=0):
        creneau_complet.creer_ou_mettre_a_jour_portions()
