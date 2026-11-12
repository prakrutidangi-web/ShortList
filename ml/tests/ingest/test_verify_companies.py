from collections.abc import Callable
from pathlib import Path

import httpx
import yaml

from shortlist_ml.ingest.http import Fetcher
from shortlist_ml.ingest.verify_companies import verify_all


def test_only_boards_with_200_and_jobs_are_kept(
    tmp_path: Path, fetcher_for: Callable[..., Fetcher]
) -> None:
    cand = tmp_path / "cand.yaml"
    cand.write_text(
        "- {name: Good GH, ats: greenhouse, board_token: good}\n"
        "- {name: Missing, ats: greenhouse, board_token: missing}\n"
        "- {name: Empty, ats: lever, board_token: empty}\n"
        "- {name: Good Lever, ats: lever, board_token: lgood}\n"
        "- {name: Weird, ats: lever, board_token: weird}\n"
        "- {name: BigTech, ats: custom, note: own careers site}\n"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if "/missing/" in path:
            return httpx.Response(404)
        if path.endswith("/empty"):
            return httpx.Response(200, json=[])
        if path.endswith("/weird"):
            return httpx.Response(200, json={"unexpected": True})
        if "boards-api" in req.url.host:
            assert "content=true" not in str(req.url)  # verification stays light
            return httpx.Response(200, json={"jobs": [{"id": 1}]})
        return httpx.Response(200, json=[{"id": "x"}, {"id": "y"}])

    out, report = tmp_path / "companies.yaml", tmp_path / "report.md"
    results = verify_all(cand, out, report, fetcher_for(handler))
    assert [r.ok for r in results] == [True, False, False, True, False]
    kept = yaml.safe_load(out.read_text())
    assert kept == [
        {"name": "Good GH", "ats": "greenhouse", "board_token": "good"},
        {"name": "Good Lever", "ats": "lever", "board_token": "lgood"},
    ]
    text = report.read_text()
    assert "2 of 5 candidates verified" in text
    assert "BigTech | custom | own careers site" in text and "Not attempted" in text
    assert "FAILED: HTTP 404" in text and "zero jobs" in text and "unexpected JSON shape" in text
