"""Independent WooCommerce 11.2.1 PHP algorithm translation, fake keys only.

Grounding: class-wc-rest-authentication.php check_oauth_signature,
normalize_parameters/join_with_equals_sign and wc-rest-functions.php
wc_rest_urlencode_rfc3986 at WooCommerce tag 11.2.1.
"""
import base64
import hashlib
import hmac
import re
import unittest
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from services.woocommerce_mcp.woocommerce_client import authorization

FAKE_KEY, FAKE_SECRET = "ck_m3_public_fixture", "cs_m3_public_fixture"


def woocommerce_signature(method, canonical_url, header, secret=FAKE_SECRET):
    # PHP parse_header decodes header fields; PHP $_GET already decoded query once.
    params = dict(parse_qsl(urlsplit(canonical_url).query, keep_blank_values=True))
    params.update({key: unquote(value) for key, value in re.findall(r'(oauth_[a-z_-]+)="([^"]*)"', header)})
    supplied = unquote(params.pop("oauth_signature").replace(" ", "+"))
    enc = lambda value: quote(str(value), safe="~")
    normalized = [(enc(key), enc(value)) for key, value in sorted(params.items())]
    joined = "%26".join(enc(key + "=" + value) for key, value in normalized)
    parsed = urlsplit(canonical_url)
    base = method.upper() + "&" + enc(parsed.scheme + "://" + parsed.netloc + parsed.path) + "&" + joined
    expected = base64.b64encode(hmac.new((secret + "&").encode(), base.encode(), hashlib.sha256).digest()).decode()
    return expected, supplied


class OAuthVectors(unittest.TestCase):
    def test_woocommerce_1121_vectors(self):
        for value in ("plain", "two words", "+", "%20", "%25", "mug & plate", "मराठी", "a+b c%20"):
            from urllib.parse import urlencode
            url = "http://shop.urumi.test/wp-json/wc/v3/products?" + urlencode({"search": value, "page": 1})
            for method in ("GET", "POST", "PUT"):
                with self.subTest(value=value, method=method):
                    header = authorization(method, url, FAKE_KEY, FAKE_SECRET, "a" * 32, 1792022400)
                    expected, supplied = woocommerce_signature(method, url, header)
                    self.assertEqual(expected, supplied)
                    self.assertNotIn("oauth_version", header)
                    self.assertNotIn("oauth_body_hash", header)
                    self.assertNotIn(FAKE_SECRET, header)

    def test_wrong_origin_and_method_rejected(self):
        url = "http://shop.urumi.test/wp-json/wc/v3/products?page=1"
        header = authorization("GET", url, FAKE_KEY, FAKE_SECRET, "a" * 32, 1792022400)
        self.assertNotEqual(*woocommerce_signature("GET", url.replace("shop.urumi.test", "urumi-wordpress.urumi.svc.cluster.local"), header))
        self.assertNotEqual(*woocommerce_signature("PUT", url, header))
