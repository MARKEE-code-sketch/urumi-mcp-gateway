"""Five shop operations with strict projection, pagination, and safe MCP replies."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import re
import secrets
import time

from mcp import types

from .schemas import DEFINITIONS, arguments, timestamp, valid
from .woocommerce_client import ShopError, protocol_error

LOG = logging.getLogger("woocommerce_mcp")
MONEY = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?")


def money(value, nullable=False):
    if nullable and value in {None, ""}:
        return None
    if not isinstance(value, str) or len(value) > 32 or not MONEY.fullmatch(value):
        raise protocol_error()
    return format(Decimal(value), ".2f")


def product(source, currency):
    if not isinstance(source, dict):
        raise protocol_error()
    try:
        result = {key: source[key] for key in ("id", "name", "sku", "status", "permalink")}
        result.update(price=money(source["price"], True), regular_price=money(source["regular_price"], True), currency=currency)
        return result
    except (KeyError, TypeError):
        raise protocol_error() from None


def order(source):
    if not isinstance(source, dict):
        raise protocol_error()
    try:
        result = {key: source[key] for key in ("id", "number", "status", "currency")}
        utc = source["date_created_gmt"]
        if not isinstance(utc, str):
            raise ValueError()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", utc):
            utc += "Z"
        result.update(total=money(source["total"]), date_created=timestamp(utc).isoformat().replace("+00:00", "Z"))
        if not isinstance(source["line_items"], list):
            raise TypeError()
        result["line_items"] = [{**{key: line[key] for key in ("product_id", "name", "sku", "quantity")},
                                 "total": money(line["total"])} for line in source["line_items"]]
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        raise protocol_error() from None


def envelope(data, error=False):
    fields = {"content": [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))], "isError": error}
    if not error:
        fields["structuredContent"] = data
    return types.CallToolResult(**fields)


def error(code, message):
    return envelope({"error": {"code": code, "message": message}}, True)


def redact(value, configured_secrets):
    if isinstance(value, str):
        for secret in configured_secrets:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item, configured_secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, configured_secrets) for key, item in value.items()}
    return value


class Tools:
    def __init__(self, client, deadline=8, max_pages=20):
        self.client, self.deadline, self.max_pages = client, deadline, max_pages

    async def call(self, name, inputs):
        started, correlation = time.monotonic(), secrets.token_hex(8)
        try:
            try:
                args = arguments(name, inputs)
                bounds = self.bounds(args) if name == "list_orders" else {}
            except (ValueError, OverflowError, TypeError):
                raise ShopError("INVALID_ARGUMENT", "Arguments do not match the tool contract.") from None
            async with asyncio.timeout(self.deadline):
                data = await self.execute(name, args, bounds)
            data = redact(data, (self.client.settings.key, self.client.settings.secret))
            if not valid(DEFINITIONS[name]["outputSchema"], data):
                raise protocol_error()
            if len(json.dumps(data, ensure_ascii=False).encode()) > 512 * 1024:
                raise ShopError("UPSTREAM_LIMIT_EXCEEDED", "The result exceeds the safe work limit.")
            LOG.info("tool=%s code=OK duration=%.3f request=%s", name, time.monotonic() - started, correlation)
            return envelope(data)
        except TimeoutError:
            message = "The shop tool deadline expired."
            if name in {"create_product", "update_order_status"}:
                message += " The write may have completed; check before retrying."
            return error("UPSTREAM_TIMEOUT", message)
        except ShopError as exc:
            LOG.info("tool=%s code=%s duration=%.3f request=%s", name, exc.code, time.monotonic() - started, correlation)
            return error(exc.code, exc.message)
        except Exception:
            LOG.error("tool=%s code=UPSTREAM_PROTOCOL_ERROR request=%s", name, correlation)
            return error("UPSTREAM_PROTOCOL_ERROR", "The shop returned an invalid response.")

    @staticmethod
    def bounds(args):
        query = {}
        for argument, query_name, direction in (("created_from", "after", -1), ("created_to", "before", 1)):
            if argument in args:
                bound = timestamp(args[argument])
                whole = bound.replace(microsecond=0)
                if direction == 1 and bound.microsecond:
                    whole += timedelta(seconds=1)
                query[query_name] = (whole + timedelta(seconds=direction)).isoformat().replace("+00:00", "Z")
        return query

    async def execute(self, name, args, bounds):
        if name.startswith("list_"):
            return await self.listing(name, args, bounds)
        if name == "create_product":
            body = {key: args[key] for key in ("name", "regular_price", "sku") if key in args}
            body.update(type="simple", status="publish")
            data, _ = await self.client.request("POST", "/products", body=body)
            return {"product": product(data, self.client.settings.currency)}
        method = "PUT" if name == "update_order_status" else "GET"
        data, _ = await self.client.request(method, f"/orders/{args['order_id']}",
                                          body={"status": args["status"]} if method == "PUT" else None)
        return {"order": order(data)}

    async def listing(self, name, args, bounds):
        page, per_page = args.get("page", 1), args.get("per_page", 20)
        offset, matching, found, budget = (page - 1) * per_page, 0, [], [0]
        is_order = name == "list_orders"
        query = {"orderby": "id", "order": "asc", "per_page": 100}
        query.update({key: args[key] for key in (("status",) if is_order else ("search", "sku")) if key in args})
        if is_order:
            query.update(bounds, dates_are_gmt="true")
        lower = timestamp(args["created_from"]) if "created_from" in args else None
        upper = timestamp(args["created_to"]) if "created_to" in args else None
        exhausted = False
        for source_page in range(1, self.max_pages + 1):
            query["page"] = source_page
            data, headers = await self.client.request("GET", "/orders" if is_order else "/products", query=query, budget=budget)
            total = headers.get("X-WP-TotalPages", "")
            if not isinstance(data, list) or len(data) > 100 or not re.fullmatch(r"0|[1-9][0-9]*", total):
                raise protocol_error()
            for source in data:
                item = order(source) if is_order else product(source, self.client.settings.currency)
                # Validate each projection even if a local filter later excludes it.
                item_schema = DEFINITIONS[name]["outputSchema"]["properties"]["items"]["items"]
                if not valid(item_schema, item):
                    raise protocol_error()
                if is_order:
                    created = timestamp(item["date_created"])
                    if (lower and created < lower) or (upper and created > upper):
                        continue
                elif "sku" in args and item["sku"] != args["sku"]:
                    continue
                if matching >= offset:
                    found.append(item)
                matching += 1
                if len(found) == per_page + 1:
                    break
            exhausted = len(data) < 100 or source_page >= int(total)
            if len(found) > per_page or exhausted:
                break
        if not exhausted and len(found) <= per_page:
            raise ShopError("UPSTREAM_LIMIT_EXCEEDED", "The requested page exceeds the safe work limit.")
        return {"items": found[:per_page], "page": page, "per_page": per_page, "has_more": len(found) > per_page}
