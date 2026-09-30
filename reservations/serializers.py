from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from creneaux.models import Creneau

from .models import Commande, Reservation
from .utils import MESSAGE_CRENEAU_PRIS, bloquer_creneau


class ReservationSerializer(serializers.ModelSerializer):
    """
    Représentation complète d'une réservation, avec les infos du terrain
    et du créneau directement inclues (le frontend n'a pas besoin de faire
    d'appels supplémentaires pour afficher une carte de réservation).
    """

    # On inclut ici des champs provenant du créneau et du terrain liés à la réservation, 
    # pour que le frontend puisse afficher toutes les informations nécessaires sans avoir à faire des requêtes supplémentaires.
    terrain_id = serializers.IntegerField(source='creneau.terrain.id', read_only=True)
    terrain_nom = serializers.CharField(source='creneau.terrain.nom', read_only=True)
    terrain_image = serializers.SerializerMethodField()
    date = serializers.DateField(source='creneau.date', read_only=True)
    heure_debut = serializers.TimeField(source='creneau.heure_debut', read_only=True)
    heure_fin = serializers.TimeField(source='creneau.heure_fin', read_only=True)
    # "Portion 2", "Terrain complet", ou vide pour un terrain simple.
    libelle_portion = serializers.CharField(source='creneau.libelle_portion', read_only=True)
    reste_a_payer = serializers.IntegerField(read_only=True)
    ticket = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'id', 'statut', 'nom_complet', 'telephone',
            'montant_avance', 'montant_total', 'reste_a_payer',
            'moyen_paiement', 'transaction_id', 'cree_le',
            'terrain_id', 'terrain_nom', 'terrain_image', 'date', 'heure_debut', 'heure_fin',
            'libelle_portion', 'ticket',
        ]

    def get_terrain_image(self, reservation):
        # Même logique que TerrainListSerializer.get_image : la première
        # photo du terrain sert de vignette pour la carte de réservation.
        premiere_photo = reservation.creneau.terrain.photos.first()
        if not premiere_photo:
            return None

        # build_absolute_uri transforme "/media/xxx.jpg" en une URL complète
        # (http://.../media/xxx.jpg) utilisable directement par le frontend.
        request = self.context.get('request')
        url = premiere_photo.image.url
        return request.build_absolute_uri(url) if request else url

    def get_ticket(self, reservation):
        # Le ticket n'existe qu'une fois le paiement confirmé par l'IPN
        # (voir PaiementIPNView) : pas de ticket tant que c'est "en_attente".
        ticket = getattr(reservation, 'ticket', None) #getattr() est utilisé pour récupérer l'attribut 'ticket' de l'objet reservation. Si l'attribut n'existe pas, il renvoie None au lieu de lever une exception. Cela permet de gérer les cas où la réservation n'a pas encore de ticket associé (par exemple, si le paiement n'a pas été confirmé).
        if ticket is None:
            return None
        return {'id': ticket.id, 'code': str(ticket.code), 'utilise': ticket.utilise}


MONTANT_AVANCE_MINIMUM = 10000


class ReservationCreateSerializer(serializers.ModelSerializer):
    """
    Utilisé pour POST /api/reservations/.

    L'amateur choisit lui-même le montant de son avance (doit être
    strictement supérieur à 10 000 FCFA) : ce n'est pas le gérant qui
    l'impose. Le reste (montant total, statut...) est déduit côté serveur.
    """

    class Meta:
        model = Reservation
        fields = ['creneau', 'nom_complet', 'telephone', 'montant_avance']

    def validate_creneau(self, creneau):
        # est_reservable() tient compte des portions : une portion est refusée
        # si le terrain complet est pris, et inversement (voir Creneau).
        if not creneau.est_reservable():
            raise serializers.ValidationError(MESSAGE_CRENEAU_PRIS)

        #make_aware() est utilisé pour convertir un objet datetime naïf (sans information de fuseau horaire) 
        # en un objet datetime conscient (avec information de fuseau horaire). Cela est nécessaire car Django utilise des objets datetime conscients pour gérer les dates et heures.
        debut_creneau = timezone.make_aware(
            timezone.datetime.combine(creneau.date, creneau.heure_debut)
        )

        # On ne peut pas réserver un créneau qui est déjà passé : inutile de le montrer comme "disponible" 
        # dans la liste des créneaux, mais on vérifie quand même côté serveur pour éviter les réservations frauduleuses.
        if debut_creneau <= timezone.now():
            raise serializers.ValidationError("Ce créneau est déjà passé.")

        return creneau

    def validate_montant_avance(self, montant):
        if montant <= MONTANT_AVANCE_MINIMUM:
            raise serializers.ValidationError(
                f"L'avance doit être strictement supérieure à {MONTANT_AVANCE_MINIMUM:,} FCFA.".replace(',', ' ')
            )
        return montant

    def validate(self, data):
        # L'avance ne peut pas dépasser le prix total du créneau (sinon le
        # "reste à payer sur place" deviendrait négatif).
        if data['montant_avance'] >= data['creneau'].prix:
            raise serializers.ValidationError(
                {'montant_avance': "L'avance ne peut pas être supérieure ou égale au prix total du créneau."}
            )
        return data

    def create(self, validated_data):
        creneau = validated_data['creneau']

        # Tout se fait dans une transaction : si le créneau a été pris entre
        # temps, bloquer_creneau() lève une erreur et rien n'est enregistré.
        with transaction.atomic():
            # On bloque le créneau (après une dernière vérification sous
            # verrou) pour que personne d'autre ne puisse le réserver pendant
            # que le paiement est en cours.
            bloquer_creneau(creneau)

            # La réservation est créée "en_attente" : le paiement de l'avance
            # n'a pas encore été confirmé par PayTech.
            reservation = Reservation.objects.create(
                amateur=self.context['request'].user,
                montant_total=creneau.prix,
                **validated_data,
            )

        return reservation


