import logging

import httpx

from app.core.config import settings
from app.engine.nodes.base import BaseNodeExecutor
from app.engine.variables import interpolate

logger = logging.getLogger(__name__)


class IntegrationNodeExecutor(BaseNodeExecutor):
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        service = config.get("service", "email")
        if service == "email":
            return await self._send_email(config, variables)
        if service == "slack":
            return await self._send_slack(config, variables)
        return {"error": f"Unsupported integration service: {service}"}

    async def _send_email(self, config: dict, variables: dict) -> dict:
        raw_recipients = config.get("recipients", config.get("to", ""))
        subject = interpolate(config.get("subject", ""), variables)
        body = interpolate(config.get("body", ""), variables)
        from_email = config.get("from", "automind@resend.dev")

        # Normalise recipients to a list
        if isinstance(raw_recipients, str):
            resolved = interpolate(raw_recipients, variables)
            if isinstance(resolved, list):
                # Variable resolved to a list (e.g. list of lead objects)
                recipients = []
                for item in resolved:
                    if isinstance(item, dict):
                        recipients.append(item.get("email", item.get("name", str(item))))
                    else:
                        recipients.append(str(item))
            elif isinstance(resolved, dict):
                recipients = [resolved.get("email", str(resolved))]
            else:
                recipients = [r.strip() for r in str(resolved).split(",") if r.strip()]
        elif isinstance(raw_recipients, list):
            recipients = [interpolate(str(r), variables) if isinstance(r, str) else str(r) for r in raw_recipients]
        else:
            recipients = [str(raw_recipients)]

        if not recipients:
            return {"error": "No email recipients specified", "emails_sent": 0, "service": "email"}

        if not settings.RESEND_API_KEY:
            logger.info("RESEND_API_KEY not set - returning mock email result")
            return {
                "emails_sent": len(recipients),
                "service": "email",
                "mock": True,
                "recipients": recipients,
                "subject": subject,
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
                        "from": from_email,
                        "to": recipients,
                        "subject": subject,
                        "html": body,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            return {
                "emails_sent": len(recipients),
                "service": "email",
                "resend_id": data.get("id"),
                "recipients": recipients,
                "subject": subject,
            }
        except httpx.HTTPStatusError as exc:
            logger.exception("Resend API error")
            return {
                "error": f"Resend API error: {exc.response.status_code} - {exc.response.text}",
                "emails_sent": 0,
                "service": "email",
            }
        except Exception as exc:
            logger.exception("Email send error")
            return {
                "error": f"Email error: {exc}",
                "emails_sent": 0,
                "service": "email",
            }

    async def _send_slack(self, config: dict, variables: dict) -> dict:
        message = interpolate(config.get("message", ""), variables)
        webhook_url = config.get("webhook_url") or settings.SLACK_WEBHOOK_URL

        if not webhook_url:
            logger.info("SLACK_WEBHOOK_URL not set - returning mock slack result")
            return {
                "message_sent": True,
                "service": "slack",
                "mock": True,
                "message": message,
            }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    webhook_url,
                    json={"text": message},
                )
                resp.raise_for_status()
            return {
                "message_sent": True,
                "service": "slack",
                "message": message,
            }
        except Exception as exc:
            logger.exception("Slack webhook error")
            return {
                "error": f"Slack error: {exc}",
                "message_sent": False,
                "service": "slack",
            }
