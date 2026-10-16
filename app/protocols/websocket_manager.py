"""
Shield Technology - WebSocket Real-Time Alert Broadcast Engine.
Pushes instant security notifications and telemetry metric feeds to connected SOC dashboards.
Supports tenant isolation, selective filtering, and active connection health monitoring.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("shield.websocket")


class WebSocketConnection:
    """Represents an active client WebSocket session."""

    def __init__(self, client_id: str, tenant_id: str, is_admin: bool = False):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.is_admin = is_admin
        self.connected_at = datetime.now(timezone.utc)
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribed_severities: Set[str] = {"HIGH", "CRITICAL"}
        self.is_active = True

    async def send_json(self, data: Dict[str, Any]):
        if not self.is_active:
            return
        try:
            self.message_queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("Dropping alert for slow client: %s", self.client_id)


class WebSocketManager:
    """
    Central connection manager coordinating tenant-scoped alert subscriptions.
    """

    def __init__(self):
        self._connections: Dict[str, WebSocketConnection] = {}
        self._tenant_index: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
        self.total_broadcasts = 0
        self.total_delivered = 0

    async def connect(self, client_id: str, tenant_id: str, is_admin: bool = False) -> WebSocketConnection:
        conn = WebSocketConnection(client_id, tenant_id, is_admin)
        async with self._lock:
            self._connections[client_id] = conn
            if tenant_id not in self._tenant_index:
                self._tenant_index[tenant_id] = set()
            self._tenant_index[tenant_id].add(client_id)
        logger.info("WebSocket connected: %s (tenant: %s)", client_id, tenant_id)
        return conn

    async def disconnect(self, client_id: str):
        async with self._lock:
            if client_id in self._connections:
                conn = self._connections.pop(client_id)
                conn.is_active = False
                if conn.tenant_id in self._tenant_index:
                    self._tenant_index[conn.tenant_id].discard(client_id)
        logger.info("WebSocket disconnected: %s", client_id)

    async def broadcast_alert(self, alert: Dict[str, Any]):
        """Dispatches an alert to authorized subscribers respecting tenant boundaries."""
        self.total_broadcasts += 1
        tenant_id = alert.get("tenant_id")
        severity = alert.get("severity", "MEDIUM")

        async with self._lock:
            target_clients = set()
            # Tenant subscribers
            if tenant_id and tenant_id in self._tenant_index:
                target_clients.update(self._tenant_index[tenant_id])

            # Global admin subscribers
            for c_id, conn in self._connections.items():
                if conn.is_admin:
                    target_clients.add(c_id)

            for c_id in target_clients:
                conn = self._connections.get(c_id)
                if conn and severity in conn.subscribed_severities:
                    await conn.send_json(alert)
                    self.total_delivered += 1

    def active_connections_count(self) -> int:
        return len(self._connections)

    def stats(self) -> Dict[str, Any]:
        return {
            "active_clients": len(self._connections),
            "total_broadcasts": self.total_broadcasts,
            "total_delivered_messages": self.total_delivered,
            "tenants_active": list(self._tenant_index.keys()),
        }


# Singleton manager instance
ws_manager = WebSocketManager()
