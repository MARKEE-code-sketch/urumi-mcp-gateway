"""Scan handoff files for known private values without printing those values."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values


def main():
    spec = importlib.util.spec_from_file_location('package_checker', ROOT / 'scripts/m9/check-m9.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    values = set()
    def collect(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, (dict, list)):
                    collect(value)
                elif isinstance(value, str) and len(value) >= 12 and (
                    'password' in key.lower() or key.lower() in
                    {'consumer_key', 'consumer_secret', 'raw_key', 'invite_url', 'token', 'api_key'}
                    or key in {'AUTH_KEY', 'SECURE_AUTH_KEY', 'LOGGED_IN_KEY', 'NONCE_KEY',
                               'AUTH_SALT', 'SECURE_AUTH_SALT', 'LOGGED_IN_SALT', 'NONCE_SALT'}):
                    values.add(value)
        elif isinstance(item, list):
            for value in item:
                collect(value)
    for name in ('access.json', 'live-config.json', 'external-key.json', 'browser-qa.json'):
        path = ROOT / '.tools/operator/m10' / name
        if path.is_file():
            collect(json.loads(path.read_text(encoding='utf-8-sig')))
    clean_access = ROOT / '.tools/operator/m10-clean/access.json'
    if clean_access.is_file():
        collect(json.loads(clean_access.read_text(encoding='utf-8-sig')))
    for key, value in dotenv_values(ROOT / '.env').items():
        if value and any(word in key.upper() for word in ('KEY', 'PASSWORD', 'SECRET', 'TOKEN')):
            values.add(value)
    for name in ('ca-key.pem', 'tls.key'):
        values.add((ROOT / '.tools/operator/m10/tls' / name).read_text().strip())
    clean_key = ROOT / '.tools/operator/m10-clean/tls.key'
    if clean_key.is_file():
        values.add(clean_key.read_text().strip())
    source = checker.source_files()
    evidence = [p for p in (ROOT / 'docs/evidence').rglob('*') if p.is_file()]
    matches = []
    for path in source + evidence:
        contents = path.read_bytes()
        if any(value.encode(encoding) in contents for value in values
               for encoding in ('utf-8', 'utf-16-le', 'utf-16-be')):
            matches.append(path.relative_to(ROOT).as_posix())
    frozen = json.loads((ROOT / 'docs/evidence/m10/image-source-inputs.json').read_text())['sha256']
    changed = [name for name, digest in frozen.items()
               if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    result = {'status': 'PASS' if not matches and not changed else 'FAIL',
        'source_files_checked': len(source), 'evidence_files_checked': len(evidence),
        'known_private_sentinels_checked': len(values), 'matches': len(matches),
        'matched_files': matches, 'source_freeze_files_unchanged': len(frozen) - len(changed),
        'changed_runtime_source': changed,
        'scope': 'Source allowlist and all evidence; known UTF8/UTF16 values only. Screenshots separately visually reviewed; unknown-secret absence is not guaranteed.'}
    (ROOT / 'docs/evidence/m10/final-artifact-scan.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
