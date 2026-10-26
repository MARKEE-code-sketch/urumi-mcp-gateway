from scripts.m9.package_checks import inspect_docs
from scripts.m9.preflight import ROOT


def test_docs_links_and_required_topics():
    assert len(inspect_docs(ROOT))==5
    operations=(ROOT/'docs/operations.md').read_text().lower()
    for term in ['powershell','linux','backup','restore','rollback','migration','reclaim','m10','binary','secret','namespace','helm history']:
        assert term in operations,term
    readme=(ROOT/'README.md').read_text().lower()
    for term in ['checkout','chat','gateway','key','k3s','https','m10','private']:
        assert term in readme,term
