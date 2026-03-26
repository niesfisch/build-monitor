from gha_tray_monitor.github_api import parse_workflow_url


def test_parse_workflow_url() -> None:
    parsed = parse_workflow_url("https://github.com/acme/api/actions/workflows/ci.yml")

    assert parsed.owner == "acme"
    assert parsed.repo == "api"
    assert parsed.workflow == "ci.yml"

