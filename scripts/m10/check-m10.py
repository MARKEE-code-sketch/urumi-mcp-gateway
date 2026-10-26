"""Run controlled composition checks or an explicit read-only target inventory."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.target import inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['controlled', 'inventory'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context')
    parser.add_argument('--kubeconfig', type=Path)
    parser.add_argument('--namespace')
    parser.add_argument('--release')
    args = parser.parse_args()
    out = args.output.resolve()
    evidence = ROOT / 'docs/evidence/m10'
    if not (out.is_relative_to(evidence) or out.is_relative_to(ROOT / '.tools/m10')):
        parser.error('Output must be inside docs/evidence/m10 or .tools/m10.')
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == 'inventory':
        if not all([args.context, args.kubeconfig, args.namespace, args.release]):
            parser.error('Inventory requires explicit context, kubeconfig, namespace and release.')
        try:
            result = inventory(args.context, args.kubeconfig, args.namespace, args.release)
        except (ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
            parser.exit(1, 'Inventory failed validation or scoped read; no raw diagnostics were saved.\n')
        (out / 'runtime-inventory.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print('Read-only inventory recorded; no acceptance verdict assigned.')
        return 0

    # tests/backend uses the historical M5 database and truncates it. Never include it here.
    command = [sys.executable, '-m', 'pytest', 'tests/e2e', 'tests/gateway', 'tests/chat',
               '-q', '-p', 'no:cacheprovider', '--basetemp', str(ROOT / '.tools/m10/pytest-controlled'),
               '--junitxml', str(out / 'controlled-tests.xml')]
    child_environment = dict(os.environ)
    child_environment.pop('URUMI_M10_TEST_DSN', None)
    completed = subprocess.run(command, cwd=ROOT, env=child_environment, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
    (out / 'controlled-tests.txt').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    result = {'status': 'PASS_CONTROLLED_ONLY' if completed.returncode == 0 else 'FAIL',
              'checked_at': datetime.now(timezone.utc).isoformat(), 'command': command,
              'exit_code': completed.returncode,
              'scope': 'Controlled Python contracts only; no live database/cluster/provider/browser proof.',
              'excluded': 'tests/backend historical database fixtures are not executed.',
              'live_acceptance': [{'id': f'C10-{n:02}', 'status': 'NOT RUN',
                                   'reason': 'Real target and scenario evidence required.'} for n in range(1, 19)]}
    (out / 'controlled-results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(result['status'])
    return int(completed.returncode != 0)


if __name__ == '__main__':
    raise SystemExit(main())
