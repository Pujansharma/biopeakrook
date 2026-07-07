"""Layer response helpers — directive JSON key aliasing and payload serialization."""

from typing import Type

from rest_framework import serializers


class DirectiveJsonKeyCharField(serializers.CharField):
    """Expose directive JSON keys like icon-class under valid Python field names."""

    def __init__(self, json_key: str, **kwargs):
        self.json_key = json_key
        super().__init__(**kwargs)

    def bind(self, field_name, parent):
        super().bind(self.json_key, parent)

    def get_value(self, dictionary):
        return dictionary.get(self.json_key, serializers.empty)

    def get_attribute(self, instance):
        if isinstance(instance, dict):
            return instance.get(self.json_key)
        return super().get_attribute(instance)


def serialize_layer_payload(
    serializer_class: Type[serializers.Serializer],
    payload: dict | None,
) -> dict:
    serializer = serializer_class(data=payload or {})
    serializer.is_valid(raise_exception=True)
    return serializer.data
