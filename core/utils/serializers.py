from typing import TypeVar

from django.db.models import Model
from rest_framework import serializers

_MT = TypeVar("_MT", bound=Model)


class BaseModelSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context.update(
            {
                **self.context,
                "omit_fields": self.context.get("omit_fields", []),
                "omit_nested_fields": self.context.get("omit_nested_fields", {}),
            }
        )

    def get_fields(self):
        fields = super().get_fields()
        omit_fields = self.context.get("omit_fields", [])
        for field in omit_fields:
            fields.pop(field, None)
        return fields

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        for field in self.get_fields():
            if has_display := getattr(instance, f"get_{field}_display", None):
                rep[field] = has_display()
        return rep


class BaseSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context.update(
            {
                **self.context,
                "omit_fields": self.context.get("omit_fields", []),
                "omit_nested_fields": self.context.get("omit_nested_fields", {}),
            }
        )

    def get_fields(self):
        fields = super().get_fields()
        omit_fields = self.context.get("omit_fields", [])
        for field in omit_fields:
            fields.pop(field, None)
        return fields

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        for field in self.get_fields():
            if has_display := getattr(instance, f"get_{field}_display", None):
                rep[field] = has_display()
        return rep
