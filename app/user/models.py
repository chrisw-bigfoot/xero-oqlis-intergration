from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _
import hashlib



class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_("The Email field must be set"))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        # Set avatar color BEFORE saving
        user.avatar_color = user.generate_avatar_color()

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None

    email = models.EmailField(
        _("email address"),
        unique=True,
        error_messages={"unique": _("A user with that email already exists.")},
    )

    # Choose **ONE** of the following two styles (I recommend the first one)

    # Option 1: Recommended (lowercase + string reference → best practice)
    tenant = models.ForeignKey(
        "tenant.Tenant",
        related_name="users",
        on_delete=models.CASCADE,
        null=True, 
        blank=True
    )

    # Option 2: Also correct, but less common in modern projects
    # tenant = models.ForeignKey(Tenant, related_name="users", on_delete=models.CASCADE)

    # ───────────────────────────────────────────────────────────────
    # Avatar fields + logic
    # ───────────────────────────────────────────────────────────────
    avatar_color = models.CharField(
        max_length=7,                    # #rrggbb
        default="#9e9e9e",               # neutral gray fallback
        blank=True,
        help_text="Background color for initials avatar (hex)",
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def get_initials(self):
        """Return uppercase initials (max 2 characters)"""
        parts = []
        if self.first_name:
            parts.append(self.first_name.strip()[0])
        if self.last_name:
            parts.append(self.last_name.strip()[0])

        initials = "".join(parts).upper()
        return initials[:2] or self.email[0].upper()  # fallback to email

    def generate_avatar_color(self):
        """
        Deterministic color — same user = always same color
        """
        # Combine stable fields
        seed = (self.email.lower() + (self.first_name or "") + (self.last_name or "")).strip()
        if not seed:
            seed = self.email.lower()

        h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)

        # ─── You can choose between two styles ───────────────────────

        # Style 1: Nice pastel colors (very pretty)
        # hue = h % 360
        # saturation = 70 + (h % 20)      # 70-90%
        # lightness = 65 + (h % 15)       # 65-80%
        # return f"hsl({hue}, {saturation}%, {lightness}%)"

        # Style 2: Fixed nice color palette (more controlled / corporate look)
        colors = [
            "#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb",
            "#64b5f6", "#4fc3f7", "#4dd0e1", "#4db6ac", "#81c784",
            "#aed581", "#dce775", "#ffd54f", "#ffb74d", "#ff8a65", "#d4e157"
        ]
        return colors[h % len(colors)]