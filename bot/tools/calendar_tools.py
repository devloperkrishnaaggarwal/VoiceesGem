"""Google Calendar Tools.

Provides voice agent tools for interacting with Google Calendar:
  - list_calendar_events: List upcoming events
  - create_calendar_event: Create a new event
  - delete_calendar_event: Delete an event by title
"""

import os
from datetime import datetime, timedelta, timezone

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from tools.google_auth import get_google_service

# Google Calendar API config
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_calendar_service():
    """Get authenticated Google Calendar service."""
    return get_google_service("calendar", "v3", CALENDAR_SCOPES)


# =============================================================================
# Tool Schemas
# =============================================================================

list_calendar_events_schema = FunctionSchema(
    name="list_calendar_events",
    description=(
        "List upcoming events from the user's Google Calendar. "
        "Call this when the user asks about their schedule, upcoming meetings, "
        "or what's on their calendar."
    ),
    properties={
        "max_results": {
            "type": "integer",
            "description": "Maximum number of events to return. Default is 5.",
        },
        "days_ahead": {
            "type": "integer",
            "description": "Number of days ahead to look for events. Default is 7.",
        },
    },
    required=[],
)

create_calendar_event_schema = FunctionSchema(
    name="create_calendar_event",
    description=(
        "Create a new event on the user's Google Calendar. "
        "Call this when the user wants to schedule a meeting, appointment, or reminder."
    ),
    properties={
        "summary": {
            "type": "string",
            "description": "Title/name of the event.",
        },
        "start_datetime": {
            "type": "string",
            "description": (
                "Start date and time in ISO 8601 format (e.g., '2026-02-15T10:00:00'). "
                "Use today's context if the user says 'today' or 'tomorrow'."
            ),
        },
        "end_datetime": {
            "type": "string",
            "description": (
                "End date and time in ISO 8601 format. "
                "If not specified, defaults to 1 hour after start."
            ),
        },
        "description": {
            "type": "string",
            "description": "Optional description or notes for the event.",
        },
        "attendees": {
            "type": "string",
            "description": "Comma-separated email addresses of attendees.",
        },
    },
    required=["summary", "start_datetime"],
)

delete_calendar_event_schema = FunctionSchema(
    name="delete_calendar_event",
    description=(
        "Delete an event from the user's Google Calendar by its title. "
        "Call this when the user wants to cancel or remove a meeting or event."
    ),
    properties={
        "event_title": {
            "type": "string",
            "description": "The title/name of the event to delete.",
        },
    },
    required=["event_title"],
)


# =============================================================================
# Tool Handlers
# =============================================================================

async def list_calendar_events_handler(params: FunctionCallParams):
    """List upcoming calendar events."""
    max_results = params.arguments.get("max_results", 5)
    days_ahead = params.arguments.get("days_ahead", 7)

    logger.info(f"Listing next {max_results} calendar events (next {days_ahead} days)")

    service = _get_calendar_service()
    if not service:
        await params.result_callback({
            "error": "Google Calendar is not configured. Please set up your Google credentials."
        })
        return

    try:
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        now = datetime.now(timezone.utc).isoformat()
        time_max = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()

        result = await asyncio.to_thread(
            service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute
        )

        events = result.get("items", [])

        if not events:
            await params.result_callback({
                "message": "No upcoming events found.",
                "event_count": 0,
            })
            return

        event_list = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            event_list.append({
                "title": event.get("summary", "No title"),
                "start": start,
                "end": end,
                "location": event.get("location", ""),
                "description": event.get("description", ""),
            })

        await params.result_callback({
            "events": event_list,
            "event_count": len(event_list),
        })

    except Exception as e:
        logger.error(f"Calendar list error: {e}")
        await params.result_callback({"error": f"Failed to fetch calendar events: {str(e)}"})


async def create_calendar_event_handler(params: FunctionCallParams):
    """Create a new calendar event."""
    summary = params.arguments["summary"]
    start_dt = params.arguments["start_datetime"]
    end_dt = params.arguments.get("end_datetime")
    description = params.arguments.get("description", "")
    attendees_str = params.arguments.get("attendees", "")

    logger.info(f"Creating calendar event: {summary} at {start_dt}")

    service = _get_calendar_service()
    if not service:
        await params.result_callback({
            "error": "Google Calendar is not configured. Please set up your Google credentials."
        })
        return

    try:
        # Default end time: 1 hour after start
        if not end_dt:
            start_parsed = datetime.fromisoformat(start_dt)
            end_parsed = start_parsed + timedelta(hours=1)
            end_dt = end_parsed.isoformat()

        event_body = {
            "summary": summary,
            "start": {"dateTime": start_dt, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt, "timeZone": "Asia/Kolkata"},
        }

        if description:
            event_body["description"] = description

        if attendees_str:
            attendees = [{"email": e.strip()} for e in attendees_str.split(",") if e.strip()]
            event_body["attendees"] = attendees

        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        event = await asyncio.to_thread(
            service.events().insert(calendarId=calendar_id, body=event_body).execute
        )

        await params.result_callback({
            "status": "created",
            "event_title": event.get("summary"),
            "event_link": event.get("htmlLink"),
            "start": start_dt,
            "end": end_dt,
        })

    except Exception as e:
        logger.error(f"Calendar create error: {e}")
        await params.result_callback({"error": f"Failed to create event: {str(e)}"})


async def delete_calendar_event_handler(params: FunctionCallParams):
    """Delete a calendar event by title."""
    event_title = params.arguments["event_title"]

    logger.info(f"Deleting calendar event: {event_title}")

    service = _get_calendar_service()
    if not service:
        await params.result_callback({
            "error": "Google Calendar is not configured. Please set up your Google credentials."
        })
        return

    try:
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        now = datetime.now(timezone.utc).isoformat()

        # Search for events matching the title
        result = await asyncio.to_thread(
            service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                q=event_title,
                singleEvents=True,
                maxResults=5,
            ).execute
        )

        events = result.get("items", [])

        if not events:
            await params.result_callback({
                "status": "not_found",
                "message": f"No upcoming event found with title matching '{event_title}'.",
            })
            return

        # Delete the first matching event
        event = events[0]
        await asyncio.to_thread(
            service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute
        )

        await params.result_callback({
            "status": "deleted",
            "deleted_event": event.get("summary", event_title),
        })

    except Exception as e:
        logger.error(f"Calendar delete error: {e}")
        await params.result_callback({"error": f"Failed to delete event: {str(e)}"})


# =============================================================================
# Exports
# =============================================================================

CALENDAR_SCHEMAS = [
    list_calendar_events_schema,
    create_calendar_event_schema,
    delete_calendar_event_schema,
]

CALENDAR_HANDLERS = {
    "list_calendar_events": list_calendar_events_handler,
    "create_calendar_event": create_calendar_event_handler,
    "delete_calendar_event": delete_calendar_event_handler,
}