class ReservationGroupeCreateSerializer(serializers.Serializer):
    """
    Utilisé pour POST /api/reservations/groupe/.

    Permet de réserver plusieurs créneaux d'UN MÊME terrain en une seule
    fois (ex: 18h ET 19h le même jour), avec une seule avance globale
    répartie au prorata du prix de chaque créneau. Crée une Commande qui
    regroupe les Reservation créées, pour un paiement PayTech unique.
    """

    creneaux = serializers.PrimaryKeyRelatedField(
        queryset=Creneau.objects.all(), many=True, allow_empty=False,
    )
    nom_complet = serializers.CharField(max_length=150)
    telephone = serializers.CharField(max_length=20)
    montant_avance = serializers.IntegerField()

    def validate_creneaux(self, creneaux):
        if len(creneaux) != len(set(c.id for c in creneaux)):
            raise serializers.ValidationError("Un même créneau ne peut pas être sélectionné deux fois.")

        if len({c.terrain_id for c in creneaux}) > 1:
            raise serializers.ValidationError("Tous les créneaux doivent appartenir au même terrain.")

        # On ne peut pas prendre, dans une même commande, le terrain complet
        # ET une de ses portions à la même heure : ils occupent la même surface.
        ids_choisis = {c.id for c in creneaux}
        for creneau in creneaux:
            if creneau.creneaux_en_conflit().filter(id__in=ids_choisis).exists():
                raise serializers.ValidationError(
                    "Vous ne pouvez pas réserver le terrain complet et une de ses portions à la même heure."
                )

        maintenant = timezone.now()
        for creneau in creneaux:
            if not creneau.est_reservable():
                raise serializers.ValidationError(f"Le créneau {creneau} n'est plus disponible.")
            debut = timezone.make_aware(timezone.datetime.combine(creneau.date, creneau.heure_debut))
            if debut <= maintenant:
                raise serializers.ValidationError(f"Le créneau {creneau} est déjà passé.")

        return creneaux

    def validate_montant_avance(self, montant):
        if montant <= MONTANT_AVANCE_MINIMUM:
            raise serializers.ValidationError(
                f"L'avance doit être strictement supérieure à {MONTANT_AVANCE_MINIMUM:,} FCFA.".replace(',', ' ')
            )
        return montant

    def validate(self, data):
        prix_total = sum(c.prix for c in data['creneaux'])
        if data['montant_avance'] >= prix_total:
            raise serializers.ValidationError(
                {'montant_avance': "L'avance ne peut pas être supérieure ou égale au prix total des créneaux choisis."}
            )
        return data

    def create(self, validated_data):
        creneaux = validated_data['creneaux']
        prix_total = sum(c.prix for c in creneaux)
        avance_totale = validated_data['montant_avance']

        # Tout ou rien : si un seul créneau a été pris entre temps, aucune
        # réservation de la commande n'est enregistrée (la transaction est annulée).
        with transaction.atomic():
            commande = Commande.objects.create(amateur=self.context['request'].user)

            # Répartition de l'avance au prorata du prix de chaque créneau, en
            # ajustant le dernier créneau pour que la somme retombe exactement
            # sur le montant saisi (les arrondis peuvent perdre 1 ou 2 FCFA).
            reservations = []
            avance_distribuee = 0
            for index, creneau in enumerate(creneaux):
                if index == len(creneaux) - 1:
                    avance_creneau = avance_totale - avance_distribuee
                else:
                    avance_creneau = round(avance_totale * creneau.prix / prix_total)
                    avance_distribuee += avance_creneau

                bloquer_creneau(creneau)
                reservation = Reservation.objects.create(
                    amateur=self.context['request'].user,
                    groupe=commande,
                    creneau=creneau,
                    nom_complet=validated_data['nom_complet'],
                    telephone=validated_data['telephone'],
                    montant_avance=avance_creneau,
                    montant_total=creneau.prix,
                )
                reservations.append(reservation)

        return commande, reservations
