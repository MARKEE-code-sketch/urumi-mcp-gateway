import importlib.util
from pathlib import Path
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('m9_checker', ROOT / 'scripts/m9/check-m9.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_source_handoff_includes_cluster_https_and_live_helpers():
    files = {p.relative_to(ROOT).as_posix() for p in checker.source_files()}
    assert 'infra/local/k3d.yaml' in files
    assert 'scripts/m10/browser_demo.mjs' in files
    assert 'backend/requirements.in' in files
    assert 'frontend/src/assets/Figtree.ttf' in files
    assert 'frontend/src/assets/urumi-mark.svg' in files
    assert 'frontend/src/assets/icons/plug.svg' in files
    assert not any(p.startswith(('.tools/', '.venv/', 'frontend/node_modules/')) for p in files)


def test_build_negative_uses_missing_entrypoint_staging(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:
        pytest.skip('PowerShell required for actual build-script rejection')
    commands = []
    staging = tmp_path / 'negative'
    result = checker.check_missing_entrypoints(shell, staging, commands)
    assert result.returncode != 0
    assert 'M10_BACKEND_ENTRYPOINT_MISSING' in result.stdout + result.stderr
    assert not (staging / 'backend').exists()
    expected = str(staging.relative_to(ROOT)) if staging.is_relative_to(ROOT) else 'source-only staging'
    assert commands[0]['cwd'] == expected


def test_historical_runtime_changes_are_observations(tmp_path, monkeypatch):
    (tmp_path / 'docs/evidence/m6').mkdir(parents=True)
    (tmp_path / 'docs/evidence/m6/image-source-check.json').write_text(
        '{"sha256":{"changed.py":"old","missing.py":"old"}}')
    (tmp_path / 'changed.py').write_text('updated integration code')
    monkeypatch.setattr(checker, 'ROOT', tmp_path)
    result = checker.historical_runtime_comparison()
    assert result['status'] == 'HISTORICAL_COMPARISON_ONLY'
    assert result['different_files'] == ['changed.py']
    assert result['missing_files'] == ['missing.py']
