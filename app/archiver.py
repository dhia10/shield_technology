"""
Shield Technology - Log Archiver & Cryptographic Integrity Verifier
Weeks 7-8: Routine for export, rotation, and SHA-256 integrity checksum verification.
"""

import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelemetryEventModel


class LogArchiver:
    def __init__(self, archive_dir: str = "./data/archives"):
        self.archive_dir = archive_dir
        os.makedirs(self.archive_dir, exist_ok=True)

    @staticmethod
    def compute_file_sha256(filepath: str) -> str:
        """Calculates cryptographic SHA-256 digest of an archive file for integrity verification."""
        sha = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    async def archive_events(
        self,
        session: AsyncSession,
        cutoff_date: datetime,
        compress: bool = True,
    ) -> Dict[str, Any]:
        """
        Exports events prior to `cutoff_date` to an immutable archive file,
        calculates SHA-256 hash for audit compliance, and flags database records as archived.
        """
        # 1. Fetch unarchived events prior to cutoff
        query = (
            select(TelemetryEventModel)
            .where(
                TelemetryEventModel.timestamp < cutoff_date,
                TelemetryEventModel.is_archived == False,
            )
            .order_by(TelemetryEventModel.timestamp.asc())
        )
        result = await session.execute(query)
        events = result.scalars().all()

        if not events:
            return {
                "status": "noop",
                "events_archived": 0,
                "message": "No unarchived events found prior to cutoff date.",
            }

        # 2. Format filename
        ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ext = "jsonl.gz" if compress else "jsonl"
        archive_filename = f"telemetry_archive_{ts_label}.{ext}"
        archive_path = os.path.join(self.archive_dir, archive_filename)

        # 3. Serialize and write
        event_ids = []
        if compress:
            with gzip.open(archive_path, "wt", encoding="utf-8") as gf:
                for ev in events:
                    event_ids.append(ev.id)
                    gf.write(json.dumps(ev.to_dict()) + "\n")
        else:
            with open(archive_path, "w", encoding="utf-8") as f:
                for ev in events:
                    event_ids.append(ev.id)
                    f.write(json.dumps(ev.to_dict()) + "\n")

        # 4. Cryptographic integrity checksum
        checksum_sha256 = self.compute_file_sha256(archive_path)

        # 5. Mark database records as archived
        update_stmt = (
            update(TelemetryEventModel)
            .where(TelemetryEventModel.id.in_(event_ids))
            .values(is_archived=True)
        )
        await session.execute(update_stmt)
        await session.commit()

        return {
            "status": "success",
            "events_archived": len(event_ids),
            "archive_file": archive_filename,
            "archive_path": archive_path,
            "sha256_checksum": checksum_sha256,
            "cutoff_date": cutoff_date.isoformat(),
        }


log_archiver = LogArchiver()
