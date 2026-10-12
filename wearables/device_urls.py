from django.urls import path

from wearables.views import (
    DeviceConnectView,
    DeviceDisconnectView,
    DeviceListView,
    DeviceSDKConfigView,
    NativeDeviceStatusView,
)

urlpatterns = [
    path("", DeviceListView.as_view(), name="wearable-device-list"),
    path("connect/", DeviceConnectView.as_view(), name="wearable-device-connect"),
    path(
        "disconnect/",
        DeviceDisconnectView.as_view(),
        name="wearable-device-disconnect",
    ),
    path("sdk-config/", DeviceSDKConfigView.as_view(), name="wearable-sdk-config"),
    path(
        "native-status/",
        NativeDeviceStatusView.as_view(),
        name="wearable-native-status",
    ),
]

