"""Run M0's independent checks and save a machine-readable report."""
from contextlib import redirect_stderr
import importlib.metadata
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/m0"


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.monotonic()
        self.current_status = "PASS"
        super().startTest(test)

    def addError(self, test, error):
        self.current_status = "FAIL"
        super().addError(test, error)

    def addFailure(self, test, error):
        self.current_status = "FAIL"
        super().addFailure(test, error)

    def addSubTest(self, test, subtest, error):
        if error:
            self.current_status = "FAIL"
        super().addSubTest(test, subtest, error)

    def stopTest(self, test):
        self.records.append({"test": test.id(), "status": self.current_status, "duration_seconds": round(time.monotonic() - self.started, 3)})
        super().stopTest(test)


if __name__ == "__main__":
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/m0"))
    start = time.monotonic()
    with redirect_stderr(output):
        result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=RecordedResult).run(suite)
    from test_protocol import ProtocolChecks
    report = {
        "scope": "M0 fixtures over real localhost HTTP, not the application or Kubernetes",
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "duration_seconds": round(time.monotonic() - start, 3),
        "negotiated_protocol": getattr(ProtocolChecks, "negotiated_protocol", None),
        "versions": {name: importlib.metadata.version(name) for name in ["mcp", "httpx", "jsonschema", "starlette", "uvicorn", "python-dotenv"]},
        "tests": result.records,
        "warnings": [line for line in output.getvalue().splitlines() if "ResourceWarning" in line],
        "not_proven": ["real shop", "gateway authorization/audit", "live Groq model", "Microsoft Learn", "Codex/Inspector client compatibility", "Kubernetes"],
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "unittest-output.txt").write_text(output.getvalue(), encoding="utf-8")
    (EVIDENCE / "test-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"tests", "not_proven"}}, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
