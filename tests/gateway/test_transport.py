import asyncio
from datetime import datetime, timedelta, timezone
import ipaddress
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpcore
import httpx
import pytest

from backend.gateway.common import GatewayError
from backend.gateway.upstream_client import Budget, CheckedBackend, CheckedTransport, LimitedStream, UpstreamClient, depth
from scripts.m6.fixtures import fixture_app
from tests.gateway.helpers import LocalServer


class Answers:
    def __init__(self, addresses):
        self.values = addresses
    def addresses(self):
        return self.values


class Resolver:
    def __init__(self, addresses):
        self.addresses, self.calls = addresses, 0
    async def resolve_name(self, *args, **kwargs):
        self.calls += 1
        return Answers(self.addresses)


class Backend:
    def __init__(self):
        self.hosts = []
    async def connect_tcp(self, host, port, **kwargs):
        self.hosts.append(host)
        return object()


@pytest.mark.parametrize('addresses', [['169.254.169.254'], ['8.8.8.8', '127.0.0.1'], ['::1'], ['10.0.0.1']])
def test_all_dns_answers_checked_before_dial(addresses):
    async def check():
        backend = Backend()
        checked = CheckedBackend('https://public.example.test/mcp', set(), Resolver(addresses), backend)
        with pytest.raises(GatewayError):
            await checked.connect_tcp('public.example.test', 443)
        assert backend.hosts == []
    asyncio.run(check())


def test_numeric_checked_dial_no_second_resolution_and_exact_host():
    async def check():
        backend, resolver = Backend(), Resolver(['8.8.8.8'])
        checked = CheckedBackend('https://public.example.test/mcp', set(), resolver, backend)
        await checked.connect_tcp('public.example.test', 443)
        assert resolver.calls == 1 and backend.hosts == ['8.8.8.8']
        with pytest.raises(GatewayError):
            await checked.connect_tcp('metadata.google.internal', 443)
        resolver.addresses = ['127.0.0.1']
        with pytest.raises(GatewayError):
            await checked.connect_tcp('public.example.test', 443)
        assert backend.hosts == ['8.8.8.8']
    asyncio.run(check())


def test_real_tls_numeric_dial_preserves_hostname_and_rejects_wrong_name(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fixture.example.test')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
        .not_valid_after(now+timedelta(days=1)).add_extension(x509.SubjectAlternativeName([
            x509.DNSName('fixture.example.test')]), critical=False).sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path/'cert.pem', tmp_path/'key.pem'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    server = LocalServer(fixture_app(), ssl_certfile=str(cert_path), ssl_keyfile=str(key_path))
    port = server.url.rsplit(':', 1)[1]
    try:
        async def check():
            good = 'https://fixture.example.test:' + port + '/mcp'
            bad = 'https://wrong.example.test:' + port + '/mcp'
            context = ssl.create_default_context(cafile=str(cert_path))
            upstream = UpstreamClient([good, bad], Resolver(['127.0.0.1']), context)
            row = dict(url=good, auth_type='none')
            async with asyncio.timeout(3):
                tools = await upstream.discover(row, None)
            assert len(tools) == 2
            with pytest.raises(Exception):
                async with asyncio.timeout(3):
                    await upstream.discover(dict(row, url=bad), None)
        asyncio.run(check())
    finally:
        server.close()


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize('chunks,sse', [([b'x'*(2*1024**2+1)], False),
    ([b'data: '+b'x'*150000+b'\n', b'data: '+b'x'*150000+b'\n\n'], True),
    ([b'data: '+b'x'*262145+b'\n\n'], True)])
def test_incremental_byte_and_multiline_event_limits(chunks, sse):
    async def check():
        stream = LimitedStream(Chunks(chunks), Budget(), sse)
        with pytest.raises(GatewayError):
            async for _ in stream:
                pass
        await stream.aclose()
        assert stream.stream.closed
    asyncio.run(check())


@pytest.mark.parametrize('response', [b'HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/\r\nContent-Length: 0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n'])
def test_redirect_and_compressed_response_rejected(response):
    async def check():
        url = 'https://public.example.test/mcp'
        transport = CheckedTransport(url, [], Budget())
        await transport.pool.aclose()
        transport.pool = httpcore.AsyncConnectionPool(network_backend=httpcore.AsyncMockBackend([response]))
        with pytest.raises(GatewayError):
            async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
                await client.post(url, json={})
    asyncio.run(check())


def test_remote_refs_and_excessive_depth_rejected_without_fetch():
    with pytest.raises(GatewayError):
        depth({'$ref': 'http://169.254.169.254/'})
    item = {}
    for _ in range(34):
        item = {'x': item}
    with pytest.raises(GatewayError):
        depth(item)
