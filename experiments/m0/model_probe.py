"""Disposable M0 Groq tool-loop probe; never imports application modules."""
import argparse
import json
from pathlib import Path

import httpx
import jsonschema
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/m0/model-probe.json"
DEFAULT_MODELS = {"groq": "openai/gpt-oss-20b", "google": "gemini-2.5-flash"}


def report(result):
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


def tool_loop(client, key, model, result):
    """Request, validate, execute fixture, return result, require final answer."""
    schemas = json.loads((ROOT / "contracts/mcp-tools.schema.json").read_text("utf-8"))
    tool = next(t for t in schemas["tools"] if t["name"] == "lookup_sku")
    fixtures = json.loads((ROOT / "tests/fixtures/m0/examples.json").read_text("utf-8"))
    sample = next(f for f in fixtures["success"]
                  if f["tool"] == "lookup_sku" and f["arguments"]["sku"] == "DEMO-001")
    messages = [
        {"role": "system", "content": "Use lookup_sku to answer from sample warehouse data. "
         "Clearly describe it as sample data. Do not invent warehouse information."},
        {"role": "user", "content": "Use lookup_sku for DEMO-001, then tell me "
         "the sample warehouse name and quantity."},
    ]
    offered = [{"type": "function", "function": {
        "name": tool["name"], "description": tool["description"],
        "parameters": tool["inputSchema"]}}]
    for _ in range(8):
        response = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json={"model": model, "messages": messages, "tools": offered,
                  "tool_choice": "auto", "max_completion_tokens": 512},
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            answer = message.get("content") or ""
            if not result["tool_calls"] or not answer.strip():
                raise ValueError("MISSING_TOOL_OR_ANSWER")
            result.update(status="PASS", stage="complete", reason_code="TOOL_LOOP_COMPLETED",
                          answer=answer.replace(key, "[REDACTED]")[:2000])
            return
        if len(calls) > 8 - len(result["tool_calls"]):
            raise ValueError("TOOL_LIMIT_REACHED")
        # Keep only fields required to return the provider's tool-call message.
        messages.append({"role": "assistant", "content": message.get("content"),
                         "tool_calls": calls})
        for call in calls:
            function = call["function"]
            if function["name"] != "lookup_sku":
                raise ValueError("UNEXPECTED_TOOL")
            arguments = json.loads(function["arguments"])
            jsonschema.validate(arguments, tool["inputSchema"])
            if arguments["sku"] != "DEMO-001":
                raise ValueError("UNEXPECTED_FIXTURE_ARGUMENT")
            result["tool_calls"].append({"name": "lookup_sku", "arguments": arguments})
            payload = sample["result"]["structuredContent"]
            jsonschema.validate(payload, tool["outputSchema"])
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(payload)})
    raise ValueError("ROUND_LIMIT_REACHED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=DEFAULT_MODELS, default="groq")
    parser.add_argument("--model", help="Optional provider model ID; confirm free account access.")
    parser.add_argument("--confirm-free-plan", action="store_true",
                        help="Confirm this run's account/model uses only free quota, no paid billing.")
    args = parser.parse_args()
    model = args.model or DEFAULT_MODELS[args.provider]
    result = {"status": "BLOCKED", "provider": args.provider, "model": model,
              "stage": "permission", "tool_calls": [], "answer": "",
              "reason_code": "FREE_PLAN_NOT_CONFIRMED"}
    # No network request or .env read without explicit free-plan confirmation.
    if not args.confirm_free_plan:
        return report(result)
    if args.provider == "google":
        result.update(stage="provider", reason_code="GOOGLE_ADAPTER_DEFERRED")
        return report(result)
    try:
        with httpx.Client(timeout=20.0, follow_redirects=False, trust_env=False) as client:
            result["stage"] = "unauthenticated_connectivity"
            # Any HTTP response proves connectivity; do not save its body.
            client.get("https://api.groq.com/openai/v1/models")
            result["stage"] = "credentials"
            config = dotenv_values(ROOT / ".env")
            key = config.get("GROQ_API_KEY")
            if not key:
                result["reason_code"] = "MISSING_GROQ_API_KEY"
                return report(result)
            result["stage"] = "tool_loop"
            tool_loop(client, key, model, result)
    except httpx.RequestError:
        result.update(status="BLOCKED", reason_code="NETWORK_UNAVAILABLE")
    except httpx.HTTPStatusError as error:
        result.update(status="BLOCKED" if error.response.status_code in (401, 403, 429) else "FAIL",
                      reason_code="PROVIDER_HTTP_" + str(error.response.status_code))
    except (ValueError, KeyError, TypeError, StopIteration, jsonschema.ValidationError):
        result.update(status="FAIL", reason_code="INVALID_MODEL_OR_FIXTURE_RESULT")
    except OSError:
        result.update(status="BLOCKED", reason_code="LOCAL_FILE_UNAVAILABLE")
    return report(result)


if __name__ == "__main__":
    raise SystemExit(main())
