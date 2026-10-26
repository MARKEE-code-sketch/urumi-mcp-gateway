"""Disposable REST shop. Never points to or modifies the real M2 store."""
import asyncio
from copy import deepcopy
import json
import math
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from test_oauth import FAKE_KEY, FAKE_SECRET, woocommerce_signature


def product_sample(number=1):
    return {"id": number, "name": f"Mug {number}", "sku": f"SKU-{number}", "price": "299",
            "regular_price": "299", "status": "publish", "permalink": f"http://fake-shop.urumi.test/product/{number}",
            "meta_data": [{"secret": "SENTINEL-CONTACT"}]}


def order_sample(number=1, created="2026-10-14T18:30:00"):
    return {"id": number, "number": str(number), "status": "processing", "currency": "INR", "total": "299",
            "date_created_gmt": created, "billing": {"email": "SENTINEL-CONTACT"},
            "line_items": [{"product_id": 1, "name": "Mug", "sku": "SKU-1", "quantity": 1, "total": "299"}]}


class FakeShop:
    def __init__(self, canonical="http://fake-shop.urumi.test"):
        self.canonical = canonical
        self.products = [product_sample()]
        self.orders = [order_sample()]
        self.observations = []
        self.mode = "healthy"

    async def handle(self, request):
        header = request.headers.get("authorization", "")
        canonical = self.canonical + request.url.path + ("?" + request.url.query if request.url.query else "")
        try:
            expected, actual = woocommerce_signature(request.method, canonical, header)
            signed = expected == actual and 'oauth_consumer_key="' + FAKE_KEY + '"' in header
        except (KeyError, ValueError):
            signed = False
        self.observations.append({"method": request.method, "path": request.url.path,
                                  "query": dict(request.query_params), "signed": signed,
                                  "host": request.headers.get("host")})
        if not signed or self.mode == "auth":
            return JSONResponse({"error": FAKE_SECRET}, status_code=401)
        if self.mode == "forbidden":
            return JSONResponse({"error": FAKE_SECRET}, status_code=403)
        if self.mode == "slow":
            await asyncio.sleep(4)
        if self.mode == "invalid_json":
            return Response("not-json", media_type="application/json")
        if self.mode == "oversize":
            return JSONResponse({"big": "x" * (2 * 1024 * 1024 + 1)})
        if self.mode == "redirect":
            return Response(status_code=302, headers={"Location": "http://untrusted.invalid"})
        if self.mode == "unavailable":
            return JSONResponse({"error": FAKE_SECRET}, status_code=503)
        path = request.url.path.removeprefix("/wp-json/wc/v3/")
        if request.method == "POST" and path == "products":
            body = await request.json()
            self.observations[-1]["body"] = body
            if body.get("sku") and any(item["sku"] == body["sku"] for item in self.products):
                return JSONResponse({"code": "product_invalid_sku", "message": FAKE_SECRET}, status_code=400)
            item = product_sample(max([p["id"] for p in self.products] or [0]) + 1)
            item.update(body, price=body["regular_price"])
            item.setdefault("sku", "")
            if "sku" not in body:
                item["sku"] = ""
            self.products.append(item)
            return JSONResponse(item, status_code=201)
        if path.startswith("orders/"):
            found = next((item for item in self.orders if str(item["id"]) == path.split("/")[1]), None)
            if found is None:
                return JSONResponse({"message": "SENTINEL-CONTACT"}, status_code=404)
            if request.method == "PUT":
                body = await request.json()
                self.observations[-1]["body"] = body
                found.update(body)
            return JSONResponse(deepcopy(found))
        if path not in {"orders", "products"}:
            return JSONResponse({}, status_code=404)
        values = deepcopy(self.orders if path == "orders" else self.products)
        query = request.query_params
        if path == "products":
            if "search" in query:
                values = [item for item in values if query["search"].casefold() in item["name"].casefold()]
            if "sku" in query:
                values = [item for item in values if item["sku"] in query["sku"].split(",")]
        elif "status" in query:
            values = [item for item in values if item["status"] == query["status"]]
        # Deliberately wider-than-requested source date results exercise local filtering.
        page, size = int(query.get("page", 1)), int(query.get("per_page", 100))
        headers = {"X-WP-TotalPages": str(math.ceil(len(values) / size))}
        if self.mode == "invalid_fields" and values:
            values[0]["id"] = True
        if self.mode == "missing_pagination":
            headers = {}
        return JSONResponse(values[(page - 1) * size:page * size], headers=headers)

    def app(self):
        async def health(request):
            return JSONResponse({"status": "fake-only"})
        return Starlette(routes=[Route("/livez", health), Route("/readyz", health),
                                 Route("/wp-json/wc/v3/{path:path}", self.handle, methods=["GET", "POST", "PUT"])])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(FakeShop().app(), host="0.0.0.0", port=8080, access_log=False)
