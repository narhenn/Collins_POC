"""
AI Agent Generator - creates complete agent workflows from natural language descriptions.
Uses OpenAI to design the workflow, then structures it as React Flow JSON.
"""

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI agent workflow designer for the GoalCert AutoMind platform.
Given a user's description of what they want an agent to do, you must design a complete workflow.

A workflow consists of nodes connected by edges. Available node types:

1. **trigger** - Starts the workflow. Config: { frequency: "manual"|"hourly"|"daily"|"weekly", cron?: "cron expression", timezone?: "UTC" }
2. **ai_action** - Calls an LLM to process/generate data. Config: { prompt: "detailed prompt with {variable} placeholders", model: "gpt-4o-mini", max_tokens: 1024, temperature: 0.7, output_variable: "variable_name" }
3. **integration** - Sends email or Slack message. Config: { service: "email"|"slack", action: "send", recipients: "email@example.com", subject: "subject", body: "body with {variables}" }
4. **decision** - Branches based on condition. Config: { left_operand: "{variable}", operator: "=="|"!="|">"|"<"|"contains", right_operand: "value" }
5. **escalation** - Notifies a human. Config: { recipient_email: "email", message_template: "message with {variables}" }
6. **web_search** - Searches the web. Config: { query: "search query with {variable} placeholders", max_results: 5, output_variable: "variable_name" }
7. **code_exec** - Executes Python code in a sandboxed environment. Config: { code: "python code (can use {variable} placeholders)", timeout: 10, output_variable: "variable_name" }. The code runs in a subprocess. Local variables of simple types (str, int, float, bool, list, dict) are captured as output. No OS, subprocess, or network imports allowed.

IMPORTANT RULES:
- Every workflow MUST start with exactly one trigger node
- AI action prompts should be detailed and specific - tell the LLM exactly what to do and what format to return
- Use output_variable to name the output of each AI action so subsequent nodes can reference it with {variable_name}
- Integration nodes should use {variable} placeholders to insert data from previous nodes
- Position nodes vertically: trigger at top (y=0), then increasing y by 140 for each subsequent node, x=250 for center
- Decision nodes can branch: use edges with sourceHandle "true" or "false"
- Be practical - design workflows that actually accomplish the user's goal

Return ONLY valid JSON with this exact structure:
{
  "agent_name": "short descriptive name",
  "agent_description": "one-line description",
  "agent_type": "sales"|"marketing"|"support"|"custom",
  "schedule": { "frequency": "daily", "cron": "0 9 * * *" },
  "workflow": {
    "nodes": [...],
    "edges": [...],
    "viewport": { "x": 0, "y": 0, "zoom": 1 }
  }
}"""


async def generate_agent_from_description(description: str) -> dict:
    """Generate a complete agent workflow from a natural language description."""
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required for agent generation")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Create an agent for: {description}"},
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    raw = response.choices[0].message.content or ""

    # Parse JSON from response (handle code fences)
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]

    result = json.loads(raw.strip())

    # Validate structure
    if "workflow" not in result or "nodes" not in result["workflow"]:
        raise ValueError("Generated workflow is missing required fields")

    return result
