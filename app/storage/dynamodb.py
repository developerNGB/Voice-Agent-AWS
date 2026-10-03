"""DynamoDB persistence for sessions, calls, leads and routing events.

All calls are lazy-boto3 so local tests never touch AWS.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

from app.models.call import CallRecord, Lead


class DynamoDBCallStore:
    """Single-table design: ``pk = CALL#<session_id>`` / ``LEAD#...`` etc."""

    def __init__(self, table_name: str, region: str = "ca-central-1", client=None):
        if not table_name:
            raise ValueError("DYNAMODB_TABLE is required for DynamoDBCallStore")
        self.table_name = table_name
        self.region = region
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("dynamodb", region_name=self.region)
        return self._client

    def put_call(self, record: CallRecord) -> None:
        item = {
            "pk": {"S": f"CALL#{record.session_id}"},
            "sk": {"S": "META"},
            "agent_id": {"S": record.agent_id},
            "caller_id": {"S": record.caller_id},
            "started_at": {"S": record.started_at},
            "ended_at": {"S": record.ended_at},
            "duration_seconds": {"N": str(Decimal(str(record.duration_seconds)))},
            "turn_count": {"N": str(record.turn_count)},
            "skills_used": {"SS": record.skills_used or ["none"]},
            "status": {"S": record.status},
            "errors": {"S": json.dumps(record.errors)},
            "transcript": {"S": json.dumps(record.transcript, ensure_ascii=False)},
            "ttl": {"N": str(int(time.time()) + 60 * 60 * 24 * 90)},  # 90-day retention
        }
        self.client.put_item(TableName=self.table_name, Item=item)

    def put_lead(self, lead: Lead) -> None:
        item = {
            "pk": {"S": f"LEAD#{lead.session_id}"},
            "sk": {"S": "LEAD"},
            "agent_id": {"S": lead.agent_id},
            "name": {"S": lead.name},
            "phone": {"S": lead.phone},
            "email": {"S": lead.email},
            "intent": {"S": lead.intent},
            "budget": {"S": lead.budget},
            "created_at": {"N": str(int(lead.created_at))},
        }
        self.client.put_item(TableName=self.table_name, Item=item)

    def put_routing_event(self, session_id: str, agent_id: str, event: dict) -> None:
        item = {
            "pk": {"S": f"CALL#{session_id}"},
            "sk": {"S": f"ROUTE#{event.get('at', time.time())}"},
            "agent_id": {"S": agent_id},
            "skill_id": {"S": event.get("skill_id", "")},
            "status": {"S": event.get("status", "")},
            "confidence": {"N": str(event.get("top_score", 0))},
            "reason": {"S": event.get("reason", "")},
        }
        self.client.put_item(TableName=self.table_name, Item=item)
