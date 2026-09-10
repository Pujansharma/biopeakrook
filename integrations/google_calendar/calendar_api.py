import uuid
from datetime import datetime

import requests
from django.conf import settings

CALENDAR_ID = "primary"  # the primary calendar of whichever access_token is passed in
EVENTS_URL = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
REQUEST_TIMEOUT = 10


def _event_body(
    title: str, start: datetime, end: datetime, location: str | None, notes: str | None,
    participant_emails: list[str] | None,
):
    return {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": settings.TIME_ZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.TIME_ZONE},
        "location": location or "",
        "description": notes or "",
        "attendees": [{"email": email} for email in participant_emails or []],
    }


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
    access_token: str, title: str, start: datetime, end: datetime,
    location: str | None = None, notes: str | None = None, need_meet_link: bool = False,
    participant_emails: list[str] | None = None, event_id: str | None = None,
):
    body = _event_body(title, start, end, location, notes, participant_emails)
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
    access_token: str, event_id: str, title: str, start: datetime, end: datetime,
    location: str | None = None, notes: str | None = None, add_meet_link: bool = False,
    clear_meet_link: bool = False, participant_emails: list[str] | None = None,
):
    # add_meet_link=True rotates the Meet link if the event already has one -
    # only pass True the first time a Meet link is added to this event.
    # clear_meet_link=True drops an existing Meet link (e.g. modality changed
    # from virtual to in-person), Google's API removes conference data when
    # conferenceData is explicitly null, not an empty object.
    body = _event_body(title, start, end, location, notes, participant_emails)
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
