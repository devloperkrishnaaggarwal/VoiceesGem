"""Google Sheets Tools.

Provides voice agent tools for interacting with Google Sheets:
  - read_sheet: Read data from a spreadsheet range
  - write_sheet: Write/append data to a spreadsheet
  - list_sheet_tabs: List all sheet tabs in a spreadsheet
"""

import os

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from tools.google_auth import get_google_service

# Google Sheets API config
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_sheets_service():
    """Get authenticated Google Sheets service."""
    return get_google_service("sheets", "v4", SHEETS_SCOPES)


# =============================================================================
# Tool Schemas
# =============================================================================

read_sheet_schema = FunctionSchema(
    name="read_sheet",
    description=(
        "Read data from a Google Spreadsheet. "
        "Call this when the user asks to read, check, or look up data from a spreadsheet."
    ),
    properties={
        "range": {
            "type": "string",
            "description": (
                "The A1 notation range to read, e.g. 'Sheet1!A1:D10' or 'A1:C5'. "
                "If the user doesn't specify, use 'Sheet1!A1:Z50' to get the first 50 rows."
            ),
        },
        "spreadsheet_id": {
            "type": "string",
            "description": (
                "The spreadsheet ID. Only provide if the user specifies a different spreadsheet. "
                "Otherwise, the default spreadsheet from configuration will be used."
            ),
        },
    },
    required=["range"],
)

write_sheet_schema = FunctionSchema(
    name="write_sheet",
    description=(
        "Write or append data to a Google Spreadsheet. "
        "Call this when the user wants to add, update, or write data to a spreadsheet."
    ),
    properties={
        "range": {
            "type": "string",
            "description": (
                "The A1 notation range to write to, e.g. 'Sheet1!A1' for starting cell. "
                "For appending, use the sheet name like 'Sheet1'."
            ),
        },
        "values": {
            "type": "string",
            "description": (
                "The data to write, as a JSON string representing a 2D array. "
                "Each inner array is a row. Example: '[[\"Name\", \"Age\"], [\"Alice\", 30]]'"
            ),
        },
        "append": {
            "type": "boolean",
            "description": "If true, append data after existing content instead of overwriting.",
        },
        "spreadsheet_id": {
            "type": "string",
            "description": "Optional. The spreadsheet ID if not using the default.",
        },
    },
    required=["range", "values"],
)

list_sheet_tabs_schema = FunctionSchema(
    name="list_sheet_tabs",
    description=(
        "List all sheet tabs in a Google Spreadsheet. "
        "Call this when the user asks what sheets or tabs are available."
    ),
    properties={
        "spreadsheet_id": {
            "type": "string",
            "description": "Optional. The spreadsheet ID if not using the default.",
        },
    },
    required=[],
)


# =============================================================================
# Tool Handlers
# =============================================================================

async def read_sheet_handler(params: FunctionCallParams):
    """Read data from a Google Sheet."""
    range_str = params.arguments["range"]
    sheet_id = params.arguments.get("spreadsheet_id") or os.getenv("GOOGLE_SHEET_ID", "")

    if not sheet_id:
        await params.result_callback({
            "error": "No spreadsheet ID configured. Please set GOOGLE_SHEET_ID in your .env file."
        })
        return

    logger.info(f"Reading sheet {sheet_id} range: {range_str}")

    service = _get_sheets_service()
    if not service:
        await params.result_callback({
            "error": "Google Sheets is not configured. Please set up your Google credentials."
        })
        return

    try:
        result = await asyncio.to_thread(
            service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_str,
            ).execute
        )

        values = result.get("values", [])

        if not values:
            await params.result_callback({
                "message": "No data found in the specified range.",
                "range": range_str,
                "row_count": 0,
            })
            return

        # Format data: first row as headers if it looks like headers
        await params.result_callback({
            "data": values,
            "range": range_str,
            "row_count": len(values),
            "column_count": max(len(row) for row in values) if values else 0,
        })

    except Exception as e:
        logger.error(f"Sheets read error: {e}")
        await params.result_callback({"error": f"Failed to read spreadsheet: {str(e)}"})


