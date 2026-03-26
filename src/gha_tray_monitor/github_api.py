from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

from .models import BuildConfig, BuildState, BuildStatus

WORKFLOW_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/workflows/(?P<workflow>[^/?#]+)"
)

FAILED_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "startup_failure",
    "action_required",
    "stale",
}


@dataclass(slots=True)
class ParsedWorkflow:
    owner: str
    repo: str
    workflow: str


def parse_workflow_url(url: str) -> ParsedWorkflow:
    match = WORKFLOW_URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"Unsupported workflow URL: {url}")

    return ParsedWorkflow(
        owner=match.group("owner"),
        repo=match.group("repo"),
        workflow=match.group("workflow"),
    )


class GitHubClient:
    def __init__(self, token_env_name: str = "GITHUB_TOKEN", timeout_seconds: float = 10.0) -> None:
        token = os.getenv(token_env_name)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "gha-tray-monitor",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def latest_status(self, build: BuildConfig) -> BuildStatus:
        try:
            workflow = parse_workflow_url(build.url)
            params: dict[str, str | int] = {"per_page": 1}
            if build.branch:
                params["branch"] = build.branch

            response = self._client.get(
                f"/repos/{workflow.owner}/{workflow.repo}/actions/workflows/{workflow.workflow}/runs",
                params=params,
            )

            if response.status_code >= 400:
                return BuildStatus(
                    config=build,
                    state=BuildState.UNKNOWN,
                    summary=f"HTTP {response.status_code} from GitHub API",
                    details_url=build.url,
                    updated_at=None,
                )

            payload = response.json()
            runs = payload.get("workflow_runs", [])
            if not runs:
                return BuildStatus(
                    config=build,
                    state=BuildState.UNKNOWN,
                    summary="No workflow runs found",
                    details_url=build.url,
                    updated_at=None,
                )

            run = runs[0]
            status = str(run.get("status", "unknown"))
            conclusion = str(run.get("conclusion") or "")
            html_url = str(run.get("html_url") or build.url)
            updated_at = run.get("updated_at")

            if status != "completed":
                return BuildStatus(
                    config=build,
                    state=BuildState.RUNNING,
                    summary=f"{status}",
                    details_url=html_url,
                    updated_at=updated_at,
                )

            if conclusion == "success":
                state = BuildState.SUCCESS
                summary = "success"
            elif conclusion in FAILED_CONCLUSIONS:
                state = BuildState.FAILED
                summary = conclusion
            else:
                state = BuildState.UNKNOWN
                summary = conclusion or "completed"

            return BuildStatus(
                config=build,
                state=state,
                summary=summary,
                details_url=html_url,
                updated_at=updated_at,
            )

        except Exception as exc:
            return BuildStatus(
                config=build,
                state=BuildState.UNKNOWN,
                summary=f"Error: {exc}",
                details_url=build.url,
                updated_at=None,
            )

