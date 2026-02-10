"""Gmail Tools.

Provides voice agent tools for interacting with Gmail:
  - list_emails: List recent emails from inbox
  - read_email: Read a specific email by ID
  - send_email: Send an email
"""

import base64
import os
from email.mime.text import MIMEText

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from tools.google_auth import get_google_service

# Gmail API config — prefer OAuth2 for personal accounts
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _get_gmail_service():
    """Get authenticated Gmail service.

    Prefers OAuth2 for Gmail since service accounts require
    Google Workspace domain-wide delegation for Gmail access.
    """
    subject = os.getenv("GOOGLE_GMAIL_USER")
    return get_google_service(
        "gmail", "v1", GMAIL_SCOPES,
        subject=subject,
        prefer_oauth2=True,
    )


# =============================================================================
# Tool Schemas
# =============================================================================

list_emails_schema = FunctionSchema(
    name="list_emails",
    description=(
        "List recent emails from the user's Gmail inbox. "
        "Call this when the user asks about their emails, messages, or inbox."
    ),
    properties={
        "max_results": {
            "type": "integer",
            "description": "Maximum number of emails to return. Default is 5.",
        },
        "query": {
            "type": "string",
            "description": (
                "Optional Gmail search query to filter emails (same syntax as Gmail search). "
                "Examples: 'is:unread', 'from:john@example.com', 'subject:meeting', 'newer_than:1d'."
            ),
        },
    },
    required=[],
)

read_email_schema = FunctionSchema(
    name="read_email",
    description=(
        "Read the full content of a specific email by its ID. "
        "Call this after list_emails when the user wants to hear the details of a specific email."
    ),
    properties={
        "email_id": {
            "type": "string",
            "description": "The email ID returned from list_emails.",
        },
    },
    required=["email_id"],
)

send_email_schema = FunctionSchema(
    name="send_email",
    description=(
        "Send an email via Gmail. "
        "Call this when the user wants to send, compose, or reply to an email."
    ),
    properties={
        "to": {
            "type": "string",
            "description": "Recipient email address.",
        },
        "subject": {
            "type": "string",
            "description": "Email subject line.",
        },
        "body": {
            "type": "string",
            "description": "Email body text.",
        },
    },
    required=["to", "subject", "body"],
)


# =============================================================================
# Tool Handlers
# =============================================================================

async def list_emails_handler(params: FunctionCallParams):
    """List recent emails from Gmail."""
    max_results = params.arguments.get("max_results", 5)
    query = params.arguments.get("query", "")

    logger.info(f"Listing emails (max={max_results}, query='{query}')")

    service = _get_gmail_service()
    if not service:
        await params.result_callback({
            "error": (
                "Gmail is not configured. Please set up OAuth2 credentials "
                "(credentials.json) or a service account with domain-wide delegation."
            )
        })
        return

    try:
        result = await asyncio.to_thread(
            service.users().messages().list(
                userId="me",
                maxResults=max_results,
                q=query or "in:inbox",
            ).execute
        )

        messages = result.get("messages", [])

        if not messages:
            await params.result_callback({
                "message": "No emails found matching your criteria.",
                "email_count": 0,
            })
            return

        email_list = []
        for msg in messages:
            # Get message metadata (not full body for listing)
            msg_data = await asyncio.to_thread(
                service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute
            )

            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

            email_list.append({
                "id": msg["id"],
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "No subject"),
                "date": headers.get("Date", ""),
                "snippet": msg_data.get("snippet", ""),
                "is_unread": "UNREAD" in msg_data.get("labelIds", []),
            })

        await params.result_callback({
            "emails": email_list,
            "email_count": len(email_list),
        })

    except Exception as e:
        logger.error(f"Gmail list error: {e}")
        await params.result_callback({"error": f"Failed to list emails: {str(e)}"})


async def read_email_handler(params: FunctionCallParams):
    """Read a specific email by ID."""
    email_id = params.arguments["email_id"]

    logger.info(f"Reading email: {email_id}")

    service = _get_gmail_service()
    if not service:
        await params.result_callback({
            "error": "Gmail is not configured. Please set up your Google credentials."
        })
        return

    try:
        msg = await asyncio.to_thread(
            service.users().messages().get(
                userId="me",
                id=email_id,
                format="full",
            ).execute
        )

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Extract body text
        body = _extract_email_body(msg.get("payload", {}))

        await params.result_callback({
            "id": email_id,
            "from": headers.get("From", "Unknown"),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", "No subject"),
            "date": headers.get("Date", ""),
            "body": body[:2000],  # Limit body length for voice readback
        })

    except Exception as e:
        logger.error(f"Gmail read error: {e}")
        await params.result_callback({"error": f"Failed to read email: {str(e)}"})


async def send_email_handler(params: FunctionCallParams):
    """Send an email via Gmail."""
    to = params.arguments["to"]
    subject = params.arguments["subject"]
    body = params.arguments["body"]

    logger.info(f"Sending email to {to}: {subject}")

    service = _get_gmail_service()
    if not service:
        await params.result_callback({
            "error": "Gmail is not configured. Please set up your Google credentials."
        })
        return

    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_body = {"raw": raw}

        sent = await asyncio.to_thread(
            service.users().messages().send(
                userId="me",
                body=send_body,
            ).execute
        )

        await params.result_callback({
            "status": "sent",
            "message_id": sent.get("id"),
            "to": to,
            "subject": subject,
        })

    except Exception as e:
        logger.error(f"Gmail send error: {e}")
        await params.result_callback({"error": f"Failed to send email: {str(e)}"})


# =============================================================================
# Helpers
# =============================================================================

def _extract_email_body(payload: dict) -> str:
    """Extract plain text body from email payload (handles multipart)."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Check parts for multipart messages
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Fallback: try first part recursively
    for part in parts:
        result = _extract_email_body(part)
        if result:
            return result

    return "(Could not extract email body)"


# =============================================================================
# Exports
# =============================================================================

MAIL_SCHEMAS = [
    list_emails_schema,
    read_email_schema,
    send_email_schema,
]

MAIL_HANDLERS = {
    "list_emails": list_emails_handler,
    "read_email": read_email_handler,
    "send_email": send_email_handler,
}