async def write_sheet_handler(params: FunctionCallParams):
    """Write/append data to a Google Sheet."""
    import json

    range_str = params.arguments["range"]
    values_str = params.arguments["values"]
    append = params.arguments.get("append", False)
    sheet_id = params.arguments.get("spreadsheet_id") or os.getenv("GOOGLE_SHEET_ID", "")

    if not sheet_id:
        await params.result_callback({
            "error": "No spreadsheet ID configured. Please set GOOGLE_SHEET_ID in your .env file."
        })
        return

    logger.info(f"Writing to sheet {sheet_id} range: {range_str} (append={append})")

    service = _get_sheets_service()
    if not service:
        await params.result_callback({
            "error": "Google Sheets is not configured. Please set up your Google credentials."
        })
        return

    try:
        # Parse the values JSON string
        try:
            values = json.loads(values_str)
        except (json.JSONDecodeError, TypeError):
            # If it's already a list, use it directly
            if isinstance(values_str, list):
                values = values_str
            else:
                await params.result_callback({
                    "error": "Invalid values format. Expected a JSON array of arrays."
                })
                return

        body = {"values": values}

        if append:
            result = await asyncio.to_thread(
                service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range=range_str,
                    valueInputOption="USER_ENTERED",
                    body=body,
                ).execute
            )
            updated = result.get("updates", {})
            await params.result_callback({
                "status": "appended",
                "updated_range": updated.get("updatedRange", range_str),
                "rows_added": updated.get("updatedRows", len(values)),
            })
        else:
            result = await asyncio.to_thread(
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=range_str,
                    valueInputOption="USER_ENTERED",
                    body=body,
                ).execute
            )
            await params.result_callback({
                "status": "updated",
                "updated_range": result.get("updatedRange", range_str),
                "rows_updated": result.get("updatedRows", len(values)),
            })

    except Exception as e:
        logger.error(f"Sheets write error: {e}")
        await params.result_callback({"error": f"Failed to write to spreadsheet: {str(e)}"})


async def list_sheet_tabs_handler(params: FunctionCallParams):
    """List all sheet tabs in a spreadsheet."""
    sheet_id = params.arguments.get("spreadsheet_id") or os.getenv("GOOGLE_SHEET_ID", "")

    if not sheet_id:
        await params.result_callback({
            "error": "No spreadsheet ID configured. Please set GOOGLE_SHEET_ID in your .env file."
        })
        return

    logger.info(f"Listing tabs for sheet {sheet_id}")

    service = _get_sheets_service()
    if not service:
        await params.result_callback({
            "error": "Google Sheets is not configured. Please set up your Google credentials."
        })
        return

    try:
        spreadsheet = await asyncio.to_thread(
            service.spreadsheets().get(spreadsheetId=sheet_id).execute
        )

        sheets = spreadsheet.get("sheets", [])
        tabs = []
        for sheet in sheets:
            props = sheet.get("properties", {})
            tabs.append({
                "title": props.get("title", "Untitled"),
                "index": props.get("index", 0),
                "row_count": props.get("gridProperties", {}).get("rowCount", 0),
                "column_count": props.get("gridProperties", {}).get("columnCount", 0),
            })

        await params.result_callback({
            "spreadsheet_title": spreadsheet.get("properties", {}).get("title", ""),
            "tabs": tabs,
            "tab_count": len(tabs),
        })

    except Exception as e:
        logger.error(f"Sheets list tabs error: {e}")
        await params.result_callback({"error": f"Failed to list sheet tabs: {str(e)}"})


# =============================================================================
# Exports
# =============================================================================

SHEETS_SCHEMAS = [
    read_sheet_schema,
    write_sheet_schema,
    list_sheet_tabs_schema,
]

SHEETS_HANDLERS = {
    "read_sheet": read_sheet_handler,
    "write_sheet": write_sheet_handler,
    "list_sheet_tabs": list_sheet_tabs_handler,
}
