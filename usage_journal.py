"""Persistent privacy-conscious usage journal for the Streamlit app."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class UsageJournal:
    """Writes compact JSON events to a rotating log file."""

    def __init__(
        self,
        log_path: str | Path = "logs/usage.jsonl",
        *,
        max_bytes: int = 5 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        logger_name = f"usage_journal:{self.log_path.resolve()}"
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = RotatingFileHandler(
                self.log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def write(
        self,
        event: str,
        *,
        session_id: str,
        app_version: str,
        **details: Any,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "session_id": session_id,
            "app_version": app_version,
            **details,
        }
        self._logger.info(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
        )

