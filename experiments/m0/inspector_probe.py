"""Check an already-installed Inspector CLI against the disposable M0 server."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/m0"))
from test_protocol import LocalFixture, FIXTURE_KEY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspector-cli", type=Path, required=True, help="Installed inspector/cli/build/index.js path")
    parser.add_argument("--node", default="node", help="Node executable, if it is not on PATH")
    args = parser.parse_args()
    checks = []
    with LocalFixture() as server:
        base = [args.node, str(args.inspector_cli), server.url, "--transport", "http"]
        for method in ("tools/list", "tools/call"):
            command = base + ["--method", method, "--header", f"Authorization: Bearer {FIXTURE_KEY}"]
            if method == "tools/call":
                command += ["--tool-name", "lookup_sku", "--tool-arg", "sku=DEMO-001"]
            try:
                process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=8)
            except subprocess.TimeoutExpired:
                checks.append({"method": method, "status": "BLOCKED", "exit_code": None, "reason": "CLI_STARTUP_OR_CALL_TIMEOUT", "result": {}, "stderr": "Inspector did not finish within eight seconds."})
                continue
            try:
                result = json.loads(process.stdout)
                passed = process.returncode == 0 and (bool(result.get("tools")) if method == "tools/list" else result.get("structuredContent", {}).get("found") is True and result.get("isError") is False)
            except json.JSONDecodeError:
                result, passed = {}, False
            checks.append({"method": method, "status": "PASS" if passed else "FAIL", "exit_code": process.returncode, "result": result, "stderr": process.stderr.replace(FIXTURE_KEY, "[fixture-key]")})
    report = {"scope": "Inspector CLI against M0 sample server, not dashboard/gateway or a visual Inspector demo", "version": json.loads((args.inspector_cli.parents[2] / "package.json").read_text(encoding="utf-8"))["version"], "checks": checks}
    (ROOT / "docs/evidence/m0/inspector-probe.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": [{"method": c["method"], "status": c["status"], "exit_code": c["exit_code"], "stderr": c["stderr"]} for c in checks]}, indent=2))
    return 0 if all(c["status"] == "PASS" for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
