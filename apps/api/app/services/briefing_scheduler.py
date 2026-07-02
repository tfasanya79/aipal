"""Background scheduler for triggered briefings (morning, evening, check-ins)."""

import asyncio
import logging
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

log = logging.getLogger("aipal.briefing_scheduler")


class BriefingScheduler:
    """Simple async scheduler for user-set briefing times."""

    def __init__(self):
        self.tasks: dict[str, asyncio.Task] = {}
        self.callbacks: dict[str, Callable] = {}

    def register_callback(self, event_type: str, callback: Callable) -> None:
        """Register a callback for a briefing event (morning|evening|checkin)."""
        self.callbacks[event_type] = callback

    async def schedule_briefing_for_user(
        self,
        user_id: str,
        event_type: str,  # "morning" | "evening" | "checkin"
        scheduled_time: str | None,  # HH:MM format
        timezone: str,
    ) -> None:
        """Schedule a briefing to fire at a user's preferred time.
        
        For now, this is a single-session scheduler. In production, use APScheduler or Celery.
        """
        if not scheduled_time or event_type not in self.callbacks:
            return

        task_key = f"{user_id}:{event_type}"
        
        # Cancel existing scheduled task
        if task_key in self.tasks:
            self.tasks[task_key].cancel()
        
        # Schedule new task
        try:
            tz = ZoneInfo(timezone or "UTC")
        except Exception:
            tz = ZoneInfo("UTC")
        
        async def _run_briefing():
            while True:
                try:
                    now = datetime.now(tz)
                    scheduled_hour, scheduled_min = map(int, scheduled_time.split(":"))
                    target = now.replace(hour=scheduled_hour, minute=scheduled_min, second=0, microsecond=0)
                    
                    # If target time has passed today, schedule for tomorrow
                    if target <= now:
                        from datetime import timedelta
                        target = target + timedelta(days=1)
                    
                    wait_seconds = (target - now).total_seconds()
                    log.info(f"Briefing scheduled for {user_id} ({event_type}) in {wait_seconds:.0f}s")
                    
                    await asyncio.sleep(wait_seconds)
                    callback = self.callbacks.get(event_type)
                    if callback:
                        await callback(user_id, event_type)
                    
                    # Reschedule for next day
                    await asyncio.sleep(1)  # Prevent busy loop
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Briefing task error for {user_id}: {e}")
                    await asyncio.sleep(60)  # Retry after 1 minute
        
        task = asyncio.create_task(_run_briefing())
        self.tasks[task_key] = task

    async def cancel_briefing(self, user_id: str, event_type: str) -> None:
        """Cancel a scheduled briefing."""
        task_key = f"{user_id}:{event_type}"
        if task_key in self.tasks:
            self.tasks[task_key].cancel()
            del self.tasks[task_key]


# Global scheduler instance
_scheduler = BriefingScheduler()


async def get_scheduler() -> BriefingScheduler:
    """Get the global briefing scheduler."""
    return _scheduler
