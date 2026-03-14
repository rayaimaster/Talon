"""
Multi-provider LLM abstraction for Project Talon.

Normalizes tool_use across Anthropic, OpenAI, and OpenAI-compatible providers
so the ReAct loop is completely provider-agnostic.

Supported providers:
  - "anthropic" : Claude via anthropic SDK
  - "openai"    : GPT-4o, GPT-4o-mini, etc. via openai SDK
  - "local"     : LM Studio, Ollama, vLLM — any OpenAI-compatible endpoint
  - "gemini"    : Gemini 1.5 Flash/Pro via google-generativeai SDK

Usage:
    provider = ProviderFactory.create("anthropic", {"model": "claude-3-5-haiku-20241022"})
    response = await provider.chat(
        model="claude-3-5-haiku-20241022",
        system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Hello!"}],
        tools=[],
    )
    print(response.content)
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Response model ─────────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Normalised response from any LLM provider."""
    content: str                    # Final text response (may be empty if tool_use)
    tool_calls: list[dict]          # [{tool_name, tool_input}, ...]
    stop_reason: str                # "end_turn" | "tool_use"
    usage: dict = field(default_factory=dict)  # {input_tokens, output_tokens}

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# ── Abstract base ──────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def chat(
        self,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """
        Send a chat request and return a normalised LLMResponse.

        Args:
            model:    Provider-specific model identifier.
            system:   System prompt string.
            messages: Conversation history in Anthropic-compatible format
                      [{"role": "user"|"assistant", "content": "..."}, ...].
            tools:    Anthropic-format tool definitions (will be converted
                      per-provider as needed).
        """


