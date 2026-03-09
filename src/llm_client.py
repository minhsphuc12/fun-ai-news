"""
Unified LLM client supporting Anthropic (Claude) and Google Gemini.

Both providers are wrapped behind a common interface so the rest of the pipeline
never imports provider-specific SDKs directly.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class NormalizedResponse:
    content: list  # list[TextBlock | ToolUseBlock]
    stop_reason: str  # "end_turn" | "tool_use"


_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.0-flash",
}


class LLMClient:
    """Thin wrapper around Anthropic or Gemini with a unified completion interface."""

    def __init__(self, provider: str, api_key: str, model: str | None = None):
        if provider not in ("anthropic", "gemini"):
            raise ValueError(f"Unknown provider {provider!r}. Choose 'anthropic' or 'gemini'.")
        self.provider = provider
        self.model = model or _DEFAULT_MODELS[provider]
        self._client = self._init_client(provider, api_key)

    def _init_client(self, provider: str, api_key: str) -> Any:
        if provider == "anthropic":
            from anthropic import Anthropic
            return Anthropic(api_key=api_key)
        else:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai

    def complete(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
    ) -> NormalizedResponse:
        """Send a completion request and return a provider-agnostic response."""
        if self.provider == "anthropic":
            return self._complete_anthropic(messages, system, max_tokens, tools)
        return self._complete_gemini(messages, system, max_tokens, tools)

    # ── Anthropic ─────────────────────────────────────────────────────────────

    def _complete_anthropic(
        self, messages: list[dict], system: str | None, max_tokens: int, tools: list[dict] | None
    ) -> NormalizedResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        content: list = []
        for block in response.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(ToolUseBlock(id=block.id, name=block.name, input=block.input))
        return NormalizedResponse(content=content, stop_reason=response.stop_reason)

    # ── Gemini ────────────────────────────────────────────────────────────────

    def _complete_gemini(
        self, messages: list[dict], system: str | None, max_tokens: int, tools: list[dict] | None
    ) -> NormalizedResponse:
        import google.generativeai as genai

        # Build a tool_use_id → function_name lookup from prior assistant turns
        id_to_name = _build_id_to_name_map(messages)

        model_kwargs: dict[str, Any] = {
            "model_name": self.model,
            "generation_config": genai.GenerationConfig(max_output_tokens=max_tokens),
        }
        if system:
            model_kwargs["system_instruction"] = system
        if tools:
            model_kwargs["tools"] = self._convert_tools_to_gemini(tools)

        model = genai.GenerativeModel(**model_kwargs)
        contents = self._messages_to_gemini_contents(messages, id_to_name)
        response = model.generate_content(contents=contents)
        return self._normalize_gemini_response(response)

    def _convert_tools_to_gemini(self, tools: list[dict]) -> list:
        import google.generativeai as genai

        declarations = [
            genai.protos.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=self._json_schema_to_gemini_schema(tool["input_schema"]),
            )
            for tool in tools
        ]
        return [genai.protos.Tool(function_declarations=declarations)]

    def _json_schema_to_gemini_schema(self, schema: dict):
        import google.generativeai as genai

        type_map = {
            "string": genai.protos.Type.STRING,
            "integer": genai.protos.Type.INTEGER,
            "number": genai.protos.Type.NUMBER,
            "boolean": genai.protos.Type.BOOLEAN,
            "object": genai.protos.Type.OBJECT,
            "array": genai.protos.Type.ARRAY,
        }
        schema_type = type_map.get(schema.get("type", "string"), genai.protos.Type.STRING)
        properties = {
            name: genai.protos.Schema(
                type=type_map.get(prop.get("type", "string"), genai.protos.Type.STRING),
                description=prop.get("description", ""),
            )
            for name, prop in schema.get("properties", {}).items()
        }
        return genai.protos.Schema(
            type=schema_type,
            properties=properties,
            required=schema.get("required", []),
        )

    def _messages_to_gemini_contents(
        self, messages: list[dict], id_to_name: dict[str, str]
    ) -> list:
        """Translate the full Anthropic-style message list to Gemini contents."""
        import google.generativeai as genai

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]

            if isinstance(content, str):
                contents.append({"role": role, "parts": [content]})
                continue

            # content is a list: tool_result dicts (user) or TextBlock/ToolUseBlock (assistant)
            parts: list = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text":
                        parts.append(block["text"])
                    elif btype == "tool_result":
                        # Gemini FunctionResponse requires the function name, not the id
                        name = id_to_name.get(block["tool_use_id"], "unknown")
                        parts.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=name,
                                    response={"result": block["content"]},
                                )
                            )
                        )
                elif hasattr(block, "type"):
                    if block.type == "text":
                        parts.append(block.text)
                    elif block.type == "tool_use":
                        parts.append(
                            genai.protos.Part(
                                function_call=genai.protos.FunctionCall(
                                    name=block.name,
                                    args=block.input,
                                )
                            )
                        )
            if parts:
                contents.append({"role": role, "parts": parts})

        return contents

    def _normalize_gemini_response(self, response) -> NormalizedResponse:
        content: list = []
        for part in response.parts:
            if hasattr(part, "text") and part.text:
                content.append(TextBlock(text=part.text))
            elif hasattr(part, "function_call") and part.function_call.name:
                content.append(
                    ToolUseBlock(
                        id=str(uuid.uuid4()),
                        name=part.function_call.name,
                        input=dict(part.function_call.args),
                    )
                )

        has_tool_use = any(b.type == "tool_use" for b in content)
        return NormalizedResponse(
            content=content,
            stop_reason="tool_use" if has_tool_use else "end_turn",
        )


def _build_id_to_name_map(messages: list[dict]) -> dict[str, str]:
    """Scan assistant turns to build a reverse map of tool_use_id → function name.

    Gemini's FunctionResponse requires the function name, but Anthropic's tool_result
    only carries the tool_use_id. We recover the name by looking back at previous
    assistant turns that contain ToolUseBlock objects.
    """
    mapping: dict[str, str] = {}
    for msg in messages:
        if msg["role"] != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if hasattr(block, "type") and block.type == "tool_use":
                    mapping[block.id] = block.name
    return mapping
