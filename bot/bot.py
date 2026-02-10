"""Gemini Live Voice Agent.

A Pipecat voice agent powered by Google Gemini Live native audio.
No separate STT, TTS, or LLM needed — Gemini handles speech-to-speech natively.

Supports two transports:
  - SmallWebRTC: for local development (browser-based)
  - Twilio WebSocket: for telephony deployment

Run locally (browser):
    uv run bot.py

Run with Twilio:
    uv run bot.py -t twilio
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

SCRIPT_DIR = Path(__file__).resolve().parent
# Make the `bot` package modules importable as top-level names (e.g., `tools`).
sys.path.insert(0, str(SCRIPT_DIR))

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndTaskFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, InputParams
from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

from tools import get_google_tools_schema, register_google_tools

load_dotenv(override=True)


# =============================================================================
# Agent Configuration — Customize your voice agent here
# =============================================================================

AGENT_NAME = "Sarah"

def load_system_instructions():
    prompt_path = SCRIPT_DIR / "prompts" / "real_estate_receptionist_prompt.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load prompt from {prompt_path}: {e}")
        # Fallback to a basic instruction if file loading fails
        return f"You are {AGENT_NAME}, a professional AI assistant."

SYSTEM_INSTRUCTIONS = load_system_instructions()



# Gemini voice options: Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr
GEMINI_VOICE = "Kore"

# Model to use (native audio model for speech-to-speech)
GEMINI_MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"


# =============================================================================
# Function Calling — Add custom tools for your agent
# =============================================================================

async def end_call_handler(params: FunctionCallParams):
    """End the call gracefully when the user says goodbye."""
    logger.info("End call requested — closing session")
    await params.result_callback({"status": "call_ended"})
    # Small delay to let the goodbye message finish playing
    await asyncio.sleep(2)
    await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


def get_tools():
    """Define the tools available to the voice agent."""
    end_call = FunctionSchema(
        name="end_call",
        description="Call this function when the user wants to end the conversation or says goodbye",
        properties={},
        required=[],
    )

    # Combine end_call with all Google tools
    return get_google_tools_schema(additional_schemas=[end_call])


# =============================================================================
# Bot Pipeline
# =============================================================================

async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Set up and run the voice agent pipeline."""
    logger.info("Starting Gemini Live voice agent")

    tools = get_tools()

    # Initialize Gemini Live — this single service replaces STT + LLM + TTS
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model=GEMINI_MODEL,
        voice_id=GEMINI_VOICE,
        system_instruction=SYSTEM_INSTRUCTIONS,
        tools=tools,
    )

    # Register function handlers
    llm.register_function("end_call", end_call_handler)
    register_google_tools(llm)

    # Initial context — kicks off the conversation
    messages = [
        {
            "role": "user",
            "content": "Say a brief, warm greeting to start the conversation.",
        },
    ]

    context = LLMContext(messages)

    # Context aggregators track the conversation history
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    # The pipeline — beautifully simple with Gemini Live
    # Audio in → context tracking → Gemini (speech-to-speech) → audio out
    pipeline = Pipeline(
        [
            transport.input(),        # 1. Capture user audio
            user_aggregator,          # 2. Track user speech in context
            llm,                      # 3. Gemini Live: audio → audio (no STT/TTS!)
            transport.output(),       # 4. Play response audio
            assistant_aggregator,     # 5. Track bot responses in context
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    # ── Event Handlers ──────────────────────────────────────────────────────

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected — starting conversation")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message: UserTurnStoppedMessage):
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        logger.info(f"📝 {timestamp}User: {message.content}")

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        logger.info(f"🤖 {timestamp}Agent: {message.content}")

    # ── Run ──────────────────────────────────────────────────────────────────

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


# =============================================================================
# Entry Point
# =============================================================================

async def bot(runner_args: RunnerArguments):
    """Main bot entry point — compatible with both local dev and Pipecat Cloud."""

    # Krisp noise filter is available on Pipecat Cloud
    krisp_filter = None
    if os.environ.get("ENV") != "local":
        try:
            from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter
            krisp_filter = KrispVivaFilter()
        except ImportError:
            logger.warning("Krisp filter not available — running without noise filtering")

    # Transport configuration for each provider
    transport_params = {
        "twilio": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_in_filter=krisp_filter,
            audio_out_enabled=True,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_in_filter=krisp_filter,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
