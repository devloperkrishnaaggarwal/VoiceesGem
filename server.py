"""Twilio Dial-out Server.

FastAPI server for initiating outbound calls via Twilio.
For dial-in, Twilio connects directly to the bot via WebSocket (no server needed).

Usage:
    # Start the bot with Twilio transport (handles both dial-in and this server)
    uv run bot.py -t twilio

    # In another terminal, trigger a dial-out call:
    curl -X POST http://localhost:7860/dial-out \
        -H "Content-Type: application/json" \
        -d '{"to": "+1234567890", "from": "+0987654321"}'
"""

import os

import aiohttp
from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=True)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")


async def make_outbound_call(
    to_number: str,
    from_number: str,
    websocket_url: str,
    custom_params: dict | None = None,
):
    """Initiate an outbound call via Twilio REST API.

    Args:
        to_number: Phone number to call (E.164 format, e.g. +1234567890)
        from_number: Your Twilio phone number (E.164 format)
        websocket_url: WebSocket URL for the bot (e.g. wss://your-url.ngrok.io/ws)
        custom_params: Optional dict of custom parameters to pass to the bot
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in .env"
        )

    # Build TwiML with optional custom parameters
    params_xml = ""
    if custom_params:
        for key, value in custom_params.items():
            params_xml += f'        <Parameter name="{key}" value="{value}" />\n'

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}">
{params_xml}        </Stream>
    </Connect>
</Response>"""

    # Create the outbound call via Twilio REST API
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"

    async with aiohttp.ClientSession() as session:
        auth = aiohttp.BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        data = {
            "To": to_number,
            "From": from_number,
            "Twiml": twiml,
        }

        async with session.post(url, auth=auth, data=data) as response:
            if response.status == 201:
                result = await response.json()
                logger.info(f"📞 Outbound call initiated: {result['sid']}")
                return result
            else:
                error = await response.text()
                logger.error(f"❌ Failed to create call: {response.status} — {error}")
                raise Exception(f"Twilio API error: {response.status} — {error}")


async def get_caller_info(call_sid: str) -> dict:
    """Look up caller information from Twilio using the Call SID.

    Useful for personalizing greetings on dial-in calls.

    Args:
        call_sid: The Twilio Call SID from the incoming WebSocket connection

    Returns:
        Dict with caller information (from number, to number, etc.)
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return {}

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{TWILIO_ACCOUNT_SID}/Calls/{call_sid}.json"
    )

    async with aiohttp.ClientSession() as session:
        auth = aiohttp.BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        async with session.get(url, auth=auth) as response:
            if response.status == 200:
                data = await response.json()
                caller_info = {
                    "from": data.get("from_formatted", data.get("from", "")),
                    "to": data.get("to_formatted", data.get("to", "")),
                    "direction": data.get("direction", ""),
                    "status": data.get("status", ""),
                }
                logger.info(f"📱 Caller info: {caller_info['from']} → {caller_info['to']}")
                return caller_info
            else:
                logger.warning(f"Could not fetch caller info: {response.status}")
                return {}
