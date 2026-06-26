from datetime import datetime, timezone

from app.engine.nodes.base import BaseNodeExecutor


class TriggerNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        """Set initial trigger variables and pass through."""
        return {
            "trigger_time": datetime.now(timezone.utc).isoformat(),
            "triggered_by": kwargs.get("triggered_by", "manual"),
        }
