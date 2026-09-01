import uuid
from datetime import datetime

import requests

CALENDAR_ID = "primary"  # every staff member's own Google Calendar
EVENTS_URL = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"


def _event_body(
    title: str, start: datetime, end: datetime, location: str | None, notes: str | None,
    participant_emails: list[str] | None,
):
    """
    Builds the JSON body Google expects for a create/update call.

    Input:
        title="Checkup", start=2026-09-01 15:00, end=2026-09-01 15:30,
        location="Zoom", notes="First visit", participant_emails=["priya@example.com"]

    Output:
        {
            "summary": "Checkup",
            "start": {"dateTime": "2026-09-01T15:00:00+05:30"},
            "end": {"dateTime": "2026-09-01T15:30:00+05:30"},
            "location": "Zoom",
            "description": "First visit",
            "attendees": [{"email": "priya@example.com"}],
        }
    """
    return {
        "summary": title,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "location": location or "",
        "description": notes or "",
        "attendees": [{"email": email} for email in participant_emails or []],
    }


def extract_meet_link(google_event: dict):
    """
    Pulls the Google Meet video link out of a Google event, if one exists.

    Input:
        {
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
                ]
            }
        }

    Output:
        "https://meet.google.com/abc-defg-hij"
        (or None if the event has no video entry point)
    """
    entry_points = google_event.get("conferenceData", {}).get("entryPoints", [])
    for entry_point in entry_points:
        if entry_point.get("entryPointType") == "video":
            return entry_point["uri"]
    return None


def insert_event(
    access_token: str, title: str, start: datetime, end: datetime,
    location: str | None = None, notes: str | None = None, need_meet_link: bool = False,
    participant_emails: list[str] | None = None,
):
    """
    Creates a new event on the staff member's Google Calendar.
    POST https://www.googleapis.com/calendar/v3/calendars/primary/events

    Input:
        access_token="ya29.xyz...", title="Checkup",
        start=2026-09-01 15:00, end=2026-09-01 15:30,
        location="Zoom", notes="First visit", need_meet_link=True,
        participant_emails=["priya@example.com"]

    Request query params: {"conferenceDataVersion": 1, "sendUpdates": "all"}
    Request JSON body:
        {
            "summary": "Checkup",
            "start": {"dateTime": "2026-09-01T15:00:00+05:30"},
            "end": {"dateTime": "2026-09-01T15:30:00+05:30"},
            "location": "Zoom",
            "description": "First visit",
            "attendees": [{"email": "priya@example.com"}],
            "conferenceData": {
                "createRequest": {
                    "requestId": "8f14e45f-...",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

    Output (Google's response, returned as-is):
        {
            "id": "abc123xyz",
            "summary": "Checkup",
            "start": {"dateTime": "2026-09-01T15:00:00+05:30"},
            "end": {"dateTime": "2026-09-01T15:30:00+05:30"},
            "attendees": [{"email": "priya@example.com", "responseStatus": "needsAction"}],
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
                ]
            },
        }
    """
    body = _event_body(title, start, end, location, notes, participant_emails)
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
    )
    response.raise_for_status()
    return response.json()


def patch_event(
    access_token: str, event_id: str, title: str, start: datetime, end: datetime,
    location: str | None = None, notes: str | None = None, add_meet_link: bool = False,
    participant_emails: list[str] | None = None,
):
    """
    Updates an existing event on the staff member's Google Calendar.
    PATCH https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}

    `add_meet_link=True` rotates the Meet link if the event already has one -
    only pass True the first time a Meet link is added.

    Input:
        access_token="ya29.xyz...", event_id="abc123xyz",
        title="Checkup (rescheduled)", start=2026-09-01 17:00, end=2026-09-01 17:30,
        location="Zoom", notes="Moved to 5pm", add_meet_link=False,
        participant_emails=["priya@example.com"]

    Request query params: {"sendUpdates": "all"}
    Request JSON body:
        {
            "summary": "Checkup (rescheduled)",
            "start": {"dateTime": "2026-09-01T17:00:00+05:30"},
            "end": {"dateTime": "2026-09-01T17:30:00+05:30"},
            "location": "Zoom",
            "description": "Moved to 5pm",
            "attendees": [{"email": "priya@example.com"}],
        }

    Output (Google's response, returned as-is):
        {
            "id": "abc123xyz",
            "summary": "Checkup (rescheduled)",
            "start": {"dateTime": "2026-09-01T17:00:00+05:30"},
            "end": {"dateTime": "2026-09-01T17:30:00+05:30"},
            "attendees": [{"email": "priya@example.com", "responseStatus": "needsAction"}],
        }
    """
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
    if participant_emails:
        params["sendUpdates"] = "all"

    response = requests.patch(
        f"{EVENTS_URL}/{event_id}",
        params=params,
        json=body,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def list_events(access_token: str, time_min: datetime, time_max: datetime):
    """
    Fetches full event details from the staff member's Google Calendar in a time window
    (title, notes, participants, Meet link, etc.), paging through all of it.
    GET https://www.googleapis.com/calendar/v3/calendars/primary/events

    Input:
        access_token="ya29.xyz...", time_min=2026-09-01 09:00, time_max=2026-09-01 18:00

    Request query params (repeated per page, `pageToken` added from the
    previous page's `nextPageToken` once one exists):
        {
            "timeMin": "2026-09-01T09:00:00+05:30",
            "timeMax": "2026-09-01T18:00:00+05:30",
            "singleEvents": True,
            "orderBy": "startTime",
        }

    Output (normalized from Google's raw "items" list across every page):
        [
            {
                "id": "abc123xyz",
                "title": "Checkup",
                "notes": "First visit",
                "location": "Zoom",
                "start": "2026-09-01T15:00:00+05:30",
                "end": "2026-09-01T15:30:00+05:30",
                "participants": ["priya@example.com"],
                "meet_link": "https://meet.google.com/abc-defg-hij",
            }
        ]
    """
    events = []
    params = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
    }
    while True:
        response = requests.get(
            EVENTS_URL,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        payload = response.json()
        events.extend(
            {
                "id": event["id"],
                "title": event.get("summary"),
                "notes": event.get("description"),
                "location": event.get("location"),
                "start": event["start"]["dateTime"],
                "end": event["end"]["dateTime"],
                "participants": [attendee["email"] for attendee in event.get("attendees", [])],
                "meet_link": extract_meet_link(event),
            }
            for event in payload.get("items", [])
            if "dateTime" in event.get("start", {})
        )
        next_page_token = payload.get("nextPageToken")
        if not next_page_token:
            return events
        params["pageToken"] = next_page_token


def delete_event(access_token: str, event_id: str, participant_emails: list[str] | None = None):
    """
    Cancels/removes an event from the staff member's Google Calendar.
    DELETE https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}

    Input:
        access_token="ya29.xyz...", event_id="abc123xyz",
        participant_emails=["priya@example.com"]

    Request query params: {"sendUpdates": "all"}
    Request body: none

    Output:
        None on success. 404/410 (event already gone) are treated as success too;
        any other failure status raises `requests.HTTPError`.
    """
    params = {"sendUpdates": "all"} if participant_emails else {}
    response = requests.delete(
        f"{EVENTS_URL}/{event_id}",
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code not in (204, 404, 410):
        response.raise_for_status()
