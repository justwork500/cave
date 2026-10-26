from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    config_dir: Path
    session_idle_hours: int = 12
    # first-run seeds only; after that System > Networks (the database) is the source of truth
    local_ranges: list[str] = field(default_factory=list)
    trusted_proxies: list[str] = field(default_factory=list)
