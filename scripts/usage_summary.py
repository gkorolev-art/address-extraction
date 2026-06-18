"""Print a daily summary of the application usage journal."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def summarize(path: Path) -> int:
    if not path.exists():
        print(f"Журнал пока не создан: {path}")
        return 0

    daily: dict[str, Counter[str]] = defaultdict(Counter)
    total = Counter()

    with path.open(encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            day = str(record.get("timestamp", ""))[:10] or "unknown"
            event = str(record.get("event", "unknown"))
            daily[day][event] += 1
            total[event] += 1

    print("Дата        Сессии  Файлы  Обработки  Скачивания  Ошибки")
    for day in sorted(daily):
        counts = daily[day]
        errors = sum(value for key, value in counts.items() if key.endswith("_failed"))
        print(
            f"{day:10}  "
            f"{counts['session_opened']:6}  "
            f"{counts['file_loaded']:5}  "
            f"{counts['processing_completed']:9}  "
            f"{counts['result_downloaded']:10}  "
            f"{errors:6}"
        )

    print(
        "\nИтого: "
        f"сессий {total['session_opened']}, "
        f"файлов {total['file_loaded']}, "
        f"обработок {total['processing_completed']}, "
        f"скачиваний {total['result_downloaded']}"
    )
    return 0


if __name__ == "__main__":
    journal_path = Path(sys.argv[1] if len(sys.argv) > 1 else "logs/usage.jsonl")
    raise SystemExit(summarize(journal_path))

