"""Temporary in-cluster caller; never a production gateway."""
import argparse
import asyncio
import json
import socket
from urllib.parse import urlsplit

from scripts.m4.probe import probe


def denied(url):
    parsed = urlsplit(url)
    address = socket.gethostbyname(parsed.hostname)
    try:
        with socket.create_connection((address, parsed.port), timeout=3):
            raise AssertionError("Unrelated Pod reached Inventory.")
    except (TimeoutError, ConnectionRefusedError) as error:
        print(json.dumps({"status": "PASS", "mode": "denied", "dns_resolved": True, "exception": type(error).__name__}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--mode", choices=["allowed", "denied", "hosted"], required=True)
    options = parser.parse_args()
    if options.mode == "denied":
        denied(options.url)
    else:
        result = asyncio.run(probe(options.url, hosted=options.mode == "hosted"))
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["status"] == "PASS" else 1)
