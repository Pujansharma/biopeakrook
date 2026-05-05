import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseQuerySet(models.QuerySet):
    def filter_active(self, *args, **kwargs):
        kwargs.update({"is_active": True})
        return super().filter(*args, **kwargs)

    def get_active(self, *args, **kwargs):
        kwargs.update({"is_active": True})
        return super().get(*args, **kwargs)

    def get_active_by_pk(self, pk, *args, **kwargs):
        kwargs.update({"is_active": True})
        return super().get(pk=pk, *args, **kwargs)

    def filter_inactive(self, *args, **kwargs):
        kwargs.update({"is_active": False})
        return super().filter(*args, **kwargs)


class BaseModelManager(models.Manager.from_queryset(BaseQuerySet)):
    @classmethod
    def clean_spaces(cls, text):
        return " ".join(text.split())


class BaseModel(models.Model):
    is_active = models.BooleanField(
        _("active status"),
        default=True,
        help_text=_("Designates whether this is marked as active"),
    )
    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
        help_text=_("Designates when this object was created."),
    )
    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
        help_text=_("Designates when this object was last updated."),
    )

    objects = BaseModelManager()

    class Meta:
        abstract = True


class BaseUUIDModel(BaseModel):
    id = models.UUIDField(
        _("ID"), default=uuid.uuid7, primary_key=True, db_index=True, editable=False
    )

    class Meta:
        abstract = True
