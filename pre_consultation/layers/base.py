"""LayerHandler dataclass — contract each progression layer implements."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Type

from rest_framework import serializers


@dataclass(frozen=True)
class LayerHandler:
    """Wires serializers and load/persist callables for one layer."""

    layer_id: str
    request_serializer_class: Type[serializers.Serializer] | None = None
    response_serializer_class: Type[serializers.Serializer] | None = None
    put_response_serializer_class: Type[serializers.Serializer] | None = None
    load_payload: Callable[[Any, Any], dict | None] | None = None
    load_put_payload: Callable[[Any, Any], dict | None] | None = None
    persist_payload: Callable[[Any, Any, dict], None] | None = None
    build_put_serializer_context: Callable[[Any, Any], dict] | None = None
    needs_customer_profile: bool = False
    put_includes_data: bool = True

    @property
    def is_implemented(self) -> bool:
        return (
            self.request_serializer_class is not None
            and self.response_serializer_class is not None
            and self.load_payload is not None
            and self.persist_payload is not None
        )
