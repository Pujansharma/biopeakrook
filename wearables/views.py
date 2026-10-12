import uuid

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.throttling import ScopedRateThrottle

from accounts.organizations.utils.constants import FeatureTabOptions
from accounts.utils.permissions import IsCustomerUser
from core.utils.views.main import BaseGenericAPIView
from wearables.models import RookMemberIdentity, WearableConnection
from wearables.serializers import (
    DeviceConnectSerializer,
    DeviceDisconnectSerializer,
    DomainQuerySerializer,
    NativeDeviceStatusSerializer,
    TimelineQuerySerializer,
)
from wearables.services.analytics import (
    dashboard_payload,
    domain_payload,
    timeline_payload,
)
from wearables.services.client import RookConfigurationError, RookServiceError
from wearables.services.connections import (
    disconnect_connection,
    refresh_authorizing_connections,
    serialize_connection,
    start_connection,
    update_native_connection,
)
from wearables.services.identity import resolve_customer_profile
from wearables.utils.constants import HEALTH_DOMAIN_ORDER, ConnectionMethod


class WearablesAPIView(BaseGenericAPIView):
    permission_classes = (IsCustomerUser,)

    def ensure_wearables_enabled(self) -> None:
        if not getattr(settings, "WEARABLES_ENABLED", True):
            raise NotFound("Wearable integration is not enabled.")

    def ensure_profile_feature_enabled(self, customer_profile) -> None:
        if not getattr(settings, "WEARABLES_REQUIRE_PROFILE_FEATURE", False):
            return
        feature = getattr(customer_profile, "feature", None)
        if feature is None or FeatureTabOptions.WEARABLES not in feature.enabled_tabs:
            raise NotFound("Wearable integration is not enabled for this profile.")

    def get_customer_profile(self):
        self.ensure_wearables_enabled()
        customer_profile = resolve_customer_profile(self.request)
        self.ensure_profile_feature_enabled(customer_profile)
        return customer_profile

    def correlation_id(self) -> str:
        return self.request.headers.get("X-Correlation-ID") or str(uuid.uuid4())


class DeviceConnectView(WearablesAPIView):
    serializer_class = DeviceConnectSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "wearable_connect"

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = start_connection(
                request=request,
                customer_profile=customer_profile,
                validated_data=serializer.validated_data,
                correlation_id=self.correlation_id(),
            )
        except RookConfigurationError as error:
            return self.send_response(str(error), status=503)
        except RookServiceError as error:
            return self.send_response(error.detail, status=error.status_code)
        connection = result["connection"]
        data = {
            "connection": serialize_connection(connection),
            "authorizationMethod": result["authorization_method"],
            "authorizationUrl": result["authorization_url"],
            "rookUserId": connection.identity.rook_user_id,
        }
        return self.send_response("Wearable connection initiated.", data, status=201)


class DeviceListView(WearablesAPIView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "wearable_status"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        refresh_requested = request.query_params.get("refresh", "").lower() in {
            "1",
            "true",
        }
        refresh_error = None
        if refresh_requested:
            try:
                refresh_authorizing_connections(customer_profile)
            except (RookConfigurationError, RookServiceError) as error:
                refresh_error = str(error)
        connections = list(
            WearableConnection.objects.select_related("identity")
            .filter(customer_profile=customer_profile)
            .order_by("data_source")
        )
        identity = RookMemberIdentity.objects.filter(
            customer_profile=customer_profile
        ).first()
        data = {
            "connections": [
                serialize_connection(connection) for connection in connections
            ],
            "connected": any(
                connection.authorization_status == "authorized"
                for connection in connections
            ),
            "rookUserId": identity.rook_user_id if identity else None,
            "refreshError": refresh_error,
        }
        return self.send_response("Connected devices retrieved.", data)


class DeviceDisconnectView(WearablesAPIView):
    serializer_class = DeviceDisconnectSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "wearable_connect"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def post(self, request, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connection, revoke_pending = disconnect_connection(
            customer_profile=customer_profile,
            data_source=serializer.validated_data["data_source"],
            actor_user=request.user,
            correlation_id=self.correlation_id(),
        )
        data = {
            "provider": serializer.validated_data["data_source"],
            "disconnected": True,
            "historyRetained": True,
            "upstreamRevokePending": revoke_pending,
            "connection": serialize_connection(connection) if connection else None,
        }
        return self.send_response("Wearable disconnected. History was retained.", data)


class DeviceSDKConfigView(WearablesAPIView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "wearable_status"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        native_connection = (
            WearableConnection.objects.select_related("identity")
            .filter(
                customer_profile=customer_profile,
                connection_method=ConnectionMethod.SDK,
            )
            .first()
        )
        if native_connection is None:
            self.raise_bad_request(
                "Start a native wearable connection before requesting SDK configuration."
            )
        identity = native_connection.identity
        client_uuid = getattr(settings, "ROOK_SDK_CLIENT_UUID", "")
        sdk_secret = getattr(settings, "ROOK_SDK_SECRET", "")
        if not client_uuid or not sdk_secret:
            return self.send_response("ROOK mobile SDK is not configured.", status=503)
        data = {
            "clientUuid": client_uuid,
            "secret": sdk_secret,
            "environment": getattr(settings, "ROOK_ENVIRONMENT", "sandbox"),
            "rookUserId": identity.rook_user_id,
        }
        return self.send_response("ROOK mobile SDK configuration retrieved.", data)


class NativeDeviceStatusView(WearablesAPIView):
    serializer_class = NativeDeviceStatusSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "wearable_status"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def post(self, request, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            connection = update_native_connection(
                customer_profile=customer_profile,
                actor_user=request.user,
                validated_data=serializer.validated_data,
                correlation_id=self.correlation_id(),
            )
        except ValueError as error:
            self.raise_bad_request(str(error))
        return self.send_response(
            "Native wearable status updated.",
            {"connection": serialize_connection(connection)},
        )


class HealthDashboardView(WearablesAPIView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "health_read"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        return self.send_response(
            "Health dashboard retrieved.",
            dashboard_payload(customer_profile),
        )


class HealthDomainView(WearablesAPIView):
    serializer_class = DomainQuerySerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "health_read"

    @extend_schema(
        parameters=[DomainQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, domain, *args, **kwargs):
        customer_profile = self.get_customer_profile()
        if domain not in HEALTH_DOMAIN_ORDER:
            raise NotFound("Health domain not found.")
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return self.send_response(
            "Health domain retrieved.",
            domain_payload(
                customer_profile=customer_profile,
                domain=domain,
                days=serializer.validated_data["days"],
            ),
        )


class HealthTimelineView(WearablesAPIView):
    serializer_class = TimelineQuerySerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "health_read"

    @extend_schema(
        parameters=[TimelineQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, *args, **kwargs):
        if not getattr(settings, "TIMELINE_ENABLED", True):
            raise NotFound("Health timeline is not enabled.")
        customer_profile = self.get_customer_profile()
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = timeline_payload(
            customer_profile=customer_profile,
            start_date=serializer.validated_data.get("start"),
            end_date=serializer.validated_data.get("end"),
            domain=serializer.validated_data.get("domain"),
            offset=serializer.validated_data["offset"],
            limit=serializer.validated_data["limit"],
        )
        return self.send_response("Health timeline retrieved.", data)

