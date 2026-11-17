"""Provider selection for the chat pipeline."""

from __future__ import annotations

from ognex import runtime_settings
from ognex.langmodel.client import get_chat_client
from ognex.langmodel.streamer_graph import EndpointStreamer, GraphStreamer


def initialise_streamer_from_config(config=None) -> GraphStreamer:
    """Return a streamer using the runtime-selected OpenAI-compatible endpoint."""
    runtime = runtime_settings.load()
    return EndpointStreamer(
        get_chat_client(runtime),
        model_name=runtime.model,
        context_window=runtime.context_window,
    )
