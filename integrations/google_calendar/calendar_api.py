import uuid
from datetime import date, datetime, timedelta

import requests
from django.conf import settings

CALENDAR_ID = "primary"  # the primary calendar of whichever access_token is passed in
EVENTS_URL = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
CHANNELS_STOP_URL = "https://www.googleapis.com/calendar/v3/channels/stop"
REQUEST_TIMEOUT = 10

# Private extended property stamped on Biopeak→Google outbound events so inbound
# sync never re-imports them as foreign busy (loop fence).
BIOPEAK_OUTBOUND_PRIVATE_KEY = "biopeakOutbound"
BIOPEAK_OUTBOUND_PRIVATE_VALUE = "1"

# Shared (not private) extended property stamped on appointment events. Google
# keeps private props on the organizer's copy only, shared props also reach every
# attendee's copy, which is what an associate's personal calendar sync reads
BIOPEAK_IS_APPOINTMENT_SHARED_KEY = "isAppointment"
BIOPEAK_IS_APPOINTMENT_SHARED_VALUE = "1"


def event_is_biopeak_outbound(event: dict) -> bool:
    private = (event.get("extendedProperties") or {}).get("private") or {}
    return private.get(BIOPEAK_OUTBOUND_PRIVATE_KEY) == BIOPEAK_OUTBOUND_PRIVATE_VALUE


def event_is_appointment(event: dict) -> bool:
    shared = (event.get("extendedProperties") or {}).get("shared") or {}
    return (
        shared.get(BIOPEAK_IS_APPOINTMENT_SHARED_KEY)
        == BIOPEAK_IS_APPOINTMENT_SHARED_VALUE
    )


def event_is_organized_by(event: dict, email: str | None) -> bool:
    organizer_email = (event.get("organizer") or {}).get("email")
    return bool(email and organizer_email and organizer_email.lower() == email.lower())


def _date_value(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _exclusive_all_day_end(end_value):
    # Google all-day end.date is exclusive.
    if isinstance(end_value, datetime):
        last_day = end_value.date()
    elif isinstance(end_value, date):
        last_day = end_value
    else:
        return end_value
    return (last_day + timedelta(days=1)).isoformat()


def _event_body(
    title: str,
    start,
    end,
    location: str | None,
    notes: str | None,
    participant_emails: list[str] | None,
    *,
    all_day: bool = False,
    recurrence: list[str] | None = None,
    biopeak_outbound: bool = False,
    is_appointment: bool = False,
):
    if all_day:
        body = {
            "summary": title,
            "start": {"date": _date_value(start)},
            "end": {"date": _exclusive_all_day_end(end)},
            "location": location or "",
            "description": notes or "",
            "attendees": [{"email": email} for email in participant_emails or []],
        }
    else:
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": settings.TIME_ZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": settings.TIME_ZONE},
            "location": location or "",
            "description": notes or "",
            "attendees": [{"email": email} for email in participant_emails or []],
        }
    if recurrence:
        body["recurrence"] = recurrence
    extended_properties = {}
    if biopeak_outbound:
        extended_properties["private"] = {
            BIOPEAK_OUTBOUND_PRIVATE_KEY: BIOPEAK_OUTBOUND_PRIVATE_VALUE,
        }
    if is_appointment:
        extended_properties["shared"] = {
            BIOPEAK_IS_APPOINTMENT_SHARED_KEY: BIOPEAK_IS_APPOINTMENT_SHARED_VALUE,
        }
    if extended_properties:
        body["extendedProperties"] = extended_properties
    return body


def extract_meet_link(google_event: dict):
    if google_event.get("hangoutLink"):
        return google_event["hangoutLink"]
    entry_points = google_event.get("conferenceData", {}).get("entryPoints", [])
    for entry_point in entry_points:
        if entry_point.get("entryPointType") == "video":
            return entry_point["uri"]
    return None


def get_event(access_token: str, event_id: str):
    response = requests.get(
        f"{EVENTS_URL}/{event_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def insert_event(
    access_token: str,
    title: str,
    start,
    end,
    location: str | None = None,
    notes: str | None = None,
    need_meet_link: bool = False,
    participant_emails: list[str] | None = None,
    event_id: str | None = None,
    all_day: bool = False,
    recurrence: list[str] | None = None,
    biopeak_outbound: bool = False,
    is_appointment: bool = False,
):
    body = _event_body(
        title,
        start,
        end,
        location,
        notes,
        participant_emails,
        all_day=all_day,
        recurrence=recurrence,
        biopeak_outbound=biopeak_outbound,
        is_appointment=is_appointment,
    )
    if event_id:
        body["id"] = event_id
    params = {}
    if need_meet_link:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        params["conferenceDataVersion"] = 1
    if participant_emails:
        params["sendUpdates"] = "all"

    response = requests.post(
        EVENTS_URL,
        params=params,
        json=body,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def patch_event(
    access_token: str,
    event_id: str,
    title: str,
    start,
    end,
    location: str | None = None,
    notes: str | None = None,
    add_meet_link: bool = False,
    clear_meet_link: bool = False,
    participant_emails: list[str] | None = None,
    all_day: bool = False,
    recurrence: list[str] | None = None,
    biopeak_outbound: bool = False,
    is_appointment: bool = False,
):
    # add_meet_link=True rotates the Meet link if the event already has one -
    # only pass True the first time a Meet link is added to this event.
    # clear_meet_link=True drops an existing Meet link (e.g. modality changed
    # from virtual to in-person), Google's API removes conference data when
    # conferenceData is explicitly null, not an empty object.
    body = _event_body(
        title,
        start,
        end,
        location,
        notes,
        participant_emails,
        all_day=all_day,
        recurrence=recurrence,
        biopeak_outbound=biopeak_outbound,
        is_appointment=is_appointment,
    )
    params = {}
    if add_meet_link:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        params["conferenceDataVersion"] = 1
    elif clear_meet_link:
        body["conferenceData"] = None
        params["conferenceDataVersion"] = 1
    if participant_emails:
        params["sendUpdates"] = "all"

    response = requests.patch(
        f"{EVENTS_URL}/{event_id}",
        params=params,
        json=body,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def list_events(access_token: str, time_min: datetime, time_max: datetime):
    # singleEvents=False keeps recurring events collapsed to their master item.
    params = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "singleEvents": "false",
        "showDeleted": "false",
        "maxResults": 250,
    }
    page_token = None
    while True:
        if page_token:
            params["pageToken"] = page_token
        response = requests.get(
            EVENTS_URL,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        yield from payload.get("items", [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            return


def delete_event(access_token: str, event_id: str, participant_emails: list[str] | None = None):
    # 404/410 (event already gone) are treated as success, not an error.
    params = {"sendUpdates": "all"} if participant_emails else {}
    response = requests.delete(
        f"{EVENTS_URL}/{event_id}",
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code not in (204, 404, 410):
        response.raise_for_status()


def watch_events(
    access_token: str, channel_id: str, address: str, ttl: timedelta,
):
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": address,
        "params": {"ttl": str(int(ttl.total_seconds()))},
    }
    response = requests.post(
        f"{EVENTS_URL}/watch",
        json=body,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def stop_channel(access_token: str, channel_id: str, resource_id: str):
    # 404 (channel already expired/unknown to Google) is treated as success.
    response = requests.post(
        CHANNELS_STOP_URL,
        json={"id": channel_id, "resourceId": resource_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code not in (204, 404):
        response.raise_for_status()
