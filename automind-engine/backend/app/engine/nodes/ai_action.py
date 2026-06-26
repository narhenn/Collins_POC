import json
import logging
from typing import Any

from app.core.config import settings
from app.engine.nodes.base import BaseNodeExecutor
from app.engine.variables import interpolate

logger = logging.getLogger(__name__)

# Cost per million tokens (input, output)
_COST_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3-mini": (1.10, 4.40),
    # Anthropic
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}
_DEFAULT_COST = (2.50, 10.0)


def _is_openai_model(model: str) -> bool:
    return model.startswith(("gpt-", "o1", "o3", "o4"))


def _has_openai_key() -> bool:
    return bool(settings.OPENAI_API_KEY) and settings.OPENAI_API_KEY not in {"", "sk-proj-your-key-here"}


def _has_anthropic_key() -> bool:
    return bool(settings.ANTHROPIC_API_KEY) and settings.ANTHROPIC_API_KEY not in {"", "sk-ant-your-key-here"}


class AIActionNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        prompt_template = config.get("prompt", "")
        prompt = interpolate(prompt_template, variables)
        model = config.get("model", "gpt-4o-mini")
        max_tokens = config.get("max_tokens", 1024)
        temperature = config.get("temperature", 0.7)
        system_prompt = config.get("system_prompt")
        output_variable = config.get("output_variable")

        if system_prompt:
            system_prompt = interpolate(system_prompt, variables)

        # Inject memory context from past executions
        memory_context = kwargs.get("memory_context", "")
        if memory_context:
            if system_prompt:
                system_prompt = f"{memory_context}\n\n{system_prompt}"
            else:
                system_prompt = memory_context

        # Determine which provider to use
        is_openai = _is_openai_model(model)

        if is_openai and not _has_openai_key():
            return self._mock_response(prompt, model, output_variable)
        if not is_openai and not _has_anthropic_key():
            return self._mock_response(prompt, model, output_variable)

        try:
            if is_openai:
                return await self._call_openai(
                    prompt=prompt, model=model, max_tokens=max_tokens,
                    temperature=temperature, system_prompt=system_prompt,
                    output_variable=output_variable,
                )
            else:
                return await self._call_anthropic(
                    prompt=prompt, model=model, max_tokens=max_tokens,
                    temperature=temperature, system_prompt=system_prompt,
                    output_variable=output_variable,
                )
        except Exception as exc:
            logger.exception("AI API error")
            return self._error_response(str(exc), model)

    async def _call_openai(
        self, *, prompt: str, model: str, max_tokens: int,
        temperature: float, system_prompt: str | None, output_variable: str | None,
    ) -> dict:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        response_text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        output_vars = self._parse_output(response_text)
        if output_variable:
            output_vars = {output_variable: output_vars}

        return {
            "output_variables": output_vars,
            "llm_usage": {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            },
        }

    async def _call_anthropic(
        self, *, prompt: str, model: str, max_tokens: int,
        temperature: float, system_prompt: str | None, output_variable: str | None,
    ) -> dict:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await client.messages.create(**kwargs)

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        output_vars = self._parse_output(response_text)
        if output_variable:
            output_vars = {output_variable: output_vars}

        return {
            "output_variables": output_vars,
            "llm_usage": {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            },
        }

    @staticmethod
    def _parse_output(text: str) -> dict | str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            try:
                return json.loads(inner)
            except (json.JSONDecodeError, ValueError):
                pass
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
            return {"output": parsed}
        except (json.JSONDecodeError, ValueError):
            return {"output": text}

    @staticmethod
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        input_rate, output_rate = _COST_TABLE.get(model, _DEFAULT_COST)
        return round(
            (input_tokens * input_rate / 1_000_000) + (output_tokens * output_rate / 1_000_000), 6
        )

    @staticmethod
    def _mock_response(prompt: str, model: str, output_variable: str | None) -> dict:
        mock_output: dict = {"output": f"[MOCK] No API key for {model}. Prompt: {prompt[:100]}...", "mock": True}
        if output_variable:
            mock_output = {output_variable: mock_output}
        return {
            "output_variables": mock_output,
            "llm_usage": {"model": model, "input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        }

    @staticmethod
    def _error_response(error_msg: str, model: str) -> dict:
        return {
            "output_variables": {"error": error_msg},
            "llm_usage": {"model": model, "input_tokens": 0, "output_tokens": 0, "cost": 0.0},
            "error": error_msg,
        }
