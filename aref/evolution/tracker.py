"""
Action Item Tracker — Blueprint Section 3.5.2.

Tracks post-incident action items to completion.
Target: > 85% completion rate, > 8 actions/quarter.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from aref.core.metrics import ACTION_ITEMS_COMPLETED
from aref.core.models import ActionItem

logger = structlog.get_logger(__name__)


class ActionTracker:
    """Tracks action items from post-incident reviews."""

    def __init__(self) -> None:
        self._items: dict[str, ActionItem] = {}
        self._quarter_start: float = time.time()

    def add(self, item: ActionItem) -> None:
        self._items[item.action_id] = item
        logger.info("action_tracker.added", action_id=item.action_id, title=item.title)

    def complete(self, action_id: str) -> bool:
        item = self._items.get(action_id)
        if not item or item.status == "completed":
            return False
        item.status = "completed"
        item.completed_at = time.time()
        ACTION_ITEMS_COMPLETED.inc()
        logger.info("action_tracker.completed", action_id=action_id)
        return True

    def get_open_items(self) -> list[ActionItem]:
        return [i for i in self._items.values() if i.status == "open"]

    def get_overdue_items(self) -> list[ActionItem]:
        return [i for i in self._items.values() if i.is_overdue]

    def get_by_pillar(self, pillar: str) -> list[ActionItem]:
        return [i for i in self._items.values() if i.pillar == pillar]

    def get_stats(self) -> dict[str, Any]:
        total = len(self._items)
        completed = sum(1 for i in self._items.values() if i.status == "completed")
        overdue = len(self.get_overdue_items())

        # Quarter calculation
        now = time.time()
        quarter_seconds = 90 * 86400  # ~90 days
        completed_this_quarter = sum(
            1 for i in self._items.values()
            if i.status == "completed"
            and i.completed_at
            and i.completed_at >= self._quarter_start
        )

        return {
            "total": total,
            "open": total - completed,
            "completed": completed,
            "overdue": overdue,
            "completion_rate": round((completed / total * 100) if total > 0 else 0, 1),
            "completed_this_quarter": completed_this_quarter,
            "by_pillar": {
                pillar: len(self.get_by_pillar(pillar))
                for pillar in ["detection", "absorption", "adaptation", "recovery", "evolution"]
            },
        }
