from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Notre manager personnalisé pour le modèle User.
    Par défaut, Django utilise un UserManager qui se base sur le username.
    Ici, on se base sur l'email, donc on adapte le manager.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Crée et sauvegarde un utilisateur avec l'email et le mot de passe donnés.
        """
        if not email:
            raise ValueError("L'adresse email est obligatoire")

        email = self.normalize_email(email)

        # On crée l'utilisateur avec l'email et les champs supplémentaires
        user = self.model(
            email=email,
            **extra_fields
        )

        # On utilise la méthode set_password pour hasher le mot de passe avant de le sauvegarder
        user.set_password(password)
        user.save(using=self._db)

        return user

    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Crée et sauvegarde un superutilisateur avec l'email et le mot de passe donnés.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        # On vérifie que les champs is_staff et is_superuser sont bien True pour un superuser
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superuser doit avoir is_staff=True.")

        # On vérifie que les champs is_staff et is_superuser sont bien True pour un superuser
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superuser doit avoir is_superuser=True.")

        # On appelle la méthode create_user pour créer le superuser avec les champs supplémentaires
        return self.create_user(
            email=email,
            password=password,
            **extra_fields
        )
