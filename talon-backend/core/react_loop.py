from __future__ import annotations

"""
ReAct Loop Engine for Project Talon.

Implements the Perceive → Plan → Act → Observe → Decide cycle using
a provider-agnostic LLM layer (AnthropicProvider / OpenAIProvider /
GeminiProvider / local models).

The loop:
  1. Load conversation history from memory
  2. Append the new user message
  3. Call the configured LLM provider with the agent's tools
  4. If stop_reason == "end_turn"  → return the text response
  5. If stop_reason == "tool_use"  → execute tools, append results, go to 3
  6. Repeat up to max_iterations
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Coroutine, Optional

from core import memory, audit, policy
from core.llm_providers import LLMProvider, LLMResponse, ProviderFactory
from tools.registry import get_tool_definitions, execute_tool

logger = logging.getLogger(__name__)


def _content_to_list(content: Any) -> list[dict]:
    """
    Normalise response content to a JSON-serialisable list of dicts
    so we can store it in SQLite and replay it.
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        out = []
        for block in content:
            if hasattr(block, "model_dump"):
                out.append(block.model_dump())
            elif isinstance(block, dict):
                out.append(block)
            else:
                out.append({"type": "text", "text": str(block)})
        return out
    return [{"type": "text", "text": str(content)}]


def _response_to_anthropic_content(response: LLMResponse) -> list[dict]:
    """
    Convert a normalised LLMResponse back to Anthropic-style content blocks
    so we can store them in memory and feed them back into the conversation
    history (which is always kept in Anthropic format internally).
    """
    blocks: list[dict] = []

    if response.content:
        blocks.append({"type": "text", "text": response.content})

    for tc in response.tool_calls:
        blocks.append({
            "type": "tool_use",
            "id": tc.get("id") or f"tool_{uuid.uuid4().hex[:8]}",
            "name": tc["tool_name"],
            "input": tc["tool_input"],
        })

    return blocks


# ── ws_callback type alias ─────────────────────────────────────────────────────
# Optional async callback for real-time WebSocket streaming:
#   ws_callback(event_dict) → None
WsCallback = Optional[Callable[[dict], Coroutine[Any, Any, None]]]


