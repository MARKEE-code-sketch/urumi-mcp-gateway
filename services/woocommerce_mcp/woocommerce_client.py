"""Fixed-destination, bounded REST transport; credentials never enter tool arguments."""
from dataclasses import dataclass, field
import json
import logging
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from oauthlib.oauth1 import Client, SIGNATURE_HMAC_SHA256, SIGNATURE_TYPE_AUTH_HEADER

logging.getLogger("oauthlib").disabled = True
logging.getLogger("oauthlib.oauth1.rfc5849").disabled = True
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class ShopError(Exception):
    def __init__(self, code, message):
        super().__init__(code)
        self.code, self.message = code, message


def protocol_error():
    return ShopError("UPSTREAM_PROTOCOL_ERROR", "The shop returned an invalid response.")


class WooOAuthClient(Client):
    def get_oauth_params(self, request):
        return [(key, value) for key, value in super().get_oauth_params(request) if key != "oauth_version"]


def authorization(method, canonical_url, key, secret, nonce=None, now=None):
    client = WooOAuthClient(key, client_secret=secret, signature_method=SIGNATURE_HMAC_SHA256,
                            signature_type=SIGNATURE_TYPE_AUTH_HEADER,
                            nonce=nonce or secrets.token_hex(16), timestamp=str(int(time.time()) if now is None else now))
    return client.sign(canonical_url, http_method=method, body=None)[1]["Authorization"]


def origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("Invalid configured shop origin")
    parsed.port  # Validate port before accepting configuration.
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    canonical: str
    transport: str
    key: str = field(repr=False)
    secret: str = field(repr=False)
    currency: str = "INR"
    allowed_hosts: tuple = ("localhost", "127.0.0.1")

    def __post_init__(self):
        object.__setattr__(self, "canonical", origin(self.canonical))
        object.__setattr__(self, "transport", origin(self.transport))
        if (not self.key or not self.secret or any(c in self.key + self.secret for c in "\r\n")
                or self.currency != "INR" or not self.allowed_hosts):
            raise ValueError("Invalid local configuration")

    @classmethod
    def from_env(cls):
        return cls(os.environ["WOO_CANONICAL_ORIGIN"], os.environ["WOO_TRANSPORT_ORIGIN"],
                   os.environ["WOO_CONSUMER_KEY"], os.environ["WOO_CONSUMER_SECRET"],
                   os.environ.get("WOO_CURRENCY", "INR"),
                   tuple(os.environ["MCP_ALLOWED_HOSTS"].split(",")))


class WooCommerceClient:
    def __init__(self, settings, http):
        self.settings, self.http = settings, http

    async def request(self, method, path, query=None, body=None, budget=None):
        suffix = "/wp-json/wc/v3" + path
        if query:
            suffix += "?" + urlencode(sorted(query.items()))
        header = authorization(method, self.settings.canonical + suffix, self.settings.key, self.settings.secret)
        headers = {"Authorization": header, "Host": urlsplit(self.settings.canonical).netloc,
                   "Accept": "application/json"}
        write = method in {"POST", "PUT"}
        try:
            async with self.http.stream(method, self.settings.transport + suffix, headers=headers, json=body,
                                        follow_redirects=False, timeout=httpx.Timeout(3, connect=1, pool=1)) as response:
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if budget is not None:
                        budget[0] += len(chunk)
                    if size > 2 * 1024 * 1024 or (budget and budget[0] > 8 * 1024 * 1024):
                        raise ShopError("UPSTREAM_LIMIT_EXCEEDED", "The shop response exceeds the safe work limit.")
                    chunks.append(chunk)
                if response.status_code in {401, 403}:
                    raise ShopError("UPSTREAM_AUTH_FAILED", "The shop rejected its configured credential.")
                if response.status_code == 404 and path.startswith("/orders/"):
                    raise ShopError("ORDER_NOT_FOUND", "The order was not found.")
                if response.status_code >= 500:
                    raise ShopError("UPSTREAM_UNAVAILABLE", "The shop is unavailable.")
                if 300 <= response.status_code < 400:
                    raise protocol_error()
                try:
                    data = json.loads(b"".join(chunks))
                except (ValueError, UnicodeError):
                    raise protocol_error() from None
                if response.status_code >= 400:
                    if isinstance(data, dict) and data.get("code") in {"product_invalid_sku", "woocommerce_rest_product_invalid_sku"}:
                        raise ShopError("PRODUCT_SKU_CONFLICT", "The SKU is already in use or invalid.")
                    raise ShopError("UPSTREAM_REJECTED", "The shop rejected the requested action.")
                if response.status_code not in {200, 201}:
                    raise protocol_error()
                return data, response.headers
        except httpx.TimeoutException:
            raise ShopError("UPSTREAM_TIMEOUT", "The shop timed out." + (" The write may have completed; check before retrying." if write else "")) from None
        except httpx.RequestError:
            raise ShopError("UPSTREAM_UNAVAILABLE", "The shop could not be reached." + (" The write may have completed; check before retrying." if write else "")) from None
