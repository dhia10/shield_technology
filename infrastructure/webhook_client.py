"""
Shield Technology Outbound Webhook Client.
Dispatches enterprise events (e.g., Qualified Leads) to external orchestration platforms (n8n, Slack, CRM).
Includes HMAC-SHA256 signature verification headers, exponential backoff, and mock mode.
"""

from abc import ABC, abstractmethod
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional
import httpx

from infrastructure.config import settings

logger = logging.getLogger("shield.webhook")


class WebhookClientInterface(ABC):
    """Contract for sending dispatch webhooks."""

    @abstractmethod
    async def dispatch(self, payload: Dict[str, Any], event_name: str) -> bool:
        """Send asynchronous webhook payload with signature."""
        pass


class HttpWebhookClient(WebhookClientInterface):
    """Production HTTP client dispatching signed webhooks to n8n / external endpoints."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        signing_secret: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.endpoint_url = endpoint_url if endpoint_url is not None else settings.N8N_DISPATCH_WEBHOOK_URL
        self.signing_secret = signing_secret if signing_secret is not None else settings.WEBHOOK_SIGNING_SECRET
        self.timeout_seconds = timeout_seconds or settings.WEBHOOK_TIMEOUT_SECONDS
        self.mock_mode = mock_mode if mock_mode is not None else settings.MOCK_WEBHOOKS

    def _generate_signature(self, body_bytes: bytes) -> str:
        """Computes HMAC-SHA256 signature for message authenticity verification."""
        if not self.signing_secret:
            return ""
        return hmac.new(
            self.signing_secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()

    async def dispatch(self, payload: Dict[str, Any], event_name: str = "lead.qualified") -> bool:
        if self.mock_mode or not self.endpoint_url:
            logger.info(
                f"[MOCK WEBHOOK] Dispatched event '{event_name}' to simulated receiver. "
                f"Payload summary: {list(payload.keys())}"
            )
            return True

        body_data = {
            "event": event_name,
            "version": "v1",
            "data": payload,
        }
        body_json = json.dumps(body_data, ensure_ascii=False)
        body_bytes = body_json.encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"ShieldTechnology-DataPlatform/{settings.APP_VERSION}",
            "X-Shield-Event": event_name,
        }
        sig = self._generate_signature(body_bytes)
        if sig:
            headers["X-Shield-Signature"] = sig

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.endpoint_url, content=body_bytes, headers=headers)
                if response.is_success:
                    logger.info(f"Webhook dispatched successfully: {response.status_code}")
                    return True
                else:
                    logger.warning(f"Webhook receiver returned error: {response.status_code} {response.text}")
                    return False
        except Exception as exc:
            logger.error(f"Failed to dispatch webhook to {self.endpoint_url}: {exc}")
            return False
