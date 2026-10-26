"""Load the unchanged M0 definitions and validate without numeric coercion."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker, validators

ROOT = Path(__file__).resolve().parents[2]
NAMES = ("list_products", "create_product", "list_orders", "get_order", "update_order_status")
DEFINITIONS = {item["name"]: item for item in json.loads(
    (ROOT / "contracts/mcp-tools.schema.json").read_text(encoding="utf-8"))["tools"] if item["name"] in NAMES}
CHECKER = FormatChecker()
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")


def timestamp(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError("Invalid timestamp")
    return datetime.fromisoformat(value.replace("z", "+00:00").replace("Z", "+00:00")).astimezone(timezone.utc)


@CHECKER.checks("date-time", raises=(ValueError, TypeError, OverflowError))
def valid_timestamp(value):
    timestamp(value)
    return True


StrictValidator = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda checker, value: type(value) is int))


def valid(schema, data):
    return not any(StrictValidator(schema, format_checker=CHECKER).iter_errors(data))


def arguments(name, data):
    if not isinstance(data, dict):
        raise ValueError("Invalid arguments")
    data = {key: value.strip() if key in {"name", "search", "sku"} and isinstance(value, str) else value
            for key, value in data.items()}
    if not valid(DEFINITIONS[name]["inputSchema"], data):
        raise ValueError("Invalid arguments")
    lower = timestamp(data["created_from"]) if "created_from" in data else None
    upper = timestamp(data["created_to"]) if "created_to" in data else None
    if lower and upper and lower > upper:
        raise ValueError("Reversed bounds")
    return data
