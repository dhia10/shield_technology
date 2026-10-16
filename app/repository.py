"""
Shield Technology - Telemetry Repository
Weeks 4 & 7: High-throughput Bulk Insert/Upsert, Time-range filtering,
and Cursor-based Pagination.
"""

import base64
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, desc, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import TelemetryEventModel
from app.schemas import SanitizedTelemetryEvent, TelemetryHistoryItem, TelemetryStatsResponse


class TelemetryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_insert(self, events: List[SanitizedTelemetryEvent]) -> int:
        """
        High-performance bulk upsert.
        Handles duplicates by updating payload and metadata on conflict.
        """
        if not events:
            return 0

        # Build list of dicts for bulk insertion
        records = []
        for e in events:
            rec_id = e.id or str(uuid.uuid4())
            records.append({
                "id": rec_id,
                "event_hash": e.event_hash,
                "timestamp": e.timestamp,
                "agent_id": e.agent_id,
                "severity": e.severity.value if hasattr(e.severity, "value") else str(e.severity),
                "event_type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                "source_ip": e.source_ip,
                "destination_ip": e.destination_ip,
                "sanitized_payload": e.sanitized_payload,
                "raw_checksum": e.raw_checksum,
                "enrichment": e.enrichment,
                "is_archived": False,
                "created_at": datetime.now(timezone.utc),
            })

        # Detect dialect to use native ON CONFLICT DO UPDATE
        bind = self.session.bind
        dialect_name = bind.dialect.name if bind else "sqlite"
        chunk_size = 50 if dialect_name == "sqlite" else 500

        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            if dialect_name == "postgresql":
                stmt = pg_insert(TelemetryEventModel).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["event_hash"],
                    set_={
                        "sanitized_payload": stmt.excluded.sanitized_payload,
                        "enrichment": stmt.excluded.enrichment,
                        "created_at": stmt.excluded.created_at,
                    }
                )
                await self.session.execute(stmt)
            elif dialect_name == "sqlite":
                stmt = sqlite_insert(TelemetryEventModel).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["event_hash"],
                    set_={
                        "sanitized_payload": stmt.excluded.sanitized_payload,
                        "enrichment": stmt.excluded.enrichment,
                    }
                )
                await self.session.execute(stmt)
            else:
                # Fallback for standard session mapping
                for r in chunk:
                    obj = TelemetryEventModel(**r)
                    await self.session.merge(obj)

        await self.session.commit()
        return len(records)

    async def single_insert(self, event: SanitizedTelemetryEvent) -> TelemetryEventModel:
        """Single-record insert for benchmark comparisons."""
        rec = TelemetryEventModel(
            id=event.id or str(uuid.uuid4()),
            event_hash=event.event_hash,
            timestamp=event.timestamp,
            agent_id=event.agent_id,
            severity=event.severity.value if hasattr(event.severity, "value") else str(event.severity),
            event_type=event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            source_ip=event.source_ip,
            destination_ip=event.destination_ip,
            sanitized_payload=event.sanitized_payload,
            raw_checksum=event.raw_checksum,
            enrichment=event.enrichment,
            is_archived=False,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(rec)
        await self.session.commit()
        await self.session.refresh(rec)
        return rec

    @staticmethod
    def encode_cursor(dt: datetime, event_id: str) -> str:
        raw_str = f"{dt.isoformat()}|{event_id}"
        return base64.urlsafe_b64encode(raw_str.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode_cursor(cursor_str: str) -> Tuple[datetime, str]:
        raw_str = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        dt_str, event_id = raw_str.split("|", 1)
        return datetime.fromisoformat(dt_str), event_id

    async def get_history(
        self,
        cursor: Optional[str] = None,
        limit: int = 50,
        agent_id: Optional[str] = None,
        severity: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[TelemetryHistoryItem], Optional[str], bool]:
        """
        Cursor-based pagination query.
        Ensures O(1) performance even on millions of telemetry records.
        """
        conditions = [TelemetryEventModel.is_archived == False]

        if agent_id:
            conditions.append(TelemetryEventModel.agent_id == agent_id)
        if severity:
            conditions.append(TelemetryEventModel.severity == severity.upper())
        if event_type:
            conditions.append(TelemetryEventModel.event_type == event_type.upper())
        if start_time:
            conditions.append(TelemetryEventModel.timestamp >= start_time)
        if end_time:
            conditions.append(TelemetryEventModel.timestamp <= end_time)

        if cursor:
            cursor_dt, cursor_id = self.decode_cursor(cursor)
            # Tuple comparison for strict cursor ordering
            conditions.append(
                (TelemetryEventModel.timestamp < cursor_dt) |
                ((TelemetryEventModel.timestamp == cursor_dt) & (TelemetryEventModel.id < cursor_id))
            )

        query = (
            select(TelemetryEventModel)
            .where(and_(*conditions))
            .order_by(desc(TelemetryEventModel.timestamp), desc(TelemetryEventModel.id))
            .limit(limit + 1)
        )

        result = await self.session.execute(query)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        items = rows[:limit]

        next_cursor = None
        if has_more and items:
            last_item = items[-1]
            next_cursor = self.encode_cursor(last_item.timestamp, last_item.id)

        history_items = [
            TelemetryHistoryItem(
                id=item.id,
                event_hash=item.event_hash,
                timestamp=item.timestamp,
                agent_id=item.agent_id,
                severity=item.severity,
                event_type=item.event_type,
                source_ip=item.source_ip,
                destination_ip=item.destination_ip,
                sanitized_payload=item.sanitized_payload or {},
                enrichment=item.enrichment or {},
                created_at=item.created_at,
            )
            for item in items
        ]

        return history_items, next_cursor, has_more

    async def get_stats(self, window_hours: int = 24) -> TelemetryStatsResponse:
        """Computes security aggregation metrics over a specified time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        # 1. Total events
        total_q = select(func.count(TelemetryEventModel.id)).where(TelemetryEventModel.timestamp >= cutoff)
        total_events = (await self.session.execute(total_q)).scalar() or 0

        # 2. Count by severity
        sev_q = (
            select(TelemetryEventModel.severity, func.count(TelemetryEventModel.id))
            .where(TelemetryEventModel.timestamp >= cutoff)
            .group_by(TelemetryEventModel.severity)
        )
        by_severity = {row[0]: row[1] for row in (await self.session.execute(sev_q)).all()}

        # 3. Count by event_type
        type_q = (
            select(TelemetryEventModel.event_type, func.count(TelemetryEventModel.id))
            .where(TelemetryEventModel.timestamp >= cutoff)
            .group_by(TelemetryEventModel.event_type)
        )
        by_event_type = {row[0]: row[1] for row in (await self.session.execute(type_q)).all()}

        # 4. Top source IPs
        ip_q = (
            select(TelemetryEventModel.source_ip, func.count(TelemetryEventModel.id).label("cnt"))
            .where(TelemetryEventModel.timestamp >= cutoff)
            .group_by(TelemetryEventModel.source_ip)
            .order_by(desc("cnt"))
            .limit(5)
        )
        top_ips = [{"ip": row[0], "count": row[1]} for row in (await self.session.execute(ip_q)).all()]

        return TelemetryStatsResponse(
            window_hours=window_hours,
            total_events=total_events,
            by_severity=by_severity,
            by_event_type=by_event_type,
            top_source_ips=top_ips,
            cache_hit=False,
            generated_at=datetime.now(timezone.utc),
        )