class ReActLoop:
    """
    Drives one agent through its ReAct reasoning loop.

    Usage:
        loop = ReActLoop()
        response = await loop.run(
            agent_config=...,
            message="What time is it?",
            conversation_id="conv-123",
            user_id="user@example.com",
        )
    """

    async def run(
        self,
        agent_config: dict,
        message: str,
        conversation_id: str,
        user_id: str = "unknown",
        max_iterations: int = 10,
        ws_callback: WsCallback = None,
    ) -> str:
        """
        Run the ReAct loop for one user message.

        Args:
            agent_config:    Agent config dict from agents.yaml (with 'id' injected).
            message:         The user's input text.
            conversation_id: Unique conversation identifier for memory storage.
            user_id:         Who is sending the message (for audit trail).
            max_iterations:  Guard against infinite loops.
            ws_callback:     Optional async function for real-time WebSocket updates.
                             Called with event dicts: {"type": "typing"|"tool_call"|...}
        """
        agent_id = agent_config["id"]

        kill_switch = await memory.get_kill_switch_state()
        if kill_switch["active"]:
            reason = kill_switch.get("reason") or "The global kill switch is active."
            await audit.log_event(
                agent_id=agent_id,
                event_type="message_blocked",
                user_id=user_id,
                conversation_id=conversation_id,
                details={"reason": "kill_switch", "message": message[:500]},
            )
            return f"⛔ Agent activity is halted by the global kill switch. {reason}"

        # ── Policy check on incoming message ─────────────────────────────────
        allowed, reason = await policy.check_message_async(message)
        if not allowed:
            await audit.log_event(
                agent_id=agent_id,
                event_type="policy_blocked",
                user_id=user_id,
                conversation_id=conversation_id,
                details={"reason": reason, "message": message[:500]},
            )
            return f"⚠️ I'm sorry, I can't help with that. ({reason})"

        # ── Load conversation history ─────────────────────────────────────────
        messages = await memory.get_conversation_history(conversation_id, agent_id)

        # ── Append the new user message ───────────────────────────────────────
        await memory.append_message(conversation_id, agent_id, "user", message)
        messages.append({"role": "user", "content": message})

        await audit.log_event(
            agent_id=agent_id,
            event_type="message_received",
            user_id=user_id,
            conversation_id=conversation_id,
            details={"text": message[:500]},
        )

        # ── Get LLM provider for this agent ──────────────────────────────────
        try:
            provider, model = ProviderFactory.from_agent_config(agent_config)
        except (ValueError, RuntimeError) as exc:
            logger.error("[%s] Provider init error: %s", agent_id, exc)
            return f"⚠️ Configuration error: {exc}"

        logger.debug(
            "[%s] Using provider=%s model=%s",
            agent_id,
            agent_config.get("llm", {}).get("provider", "anthropic"),
            model,
        )

        # ── Build tool definitions for this agent ────────────────────────────
        agent_tools = agent_config.get("tools", [])
        tool_defs = get_tool_definitions(agent_tools)

        system_prompt = agent_config.get(
            "system_prompt", "You are a helpful assistant."
        )

        # ── Notify WebSocket: thinking started ────────────────────────────────
        if ws_callback:
            await _safe_ws_call(
                ws_callback,
                {"type": "typing", "agent": agent_id},
            )

        # ── ReAct loop ────────────────────────────────────────────────────────
        final_response = (
            "I wasn't able to complete your request within the iteration limit."
        )

        for iteration in range(max_iterations):
            logger.debug(
                "[%s] ReAct iteration %d/%d conv=%s",
                agent_id, iteration + 1, max_iterations, conversation_id,
            )

            try:
                llm_response: LLMResponse = await provider.chat(
                    model=model,
                    system=system_prompt,
                    messages=messages,
                    tools=tool_defs,
                )
            except Exception as exc:
                logger.error("[%s] LLM API error: %s", agent_id, exc)
                await audit.log_event(
                    agent_id=agent_id,
                    event_type="error",
                    conversation_id=conversation_id,
                    details={"error": str(exc)},
                )
                if ws_callback:
                    await _safe_ws_call(
                        ws_callback,
                        {"type": "error", "text": f"LLM API error: {exc}"},
                    )
                return f"⚠️ I encountered an API error: {exc}"

            # ── Agent finished ────────────────────────────────────────────────
            if llm_response.stop_reason == "end_turn":
                final_response = llm_response.content
                # Store in Anthropic format for cross-provider history compatibility
                assistant_content = _response_to_anthropic_content(llm_response)
                await memory.append_message(
                    conversation_id, agent_id, "assistant", assistant_content
                )
                await audit.log_event(
                    agent_id=agent_id,
                    event_type="agent_response",
                    conversation_id=conversation_id,
                    details={
                        "response": final_response[:500],
                        "iterations": iteration + 1,
                        "usage": llm_response.usage,
                    },
                )
                break

            # ── Tool use ─────────────────────────────────────────────────────
            if llm_response.stop_reason == "tool_use" or llm_response.tool_calls:
                assistant_content = _response_to_anthropic_content(llm_response)
                await memory.append_message(
                    conversation_id, agent_id, "assistant", assistant_content
                )
                messages.append(
                    {"role": "assistant", "content": assistant_content}
                )

                # Execute all requested tools
                tool_results = await self._execute_tools(
                    llm_response.tool_calls,
                    agent_id,
                    conversation_id,
                    ws_callback=ws_callback,
                )

                # Notify WS: still thinking after tools
                if ws_callback:
                    await _safe_ws_call(
                        ws_callback,
                        {"type": "typing", "agent": agent_id},
                    )

                # Append tool results as user-role message (Anthropic convention)
                await memory.append_message(
                    conversation_id, agent_id, "user", tool_results
                )
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unknown stop reason — bail
            logger.warning(
                "[%s] Unexpected stop_reason: %s", agent_id, llm_response.stop_reason
            )
            break

        # ── Auto-summarise after a substantive exchange ───────────────────────
        asyncio.create_task(
            self._maybe_summarise(
                agent_config, conversation_id, messages, provider, model
            )
        )

        return final_response

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _execute_tools(
        self,
        tool_calls: list[dict],
        agent_id: str,
        conversation_id: str,
        ws_callback: WsCallback = None,
    ) -> list[dict]:
        """
        Execute all tool calls from the LLM response.
        Returns a list of tool_result blocks (Anthropic format) to feed back.
        """
        tool_result_blocks = []

        for tc in tool_calls:
            tool_name = tc.get("tool_name", "")
            tool_input = tc.get("tool_input", {})
            tool_id = tc.get("id") or f"tool_{uuid.uuid4().hex[:8]}"

            logger.info(
                "[%s] Tool call: %s(%s)", agent_id, tool_name,
                json.dumps(tool_input, default=str)[:200],
            )

            # Notify WebSocket about tool call
            if ws_callback:
                await _safe_ws_call(
                    ws_callback,
                    {
                        "type": "tool_call",
                        "tool": tool_name,
                        "input": json.dumps(tool_input, default=str)[:300],
                    },
                )

            # Policy check before execution
            allowed, reason = await policy.check_tool_call_async(tool_name, tool_input)
            if not allowed:
                result_text = f"Tool blocked by policy: {reason}"
                await audit.log_event(
                    agent_id=agent_id,
                    event_type="policy_blocked",
                    conversation_id=conversation_id,
                    details={
                        "tool": tool_name,
                        "input": tool_input,
                        "reason": reason,
                    },
                )
            else:
                try:
                    result_text = await execute_tool(
                        tool_name, tool_input, agent_id=agent_id
                    )
                except Exception as exc:
                    result_text = f"Tool error: {exc}"
                    logger.error(
                        "[%s] Tool %s raised: %s", agent_id, tool_name, exc
                    )

                await audit.log_event(
                    agent_id=agent_id,
                    event_type="tool_called",
                    conversation_id=conversation_id,
                    details={
                        "tool": tool_name,
                        "input": tool_input,
                        "result_preview": str(result_text)[:300],
                    },
                )

            # Notify WebSocket about tool result
            if ws_callback:
                await _safe_ws_call(
                    ws_callback,
                    {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result": str(result_text)[:500],
                    },
                )

            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result_text),
                }
            )

        return tool_result_blocks

    async def _maybe_summarise(
        self,
        agent_config: dict,
        conversation_id: str,
        messages: list[dict],
        provider: LLMProvider,
        model: str,
    ) -> None:
        """
        After a conversation turn, generate a short episodic summary and store it.
        Only runs if there are enough messages to be worth summarising.
        """
        if len(messages) < 4:
            return

        agent_id = agent_config["id"]

        transcript_parts = []
        for m in messages[-10:]:
            role = m.get("role", "")
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text_parts.append(b.get("text", ""))
                content = " ".join(text_parts)
            transcript_parts.append(f"{role.upper()}: {str(content)[:300]}")

        transcript = "\n".join(transcript_parts)

        try:
            summary_response = await provider.chat(
                model=model,
                system=(
                    "You are a memory assistant. Summarize the following conversation "
                    "in 1-3 sentences, focusing on key facts, decisions, or outcomes. "
                    "Be concise and factual."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": f"Summarize this conversation:\n\n{transcript}",
                    }
                ],
                tools=[],
            )
            summary = summary_response.content
            if summary:
                await memory.store_episodic(
                    agent_id=agent_id,
                    summary=summary,
                    tags=[conversation_id],
                )
                logger.debug(
                    "[%s] Episodic memory stored for %s", agent_id, conversation_id
                )
        except Exception as exc:
            # Non-critical — don't crash
            logger.warning("[%s] Episodic summarise failed: %s", agent_id, exc)


async def _safe_ws_call(callback: WsCallback, event: dict) -> None:
    """Call the WebSocket callback safely, ignoring errors."""
    if callback is None:
        return
    try:
        await callback(event)
    except Exception as exc:
        logger.debug("ws_callback error (non-fatal): %s", exc)


# ── Module-level singleton ────────────────────────────────────────────────────
_react_loop: Optional[ReActLoop] = None


def get_react_loop() -> ReActLoop:
    global _react_loop
    if _react_loop is None:
        _react_loop = ReActLoop()
    return _react_loop
