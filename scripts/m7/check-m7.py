"""Run isolated M7 checks. A live probe contacts only Groq and a fake gateway."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.chat.agent import ChatAgent
from backend.chat.llm_client import GroqClient
from scripts.m7.fixtures import GatewayFixture, IdentityFixture

EVIDENCE = ROOT / 'docs/evidence/m7'


def save(name, data):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


async def live_probe(key):
    identity = IdentityFixture()
    gateway = GatewayFixture(identity)
    # One advertised fixture tool; no registry/database/store/network upstream.
    gateway.tools = [tool for tool in gateway.tools if tool['upstream_name'] == 'lookup_sku']
    class ProbeProvider(GroqClient):
        def __init__(self, key):
            super().__init__(key)
            self.requested, self.rounds = [], 0

        async def complete(self, messages, tools, final=False):
            self.rounds += 1
            response = await super().complete(messages, tools, final)
            for call in response.get('tool_calls') or []:
                function = call.get('function', {})
                self.requested.append({'provider_call_id': str(call.get('id', ''))[:128],
                                       'tool_name': str(function.get('name', ''))[:64]})
            return response
    provider = ProbeProvider(key)
    started = time.monotonic()
    try:
        agent = ChatAgent(provider, gateway, identity)
        reply = await agent.run(identity.a,
            'Use inventory__lookup_sku for DEMO-001. Tell me the SAMPLE warehouse name and quantity from its result.')
        valid = (reply['state'] == 'completed' and len(gateway.calls) == 1 and
                 gateway.calls[0][1:] == ('inventory__lookup_sku', {'sku': 'DEMO-001'}) and
                 'bengaluru' in reply['answer'].lower() and '12' in reply['answer'] and
                 'sample' in reply['answer'].lower() and len(reply['tool_calls']) == 1 and
                 reply['tool_calls'][0]['outcome'] == 'success')
        artifact = {'status': 'PASS' if valid else 'FAIL', 'provider': 'groq', 'model': provider.model,
                    'account_free_access_confirmed_by_operator': True,
                    'duration_seconds': round(time.monotonic() - started, 3),
                    'boundary': 'Real provider; fake identity and fake gateway only; no MCP/shop calls.',
                    'expected_call': {'tool_name': 'inventory__lookup_sku', 'arguments': {'sku': 'DEMO-001'}},
                    'actual_calls': [{'tool_name': call[1], 'arguments': call[2]} for call in gateway.calls],
                    'provider_requested_calls': provider.requested, 'provider_rounds': provider.rounds,
                    'reply': reply}
        if reply['state'] != 'completed' and not gateway.calls:
            artifact['status'] = 'BLOCKED'
        serialized = json.dumps(artifact)
        if key and key in serialized:
            return {'status': 'FAIL', 'reason_code': 'EVIDENCE_REDACTION_FAILED'}
        return artifact
    finally:
        await provider.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-provider', action='store_true')
    parser.add_argument('--confirm-free-plan', action='store_true')
    args = parser.parse_args()
    command = [sys.executable, '-m', 'pytest', 'tests/chat', '-q', '--assert=plain', '-p', 'no:cacheprovider']
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'unit-output.txt').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    offline = {'status': 'PASS' if completed.returncode == 0 else 'FAIL',
               'command': [Path(sys.executable).name] + command[1:], 'returncode': completed.returncode,
               'boundary': 'Deterministic tests and loopback TCP/ASGI; no hosted-provider calls.'}
    save('unit-results.json', offline)
    print(json.dumps(offline))
    if completed.returncode:
        return 1
    if not args.live_provider:
        return 0
    if not args.confirm_free_plan:
        result = {'status': 'BLOCKED', 'reason_code': 'FREE_PLAN_NOT_CONFIRMED'}
    else:
        key = os.environ.get('GROQ_API_KEY')
        if not key:
            from dotenv import dotenv_values
            key = dotenv_values(ROOT / '.env').get('GROQ_API_KEY')
        if not key:
            result = {'status': 'BLOCKED', 'reason_code': 'MISSING_GROQ_API_KEY'}
        else:
            try:
                result = asyncio.run(live_probe(key))
            except Exception:
                result = {'status': 'BLOCKED', 'reason_code': 'LIVE_PROBE_UNAVAILABLE'}
    save('provider-probe.json', result)
    print(json.dumps({key: value for key, value in result.items() if key not in ('reply', 'actual_calls')}))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
