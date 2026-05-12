import uuid

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.users.utils.constants import Gender
from core.utils.fields import PhoneNumberField
from core.utils.validators import PhoneNumberValidator


class UserManager(BaseUserManager["User"]):
    def get_queryset(self):
        return super().get_queryset().select_related().annotate()

    def get_by_natural_key(self, username):
        """
        By default, Django does a case-sensitive check on usernames. This is wrong.
        Overriding this method fixes it.
        """
        return self.get(**{self.model.USERNAME_FIELD + "__iexact": username})

    @classmethod
    def clean_email(cls, email: str) -> str | None:
        """
        Normalize the email address by stripping whitespace and converting to lowercase.
        """
        if not email:
            return None
        email = email.strip().lower()
        return email

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email, and password.
        """
        if email is not None:
            email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_active(self, *args, **kwargs):
        return super().get(is_active=True, *args, **kwargs)


class AbstractUserProfile(models.Model):
    first_name = models.CharField(
        _("first name"), max_length=100, null=True, blank=True
    )
    last_name = models.CharField(_("last name"), max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)

    gender = models.CharField(
        max_length=1, choices=Gender.CHOICES, null=True, blank=True
    )
    image = models.ImageField(upload_to="users/images/", null=True, blank=True)

    class Meta:
        abstract = True

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = "%s %s" % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name


class User(AbstractBaseUser, AbstractUserProfile, PermissionsMixin):
    phone_number_validator = PhoneNumberValidator()
    id = models.UUIDField(
        _("ID"), default=uuid.uuid7, editable=False, primary_key=True, db_index=True
    )
    email = models.EmailField(
        _("email address"),
        blank=True,
        null=True,
        unique=True,
        db_index=False,
        error_messages={
            "unique": _("A user with that email already exists."),
        },
    )
    phone = PhoneNumberField(
        _("phone number"),
        blank=True,
        null=True,
        unique=True,
        db_index=False,
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"

    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(
                fields=["email"],
                condition=models.Q(email__isnull=False),
                name="%(app_label)s_%(class)s_email_index",
            ),
            models.Index(
                fields=["phone"],
                condition=models.Q(phone__isnull=False),
                name="%(app_label)s_%(class)s_phone_index",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"

    def clean(self):
        setattr(self, self.EMAIL_FIELD, self.__class__.objects.clean_email(self.email))
