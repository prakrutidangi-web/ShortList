import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from shortlist_ml.ingest.sources import SOURCES

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class CompanyConfig:
    name: str
    ats: str
    board_token: str


def load_companies(path: Path) -> list[CompanyConfig]:
    return parse_companies(yaml.safe_load(path.read_text()) or [], path)


def parse_companies(data: object, path: Path) -> list[CompanyConfig]:
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a YAML list")
    out: list[CompanyConfig] = []
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(data):
        try:
            cfg = CompanyConfig(str(row["name"]), str(row["ats"]), str(row["board_token"]))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"{path}: entry {i} needs name, ats, board_token") from exc
        if cfg.ats not in SOURCES:
            raise ValueError(f"{path}: entry {i} ({cfg.name}): unsupported ats {cfg.ats!r}")
        if not _TOKEN_RE.match(cfg.board_token):
            raise ValueError(
                f"{path}: entry {i} ({cfg.name}): invalid board_token {cfg.board_token!r}"
            )
        if (cfg.ats, cfg.board_token) in seen:
            raise ValueError(f"{path}: duplicate board {cfg.ats}/{cfg.board_token}")
        seen.add((cfg.ats, cfg.board_token))
        out.append(cfg)
    return out
