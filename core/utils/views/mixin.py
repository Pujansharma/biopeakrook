from typing import Protocol, Any

from rest_framework.response import Response

from core.utils.request import Request


# Protocol classes for view method typing
class GetMethodMixin(Protocol):
    """Protocol for views that support GET method"""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response: ...


class PostMethodMixin(Protocol):
    """Protocol for views that support POST method"""

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response: ...


class PutMethodMixin(Protocol):
    """Protocol for views that support PUT method"""

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response: ...


class PatchMethodMixin(Protocol):
    """Protocol for views that support PATCH method"""

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response: ...


class DeleteMethodMixin(Protocol):
    """Protocol for views that support DELETE method"""

    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response: ...
