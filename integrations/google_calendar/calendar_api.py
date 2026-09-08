import uuid
from datetime import datetime

import requests

CALENDAR_ID = "primary"  # every staff member's own Google Calendar
EVENTS_URL = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
REQUEST_TIMEOUT = 10


def _event_body(
    title: str, start: datetime, end: datetime, location: str | None, notes: str | None,
    participant_emails: list[str] | None,
):
    return {
        "summary": title,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "location": location or "",
        "description": notes or "",
        "attendees": [{"email": email} for email in participant_emails or []],
    }


def extract_meet_link(google_event: dict):
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
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def patch_event(
    access_token: str, event_id: str, title: str, start: datetime, end: datetime,
    location: str | None = None, notes: str | None = None, add_meet_link: bool = False,
    participant_emails: list[str] | None = None,
):
    # add_meet_link=True rotates the Meet link if the event already has one -
    # only pass True the first time a Meet link is added to this event.
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
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def list_events(access_token: str, time_min: datetime, time_max: datetime):
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
            timeout=REQUEST_TIMEOUT,
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
