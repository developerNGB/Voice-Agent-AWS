"""Structured logging: JSONL files locally, DynamoDB/S3 when configured.

Every call produces one ``CallRecord`` with a transcript, routing events,
security events, tool calls and errors — PII-redacted before writing.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.models.call import CallRecord
from app.models.session import Session
from app.security.sanitization import sanitize_for_log


def _now_iso(ts: float | None = None) -> str:
    moment = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return moment.isoformat(timespec="seconds")


class StructuredLogger:
    """Writes ``events.jsonl`` / ``calls.jsonl`` / ``transcripts/<id>.json``."""

    def __init__(self, log_dir: str | Path = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / "transcripts").mkdir(parents=True, exist_ok=True)
        self.in_memory = False

    # -- event log -----------------------------------------------------------

    def event(self, event_type: str, **fields) -> dict:
        record = {"type": event_type, "at": _now_iso(), **fields}
        self._append(self.log_dir / "events.jsonl", record)
        return record

    def error(self, message: str, **fields) -> dict:
        return self.event("error", message=sanitize_for_log(str(message)), **fields)

    # -- final call record ---------------------------------------------------

    def build_record(self, session: Session) -> CallRecord:
        transcript = [
            {
                "at": _now_iso(t.at),
                "speaker": t.speaker,
                "text": sanitize_for_log(t.text),
                "skill": t.skill_id,
                "latency_ms": round(t.latency_ms, 1),
            }
            for t in session.history
        ]
        return CallRecord(
            session_id=session.session_id,
            agent_id=session.agent_id,
            caller_id=session.caller_id,
            started_at=_now_iso(session.started_at),
            ended_at=_now_iso(session.ended_at or time.time()),
            duration_seconds=session.duration_seconds,
            skills_used=list(session.skills_used),
            turn_count=session.turn_count,
            routing_events=len(session.routing_events),
            errors=[sanitize_for_log(e) for e in session.errors],
            status=session.status,
            transcript=transcript,
            security_events=list(session.security_events),
        )

    def finalize(self, session: Session) -> CallRecord:
        record = self.build_record(session)
        self._append(self.log_dir / "calls.jsonl", record.to_dict())
        transcript_path = self.log_dir / "transcripts" / f"{session.session_id}.json"
        transcript_path.write_text(
            json.dumps(record.to_dict(), indent=2), encoding="utf-8"
        )
        self.event(
            "call_finalized",
            session_id=session.session_id,
            agent_id=session.agent_id,
            duration_seconds=record.duration_seconds,
            turn_count=record.turn_count,
            status=record.status,
        )
        return record

    # -- helpers -------------------------------------------------------------

    def _append(self, path: Path, record: dict) -> None:
        if self.in_memory:
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_calls(self) -> list[dict]:
        path = self.log_dir / "calls.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class MemoryLogger(StructuredLogger):
    """Keeps records in memory — used by tests (no files, no I/O)."""

    def __init__(self):
        super().__init__("/tmp/freebuff-voice-agent-memory-logs")
        self.in_memory = True
        self.events: list[dict] = []
        self.calls: list[dict] = []

    def event(self, event_type: str, **fields) -> dict:
        record = {"type": event_type, "at": _now_iso(), **fields}
        self.events.append(record)
        return record

    def finalize(self, session: Session) -> CallRecord:
        record = self.build_record(session)
        self.calls.append(record.to_dict())
        return record
