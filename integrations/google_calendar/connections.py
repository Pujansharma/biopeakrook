from django.conf import settings
from django.db.models import Exists, OuterRef

from accounts.admins.models import Admin
from accounts.associates.models import Associate
from integrations.models import GoogleCalendarConnection


def connection_is_shared_organizer(connection):
    calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", None)
    return bool(
        calendar_id
        and connection is not None
        and connection.google_email
        and connection.google_email.lower() == calendar_id.lower()
    )


def user_has_active_google_calendar_owner_profile(user):
    if Admin.objects.filter(pk=user.pk, is_active=True).exists():
        return True
    return Associate.objects.filter(pk=user.pk, is_active=True).exists()


def get_google_calendar_connection_for_user(user):
    return GoogleCalendarConnection.objects.filter(user=user).first()


def google_calendar_connection_is_connected(connection):
    return bool(
        connection is not None
        and connection.is_active
        and connection.google_refresh_token
    )


def google_calendar_connection_matches_email(connection, google_email):
    if not google_calendar_connection_is_connected(connection):
        return False
    if not connection.google_email or not google_email:
        return False
    return connection.google_email.lower() == google_email.lower()


def user_can_disconnect_shared_organizer(user):
    if Admin.objects.filter(pk=user.pk, is_active=True).exists():
        return True
    associate = Associate.objects.filter(pk=user.pk, is_active=True).first()
    if associate is None:
        return False
    return associate.center_assignments.filter(
        is_admin=True, is_active=True
    ).exists()


def get_fixed_calendar_organizer():
    calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", None)
    if not calendar_id:
        return None
    admin_exists = Admin.objects.filter(pk=OuterRef("user"), is_active=True)
    associate_exists = Associate.objects.filter(
        pk=OuterRef("user"), is_active=True
    )
    connection = (
        GoogleCalendarConnection.objects.filter(
            google_email__iexact=calendar_id,
            is_active=True,
            user__is_active=True,
        )
        .filter(Exists(admin_exists) | Exists(associate_exists))
        .select_related("user")
        .first()
    )
    if connection is None or not connection.google_refresh_token:
        return None
    return connection
