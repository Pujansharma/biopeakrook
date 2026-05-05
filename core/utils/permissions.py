from rest_framework.permissions import BasePermission, SAFE_METHODS

WRITE_METHODS = ("HEAD", "OPTIONS", "POST")
MODIFY_METHODS = ("HEAD", "OPTIONS", "PATCH", "PUT", "DELETE")

READ_WRITE_METHODS = ("GET", "HEAD", "OPTIONS", "POST")
READ_UPDATE_METHODS = ("GET", "HEAD", "OPTIONS", "PATCH", "PUT")
READ_WRITE_DELETE_METHODS = ("GET", "HEAD", "OPTIONS", "POST", "DELETE")
READ_WRITE_UPDATE_DELETE_METHODS = ("GET", "HEAD", "OPTIONS", "PATCH", "PUT", "DELETE")


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class AnonWriteOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in WRITE_METHODS


class ReadUpdateOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in READ_UPDATE_METHODS