# ── Anthropic provider ─────────────────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    """Claude via the anthropic SDK."""

    def __init__(self, api_key: str):
        try:
            import anthropic as _anthropic
            self._anthropic = _anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        self._api_key = api_key
        self._client: Any = None  # lazy init

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def chat(
        self,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        resp = await client.messages.create(**kwargs)

        # Extract text content
        text_parts = []
        tool_calls = []
        for block in resp.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "tool_name": block.name,
                        "tool_input": block.input,
                    })
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "tool_name": block.get("name"),
                        "tool_input": block.get("input", {}),
                    })

        stop_reason = "tool_use" if tool_calls else "end_turn"
        if hasattr(resp, "stop_reason"):
            raw_stop = resp.stop_reason
            if raw_stop == "tool_use":
                stop_reason = "tool_use"
            elif raw_stop == "end_turn":
                stop_reason = "end_turn"

        usage = {}
        if hasattr(resp, "usage"):
            usage = {
                "input_tokens": getattr(resp.usage, "input_tokens", 0),
                "output_tokens": getattr(resp.usage, "output_tokens", 0),
            }

        return LLMResponse(
            content="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )


# ── OpenAI / OpenAI-compatible provider ───────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """
    Works for:
      - OpenAI API (base_url=None, uses OPENAI_API_KEY)
      - LM Studio   (base_url="http://localhost:1234/v1")
      - Ollama      (base_url="http://localhost:11434/v1")
      - vLLM        (base_url="http://localhost:8080/v1")
      - Any OpenAI-compatible endpoint

    Tool calling for local models:
      - First attempts OpenAI function-calling format
      - Falls back to ReAct-style JSON prompting if the model
        returns a plain text response (no tool_calls in the API response)
    """

    # ReAct-style fallback prompt appended to system when tools are available
    _REACT_SYSTEM_SUFFIX = """

You have access to the following tools. When you want to use a tool, respond ONLY with a JSON object in this exact format (no other text):
{"tool_call": {"name": "<tool_name>", "arguments": {<arguments_json>}}}

When you have a final answer and don't need any tools, respond with plain text.

Available tools:
{tools_json}
"""

    _REACT_PARSE_RE = re.compile(
        r'\{["\']?tool_call["\']?\s*:\s*\{.*?\}\s*\}',
        re.DOTALL,
    )

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        try:
            import openai as _openai
            self._openai = _openai
        except ImportError:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            )
        self._api_key = api_key
        self._base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = self._openai.AsyncOpenAI(**kwargs)
        return self._client

    def _anthropic_tools_to_openai(self, tools: list[dict]) -> list[dict]:
        """Convert Anthropic tool definitions to OpenAI function-calling format."""
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return result

    def _anthropic_messages_to_openai(self, messages: list[dict]) -> list[dict]:
        """
        Convert Anthropic-format messages to OpenAI format.
        Handles tool_result and tool_use content blocks.
        """
        result = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                result.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                # Check for tool_use blocks (assistant message with tool calls)
                tool_use_blocks = [
                    b for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ]
                text_blocks = [
                    b for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                tool_result_blocks = [
                    b for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                ]

                if tool_use_blocks:
                    # Assistant message with tool calls
                    text_content = " ".join(
                        b.get("text", "") for b in text_blocks
                    ).strip()
                    tool_calls_oai = []
                    for b in tool_use_blocks:
                        tool_calls_oai.append({
                            "id": b.get("id", "call_0"),
                            "type": "function",
                            "function": {
                                "name": b.get("name", ""),
                                "arguments": json.dumps(b.get("input", {})),
                            },
                        })
                    oai_msg: dict = {"role": "assistant", "tool_calls": tool_calls_oai}
                    if text_content:
                        oai_msg["content"] = text_content
                    result.append(oai_msg)

                elif tool_result_blocks:
                    # User message with tool results → convert to tool role
                    for b in tool_result_blocks:
                        result.append({
                            "role": "tool",
                            "tool_call_id": b.get("tool_use_id", "call_0"),
                            "content": str(b.get("content", "")),
                        })

                else:
                    # Plain text content list
                    text = " ".join(
                        b.get("text", "") if isinstance(b, dict) else str(b)
                        for b in content
                    ).strip()
                    result.append({"role": role, "content": text})
            else:
                result.append({"role": role, "content": str(content)})

        return result

    async def chat(
        self,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        client = self._get_client()
        oai_messages = self._anthropic_messages_to_openai(messages)
        # Prepend system message
        oai_messages = [{"role": "system", "content": system}] + oai_messages

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": 4096,
        }

        if tools:
            oai_tools = self._anthropic_tools_to_openai(tools)
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            # If the model doesn't support tool calling, fall back to ReAct prompting
            err_str = str(exc).lower()
            if tools and any(
                kw in err_str for kw in ["tool", "function", "not support", "unsupported"]
            ):
                logger.warning(
                    "Model %s doesn't support tool calling, falling back to ReAct prompting: %s",
                    model, exc
                )
                return await self._chat_react_fallback(
                    client=client,
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tools,
                )
            raise

        choice = resp.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "tool_name": tc.function.name,
                    "tool_input": args,
                })

        # Check if we got a plain-text response that looks like a ReAct JSON call
        text = message.content or ""
        if not tool_calls and tools and text:
            react_calls = self._parse_react_json(text)
            if react_calls:
                tool_calls = react_calls
                text = ""

        stop_reason = "tool_use" if tool_calls else "end_turn"

        usage = {}
        if resp.usage:
            usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
            }

        return LLMResponse(
            content=text.strip(),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )

    async def _chat_react_fallback(
        self,
        client: Any,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """
        ReAct-style fallback: inject tool descriptions into system prompt,
        then parse JSON tool calls from the model's plain-text response.
        """
        tools_desc = []
        for t in tools:
            tools_desc.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            })

        augmented_system = system + self._REACT_SYSTEM_SUFFIX.format(
            tools_json=json.dumps(tools_desc, indent=2)
        )

        oai_messages = self._anthropic_messages_to_openai(messages)
        oai_messages = [{"role": "system", "content": augmented_system}] + oai_messages

        resp = await client.chat.completions.create(
            model=model,
            messages=oai_messages,
            max_tokens=4096,
        )

        text = (resp.choices[0].message.content or "").strip()
        tool_calls = self._parse_react_json(text)

        if tool_calls:
            text = ""
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"

        usage = {}
        if resp.usage:
            usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
            }

        return LLMResponse(
            content=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )

    def _parse_react_json(self, text: str) -> list[dict]:
        """
        Try to parse a ReAct-style JSON tool call from model output.
        Returns a list of tool_call dicts (may be empty).
        """
        # Try to find JSON block in the text
        text_stripped = text.strip()

        # Try direct JSON parse first
        if text_stripped.startswith("{"):
            try:
                obj = json.loads(text_stripped)
                if "tool_call" in obj:
                    tc = obj["tool_call"]
                    return [{
                        "id": "react_call_0",
                        "tool_name": tc.get("name", ""),
                        "tool_input": tc.get("arguments", {}),
                    }]
            except json.JSONDecodeError:
                pass

        # Try regex extraction
        match = self._REACT_PARSE_RE.search(text)
        if match:
            try:
                obj = json.loads(match.group(0))
                if "tool_call" in obj:
                    tc = obj["tool_call"]
                    return [{
                        "id": "react_call_0",
                        "tool_name": tc.get("name", ""),
                        "tool_input": tc.get("arguments", {}),
                    }]
            except json.JSONDecodeError:
                pass

        # Try markdown code block extraction
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            try:
                obj = json.loads(code_block.group(1))
                if "tool_call" in obj:
                    tc = obj["tool_call"]
                    return [{
                        "id": "react_call_0",
                        "tool_name": tc.get("name", ""),
                        "tool_input": tc.get("arguments", {}),
                    }]
            except json.JSONDecodeError:
                pass

        return []


# ── Google Gemini provider ─────────────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    """Google Gemini via the google-generativeai SDK."""

    def __init__(self, api_key: str):
        try:
            import google.generativeai as genai
            self._genai = genai
        except ImportError:
            raise RuntimeError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )
        self._api_key = api_key
        self._genai.configure(api_key=api_key)

    def _anthropic_tools_to_gemini(self, tools: list[dict]) -> list[Any]:
        """Convert Anthropic tool definitions to Gemini FunctionDeclaration format."""
        from google.generativeai.types import FunctionDeclaration, Tool as GeminiTool

        fn_decls = []
        for t in tools:
            schema = t.get("input_schema", {})
            # Gemini wants parameters in a slightly different format
            params = {}
            if schema.get("properties"):
                params = {
                    "type": "object",
                    "properties": {
                        k: {
                            "type": v.get("type", "string").upper(),
                            "description": v.get("description", ""),
                        }
                        for k, v in schema["properties"].items()
                    },
                    "required": schema.get("required", []),
                }

            fn_decls.append(
                FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=params if params else None,
                )
            )

        if fn_decls:
            return [GeminiTool(function_declarations=fn_decls)]
        return []

    def _anthropic_messages_to_gemini(
        self, messages: list[dict]
    ) -> list[dict]:
        """Convert Anthropic-format messages to Gemini content format."""
        gemini_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            gemini_role = "model" if role == "assistant" else "user"

            if isinstance(content, str):
                gemini_messages.append({
                    "role": gemini_role,
                    "parts": [{"text": content}],
                })
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append({"text": block.get("text", "")})
                        elif block.get("type") == "tool_use":
                            parts.append({
                                "function_call": {
                                    "name": block.get("name", ""),
                                    "args": block.get("input", {}),
                                }
                            })
                        elif block.get("type") == "tool_result":
                            parts.append({
                                "function_response": {
                                    "name": block.get("tool_use_id", ""),
                                    "response": {"content": str(block.get("content", ""))},
                                }
                            })
                if parts:
                    gemini_messages.append({"role": gemini_role, "parts": parts})
        return gemini_messages

    async def chat(
        self,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        import asyncio

        gemini_tools = self._anthropic_tools_to_gemini(tools) if tools else None

        model_obj = self._genai.GenerativeModel(
            model_name=model,
            system_instruction=system,
            tools=gemini_tools,
        )

        history = self._anthropic_messages_to_gemini(messages[:-1]) if messages else []
        last_msg = messages[-1]["content"] if messages else ""
        if isinstance(last_msg, list):
            last_text = " ".join(
                b.get("text", "") for b in last_msg
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            last_text = str(last_msg)

        chat = model_obj.start_chat(history=history)

        # Gemini SDK is sync — run in executor
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, chat.send_message, last_text)
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise

        tool_calls = []
        text_parts = []

        for part in resp.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                args = dict(fc.args) if fc.args else {}
                tool_calls.append({
                    "id": f"gemini_{fc.name}",
                    "tool_name": fc.name,
                    "tool_input": args,
                })
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)

        stop_reason = "tool_use" if tool_calls else "end_turn"

        usage = {}
        if hasattr(resp, "usage_metadata"):
            usage = {
                "input_tokens": getattr(resp.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(resp.usage_metadata, "candidates_token_count", 0),
            }

        return LLMResponse(
            content="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )


# ── Provider factory ───────────────────────────────────────────────────────────

class ProviderFactory:
    """Creates LLM provider instances from config."""

    @staticmethod
    def create(provider_name: str, config: dict) -> LLMProvider:
        """
        Create and return the appropriate LLM provider.

        Args:
            provider_name: "anthropic" | "openai" | "local" | "gemini"
            config: Provider-specific config dict from agents.yaml (the llm: block)
                    May include: api_key, base_url, model (model is passed separately to chat())

        Returns:
            An LLMProvider instance ready to use.

        Raises:
            ValueError: If provider_name is unknown.
            RuntimeError: If required SDK is not installed.
        """
        name = provider_name.lower().strip()

        if name == "anthropic":
            api_key = (
                config.get("api_key")
                or os.environ.get("ANTHROPIC_API_KEY", "")
            )
            if not api_key or api_key.startswith("sk-ant-..."):
                logger.warning(
                    "ANTHROPIC_API_KEY not set — Anthropic provider will fail on first call"
                )
            return AnthropicProvider(api_key=api_key)

        elif name in ("openai",):
            api_key = (
                config.get("api_key")
                or os.environ.get("OPENAI_API_KEY", "")
            )
            if not api_key:
                logger.warning(
                    "OPENAI_API_KEY not set — OpenAI provider will fail on first call"
                )
            return OpenAIProvider(api_key=api_key, base_url=None)

        elif name == "local":
            # LM Studio, Ollama, vLLM, or any OpenAI-compatible endpoint
            api_key = (
                config.get("api_key")
                or os.environ.get("LOCAL_LLM_API_KEY", "lm-studio")
            )
            base_url = (
                config.get("base_url")
                or os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
            )
            logger.info("Local LLM provider: base_url=%s", base_url)
            return OpenAIProvider(api_key=api_key, base_url=base_url)

        elif name == "gemini":
            api_key = (
                config.get("api_key")
                or os.environ.get("GEMINI_API_KEY", "")
            )
            if not api_key:
                logger.warning(
                    "GEMINI_API_KEY not set — Gemini provider will fail on first call"
                )
            return GeminiProvider(api_key=api_key)

        else:
            raise ValueError(
                f"Unknown LLM provider: {provider_name!r}. "
                "Choose from: anthropic, openai, local, gemini"
            )

    @staticmethod
    def from_agent_config(agent_config: dict) -> tuple["LLMProvider", str]:
        """
        Convenience: extract provider + model from an agent config dict.

        Returns:
            (provider_instance, model_string)
        """
        llm_config = agent_config.get("llm", {})

        # Legacy fallback: agents without llm: block use Anthropic
        if not llm_config:
            provider_name = "anthropic"
            model = agent_config.get("model", "claude-3-5-haiku-20241022")
        else:
            provider_name = llm_config.get("provider", "anthropic")
            model = (
                llm_config.get("model")
                or agent_config.get("model")
                or _default_model(provider_name)
            )

        provider = ProviderFactory.create(provider_name, llm_config)
        return provider, model


def _default_model(provider_name: str) -> str:
    """Return a sensible default model name for each provider."""
    defaults = {
        "anthropic": "claude-3-5-haiku-20241022",
        "openai": "gpt-4o-mini",
        "local": "llama-3.2-3b-instruct",
        "gemini": "gemini-1.5-flash",
    }
    return defaults.get(provider_name.lower(), "claude-3-5-haiku-20241022")
