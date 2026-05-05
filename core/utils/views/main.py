# Concrete view classes that provide method handlers
# by composing the mixin classes with the base view.

from rest_framework.generics import (
    GenericAPIView,
    CreateAPIView,
    ListAPIView,
    RetrieveAPIView,
    DestroyAPIView,
    UpdateAPIView,
)
from rest_framework.response import Response

from core.utils.exceptions import bad_request, permission_denied
from core.utils.helper import response_format
from core.utils.messages import APIMessageMixin
from core.utils.views.mixin import (
    PostMethodMixin,
    GetMethodMixin,
    PutMethodMixin,
    PatchMethodMixin,
    DeleteMethodMixin,
)


class BaseGenericAPIView(GenericAPIView):
    """Base class for all generic API views"""

    @classmethod
    def send_response(cls, detail, data=None, status=200):
        context = response_format(detail, data)
        return Response(context, status)

    @classmethod
    def raise_bad_request(cls, detail):
        raise bad_request(detail)

    @classmethod
    def raise_permission_denied(cls, detail):
        raise permission_denied(detail)


class BaseCreateAPIView(
    CreateAPIView,
    APIMessageMixin,
    BaseGenericAPIView,
    PostMethodMixin,
):
    """
    Concrete view for creating a model instance.
    """

    def post(self, request, *args, **kwargs):
        resp = super().post(request, *args, **kwargs)
        detail = self.get_create_success_message()
        context = response_format(detail, resp.data)
        return Response(context, resp.status_code)


class BaseListAPIView(ListAPIView, APIMessageMixin, BaseGenericAPIView, GetMethodMixin):
    """
    Concrete view for listing a queryset.
    """

    def get(self, request, *args, **kwargs):
        resp = super().get(request, *args, **kwargs)
        detail = self.get_list_success_message()
        context = response_format(detail, resp.data)
        return Response(context, resp.status_code)


class BaseRetrieveAPIView(
    RetrieveAPIView, APIMessageMixin, BaseGenericAPIView, GetMethodMixin
):
    """
    Concrete view for retrieving a model instance.
    """

    def get(self, request, *args, **kwargs):
        resp = super().get(request, *args, **kwargs)
        detail = self.get_retrieve_success_message()
        context = response_format(detail, resp.data)
        return Response(context, resp.status_code)


class BaseDestroyAPIView(
    DestroyAPIView, APIMessageMixin, BaseGenericAPIView, DeleteMethodMixin
):
    """
    Concrete view for deleting a model instance.
    """

    def delete(self, request, *args, **kwargs):
        super().delete(request, *args, **kwargs)
        detail = self.get_delete_success_message()
        context = response_format(detail)
        return Response(context, 200)


class BaseUpdateAPIView(
    UpdateAPIView, APIMessageMixin, BaseGenericAPIView, PutMethodMixin, PatchMethodMixin
):
    """
    Concrete view for updating a model instance.
    """

    def put(self, request, *args, **kwargs):
        resp = super().put(request, *args, **kwargs)
        detail = self.get_modify_success_message()
        context = response_format(detail, resp.data)
        return Response(context, resp.status_code)

    def patch(self, request, *args, **kwargs):
        resp = super().patch(request, *args, **kwargs)
        detail = self.get_update_success_message()
        context = response_format(detail, resp.data)
        return Response(context, resp.status_code)


class BaseListCreateAPIView(BaseListAPIView, BaseCreateAPIView):
    """
    Concrete view for listing a queryset or creating a model instance.
    """


class BaseRetrieveUpdateAPIView(BaseRetrieveAPIView, BaseUpdateAPIView):
    """
    Concrete view for retrieving, updating a model instance.
    """


class BaseRetrieveDestroyAPIView(BaseRetrieveAPIView, BaseDestroyAPIView):
    """
    Concrete view for retrieving or deleting a model instance.
    """


class BaseRetrieveUpdateDestroyAPIView(BaseRetrieveUpdateAPIView, BaseDestroyAPIView):
    """
    Concrete view for retrieving, updating or deleting a model instance.
    """
