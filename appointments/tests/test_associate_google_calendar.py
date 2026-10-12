from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.centers.models import Center
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from appointments.views import (
    AssociateGoogleCalendarStatusView,
    AssociateGoogleCalendarSyncView,
)
from integrations.models import GoogleCalendarConnection


def create_admin():
    user = User.objects.create_user(email="gcal-admin@example.com")
    UserAccount.objects.create(user=user, account_type=UserType.ADMIN)
    return user


def create_center_and_associate():
    center = Center.objects.create(name="Gcal Center", code="CT-GCAL")
    associate_user = User.objects.create_user(email="gcal-associate@example.com")
    UserAccount.objects.create(user=associate_user, account_type=UserType.ASSOCIATE)
    associate = Associate.objects.create(user=associate_user)
    AssociateCenterAssignment.objects.create(
        associate=associate, center=center, is_active=True
    )
    return center, associate


class AssociateGoogleCalendarStatusViewTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.center, self.associate = create_center_and_associate()

    def get_status(self):
        factory = APIRequestFactory()
        request = factory.get(
            f"/centers/{self.center.pk}/availability/associates/{self.associate.pk}/google-calendar/"
        )
        force_authenticate(request, user=self.admin)
        view = AssociateGoogleCalendarStatusView.as_view()
        return view(request, center_id=self.center.pk, associate_id=self.associate.pk)

    def test_not_connected_when_no_connection_row(self):
        response = self.get_status()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["is_connected"])
        self.assertIsNone(response.data["data"]["last_synced_at"])

    def test_connected_reports_last_synced_at(self):
        synced_at = timezone.now()
        GoogleCalendarConnection.objects.create(
            user=self.associate.user,
            google_email="associate@personal.example.com",
            google_refresh_token="enc:refresh",
            is_active=True,
            last_synced_at=synced_at,
        )
        response = self.get_status()
        self.assertTrue(response.data["data"]["is_connected"])
        self.assertEqual(response.data["data"]["last_synced_at"], synced_at)

    def get_status_as_associate(self, **headers):
        factory = APIRequestFactory()
        request = factory.get(
            f"/centers/{self.center.pk}/availability/associates/{self.associate.pk}/google-calendar/",
            **headers,
        )
        force_authenticate(request, user=self.associate.user)
        view = AssociateGoogleCalendarStatusView.as_view()
        return view(request, center_id=self.center.pk, associate_id=self.associate.pk)

    def test_associate_can_view_status_with_matching_center_header(self):
        response = self.get_status_as_associate(HTTP_X_CENTER_ID=str(self.center.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["is_connected"])

    def test_associate_without_center_header_is_rejected(self):
        response = self.get_status_as_associate()
        self.assertEqual(response.status_code, 400)


class AssociateGoogleCalendarSyncViewTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.center, self.associate = create_center_and_associate()

    def post_sync(self):
        factory = APIRequestFactory()
        request = factory.post(
            f"/centers/{self.center.pk}/availability/associates/{self.associate.pk}/google-calendar/sync/"
        )
        force_authenticate(request, user=self.admin)
        view = AssociateGoogleCalendarSyncView.as_view()
        return view(request, center_id=self.center.pk, associate_id=self.associate.pk)

    def test_sync_rejected_when_not_connected(self):
        response = self.post_sync()
        self.assertEqual(response.status_code, 400)

    @patch("appointments.views.ensure_watch_channel_active_or_log")
    @patch("appointments.views.sync_google_events_to_availability_blocks")
    def test_admin_can_sync_associates_own_connection(self, mock_sync, mock_ensure_watch):
        mock_sync.return_value = {"synced": True, "created": 2}
        GoogleCalendarConnection.objects.create(
            user=self.associate.user,
            google_email="associate@personal.example.com",
            google_refresh_token="enc:refresh",
            google_access_token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        response = self.post_sync()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], {"synced": True, "created": 2})
        mock_ensure_watch.assert_called_once()
        mock_sync.assert_called_once()
        called_user, called_connection = mock_sync.call_args[0]
        self.assertEqual(called_user.pk, self.associate.pk)
        self.assertEqual(called_connection.pk, self.associate.pk)

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch("appointments.views.ensure_watch_channel_active_or_log")
    @patch("appointments.views.sync_google_events_to_availability_blocks")
    def test_sync_rejected_for_shared_organizer_connection(self, mock_sync, mock_ensure_watch):
        GoogleCalendarConnection.objects.create(
            user=self.associate.user,
            google_email="care@biopeak.health",
            google_refresh_token="enc:refresh",
            is_active=True,
        )
        response = self.post_sync()
        self.assertEqual(response.status_code, 400)
        mock_ensure_watch.assert_not_called()
        mock_sync.assert_not_called()

    def post_sync_as_associate(self, **headers):
        GoogleCalendarConnection.objects.create(
            user=self.associate.user,
            google_email="associate@personal.example.com",
            google_refresh_token="enc:refresh",
            is_active=True,
        )
        factory = APIRequestFactory()
        request = factory.post(
            f"/centers/{self.center.pk}/availability/associates/{self.associate.pk}/google-calendar/sync/",
            **headers,
        )
        force_authenticate(request, user=self.associate.user)
        view = AssociateGoogleCalendarSyncView.as_view()
        return view(request, center_id=self.center.pk, associate_id=self.associate.pk)

    @patch("appointments.views.ensure_watch_channel_active_or_log")
    @patch("appointments.views.sync_google_events_to_availability_blocks")
    def test_associate_can_sync_with_matching_center_header(self, mock_sync, mock_ensure_watch):
        mock_sync.return_value = {"synced": True, "created": 1}
        response = self.post_sync_as_associate(HTTP_X_CENTER_ID=str(self.center.pk))
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_called_once()

    @patch("appointments.views.sync_google_events_to_availability_blocks")
    def test_associate_without_center_header_is_rejected(self, mock_sync):
        response = self.post_sync_as_associate()
        self.assertEqual(response.status_code, 400)
        mock_sync.assert_not_called()
