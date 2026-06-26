import logging

import httpx

from app.core.config import settings
from app.engine.nodes.base import BaseNodeExecutor
from app.engine.variables import interpolate

logger = logging.getLogger(__name__)


class EscalationNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        recipient_email = interpolate(config.get("recipient_email", ""), variables)
        message_template = config.get("message_template", config.get("message", ""))
        message = interpolate(message_template, variables)
        subject = interpolate(
            config.get("subject", "Escalation Alert - AUTOMIND"), variables
        )

        if not recipient_email:
            return {
                "escalation_sent": False,
                "error": "No escalation recipient specified",
            }

        if not settings.RESEND_API_KEY:
            logger.info("RESEND_API_KEY not set - returning mock escalation result")
            return {
                "escalation_sent": True,
                "recipient": recipient_email,
                "mock": True,
                "subject": subject,
                "message": message,
            }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": "automind@resend.dev",
                        "to": [recipient_email],
                        "subject": subject,
                        "html": message,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            return {
                "escalation_sent": True,
                "recipient": recipient_email,
                "resend_id": data.get("id"),
                "subject": subject,
            }
        except Exception as exc:
            logger.exception("Escalation email error")
            return {
                "escalation_sent": False,
                "recipient": recipient_email,
                "error": str(exc),
            }
