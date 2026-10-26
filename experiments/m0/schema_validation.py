"""Strict timestamp checking for M0's optional JSON Schema date-time format."""
from datetime import datetime
import re
from jsonschema import Draft202012Validator, FormatChecker

CHECKER = FormatChecker()
ZONED_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})")


@CHECKER.checks("date-time", raises=(ValueError, TypeError))
def valid_timestamp(value):
    if not isinstance(value, str) or not ZONED_TIMESTAMP.fullmatch(value):
        return False
    return datetime.fromisoformat(value.replace("z", "+00:00").replace("Z", "+00:00")).tzinfo is not None


def validator(schema):
    return Draft202012Validator(schema, format_checker=CHECKER)
