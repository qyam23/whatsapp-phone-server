import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.db import get_management_dashboard, get_query_recent_messages
from src.utils import get_env


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_QUESTION_LENGTH = 1000
MAX_TOOL_ROUNDS = 2


class AIQueryError(RuntimeError):
    pass


class AIQueryNotConfigured(AIQueryError):
    pass


TOOLS = [
    {
        "type": "function",
        "name": "get_operations_summary",
        "description": "Get production communication KPIs and period-over-period changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["12h", "7d", "30d"]}
            },
            "required": ["period"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_top_people",
        "description": "Rank the most active message senders for a period.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["12h", "7d", "30d"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["period", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_top_groups",
        "description": "Rank active WhatsApp production groups for a period.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["12h", "7d", "30d"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["period", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_activity_trend",
        "description": "Get current and previous message activity series for comparison.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["12h", "7d", "30d"]}
            },
            "required": ["period"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_machine_recurrence",
        "description": "Get classified machine event counts and 30-day recurrence.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["12h", "7d", "30d"]}
            },
            "required": ["period"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_recent_messages",
        "description": "Get a small, bounded set of recent messages for content analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["12h", "7d", "30d"]},
                "chat": {"type": ["string", "null"], "maxLength": 100},
                "search": {"type": ["string", "null"], "maxLength": 100},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            "required": ["period", "chat", "search", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


SYSTEM_PROMPT = """
You are the operations data assistant for Mor Factory in Sderot, Israel.
Answer in clear Hebrew unless the user explicitly asks for another language.
Use only the supplied function tools. Never write SQL and never ask to execute SQL.
Do not infer facts that are absent from tool output. State data gaps directly.
Prefer concise management summaries with exact periods and numbers.
For message-content questions, request the smallest relevant message sample.
Do not reveal internal IDs, phone numbers, authentication details, or API configuration.
""".strip()


def ai_is_configured():
    return bool(get_env("OPENAI_API_KEY"))


def _period(value):
    return value if value in {"12h", "7d", "30d"} else "12h"


def _limit(value, maximum):
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return min(5, maximum)


def _redact_text(value):
    text = (value or "")[:500]
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(?<!\d)(?:\+?\d[\d -]{7,}\d)(?!\d)", "[phone]", text)
    return text


def execute_tool(name, arguments):
    period = _period(arguments.get("period"))
    dashboard = get_management_dashboard(period=period)

    if name == "get_operations_summary":
        return {
            "period": dashboard["period_label"],
            "metrics": dashboard["metrics"],
            "last_message_at": dashboard["last_message_at"],
            "machine_data_available": dashboard["machine_data_available"],
        }
    if name == "get_top_people":
        return {
            "period": dashboard["period_label"],
            "people": dashboard["top_senders"][: _limit(arguments.get("limit"), 10)],
        }
    if name == "get_top_groups":
        return {
            "period": dashboard["period_label"],
            "groups": dashboard["top_groups"][: _limit(arguments.get("limit"), 10)],
        }
    if name == "get_activity_trend":
        return {
            "period": dashboard["period_label"],
            "trend": dashboard["trend"],
        }
    if name == "get_machine_recurrence":
        return {
            "period": dashboard["period_label"],
            "data_available": dashboard["machine_data_available"],
            "selected_period": dashboard["machine_period"],
            "rolling_30_days": dashboard["machine_month"]["recurrence"],
        }
    if name == "get_recent_messages":
        result = get_query_recent_messages(
            period=period,
            chat=(arguments.get("chat") or "")[:100] or None,
            search=(arguments.get("search") or "")[:100] or None,
            limit=_limit(arguments.get("limit"), 30),
        )
        for message in result["messages"]:
            message["message"] = _redact_text(message["message"])
        return result

    raise AIQueryError(f"Unsupported tool: {name}")


def _responses_request(payload):
    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        raise AIQueryNotConfigured("OPENAI_API_KEY is not configured.")

    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise AIQueryError(f"OpenAI API returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise AIQueryError(f"OpenAI API request failed: {error}") from error


def _function_calls(response):
    return [
        item
        for item in response.get("output", [])
        if item.get("type") == "function_call"
    ]


def _response_text(response):
    parts = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def ask_database(question):
    question = (question or "").strip()
    if not question:
        raise AIQueryError("Question is required.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise AIQueryError("Question is too long.")

    model = get_env("OPENAI_MODEL", "gpt-5.4-mini")
    payload = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": question,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_output_tokens": 1200,
    }
    response = _responses_request(payload)
    tools_used = []

    for _ in range(MAX_TOOL_ROUNDS):
        calls = _function_calls(response)
        if not calls:
            answer = _response_text(response)
            if not answer:
                raise AIQueryError("The model returned no answer.")
            return {"answer": answer, "tools_used": tools_used, "model": model}

        outputs = []
        for call in calls[:4]:
            try:
                arguments = json.loads(call.get("arguments") or "{}")
            except json.JSONDecodeError as error:
                raise AIQueryError("The model returned invalid tool arguments.") from error
            result = execute_tool(call.get("name"), arguments)
            tools_used.append(call.get("name"))
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

        response = _responses_request(
            {
                "model": model,
                "previous_response_id": response["id"],
                "input": outputs,
                "tools": TOOLS,
                "max_output_tokens": 1200,
            }
        )

    raise AIQueryError("The model requested too many tool rounds.")
