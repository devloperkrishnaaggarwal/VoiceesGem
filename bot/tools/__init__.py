"""Google Tools Package.

Aggregates all Google service tools (Calendar, Sheets, Gmail)
for easy registration with the Pipecat voice agent.
"""

from pipecat.adapters.schemas.tools_schema import ToolsSchema

from tools.calendar_tools import CALENDAR_HANDLERS, CALENDAR_SCHEMAS
from tools.mail_tools import MAIL_HANDLERS, MAIL_SCHEMAS
from tools.sheets_tools import SHEETS_HANDLERS, SHEETS_SCHEMAS

# Combined exports
ALL_SCHEMAS = CALENDAR_SCHEMAS + SHEETS_SCHEMAS + MAIL_SCHEMAS
ALL_HANDLERS = {**CALENDAR_HANDLERS, **SHEETS_HANDLERS, **MAIL_HANDLERS}


def get_google_tools_schema(additional_schemas=None):
    """Get a ToolsSchema containing all Google tools.

    Args:
        additional_schemas: Optional list of extra FunctionSchema objects to include
                          (e.g., end_call).

    Returns:
        ToolsSchema with all registered tools.
    """
    schemas = list(ALL_SCHEMAS)
    if additional_schemas:
        schemas.extend(additional_schemas)
    return ToolsSchema(standard_tools=schemas)


def register_google_tools(llm):
    """Register all Google tool handlers with the LLM service.

    Args:
        llm: The Pipecat LLM service to register handlers with.
    """
    for name, handler in ALL_HANDLERS.items():
        llm.register_function(name, handler)
