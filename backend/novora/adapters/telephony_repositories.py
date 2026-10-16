import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from novora.adapters.db_models import DBTelephonyCall, DBWebhookEvent
from novora.core.models import TelephonyCallRecord, WebhookEventRecord

class SQLAlchemyTelephonyRepository:
    def __init__(self, session_manager: Any) -> None:
        self.sm = session_manager

    def save(self, record: TelephonyCallRecord) -> TelephonyCallRecord:
        with self.sm.get_session() as session:
            db_call = DBTelephonyCall(
                id=record.id,
                provider=record.provider,
                call_sid=record.call_sid,
                from_number=record.from_number,
                to_number=record.to_number,
                call_status=record.call_status,
                duration_seconds=record.duration_seconds,
                recording_sid=record.recording_sid,
                recording_url=record.recording_url,
                call_metadata=json.dumps(record.metadata),
                created_at=record.created_at,
            )
            session.merge(db_call)
            session.commit()
        return record

    def get(self, call_sid: str) -> Optional[TelephonyCallRecord]:
        with self.sm.get_session() as session:
            row = session.query(DBTelephonyCall).filter(DBTelephonyCall.call_sid == call_sid).first()
            if not row:
                return None
            return TelephonyCallRecord(
                id=row.id,
                provider=row.provider,
                call_sid=row.call_sid,
                from_number=row.from_number,
                to_number=row.to_number,
                call_status=row.call_status,
                duration_seconds=row.duration_seconds,
                recording_sid=row.recording_sid,
                recording_url=row.recording_url,
                metadata=json.loads(row.call_metadata),
                created_at=row.created_at,
            )

    def list_all(self, limit: int = 50, offset: int = 0) -> List[TelephonyCallRecord]:
        with self.sm.get_session() as session:
            rows = session.query(DBTelephonyCall).offset(offset).limit(limit).all()
            return [
                TelephonyCallRecord(
                    id=r.id,
                    provider=r.provider,
                    call_sid=r.call_sid,
                    from_number=r.from_number,
                    to_number=r.to_number,
                    call_status=r.call_status,
                    duration_seconds=r.duration_seconds,
                    recording_sid=r.recording_sid,
                    recording_url=r.recording_url,
                    metadata=json.loads(r.call_metadata),
                    created_at=r.created_at,
                )
                for r in rows
            ]

class SQLAlchemyWebhookEventRepository:
    def __init__(self, session_manager: Any) -> None:
        self.sm = session_manager

    def record_event(self, event: WebhookEventRecord) -> WebhookEventRecord:
        with self.sm.get_session() as session:
            db_evt = DBWebhookEvent(
                id=event.id,
                provider=event.provider,
                event_id=event.event_id,
                signature_verified=event.signature_verified,
                payload=json.dumps(event.payload),
                status=event.status,
                created_at=event.created_at,
            )
            session.merge(db_evt)
            session.commit()
        return event

    def is_processed(self, provider: str, event_id: str) -> bool:
        with self.sm.get_session() as session:
            count = session.query(DBWebhookEvent).filter(
                DBWebhookEvent.provider == provider,
                DBWebhookEvent.event_id == event_id,
            ).count()
            return count > 0

    def get(self, event_id: str) -> Optional[WebhookEventRecord]:
        with self.sm.get_session() as session:
            row = session.query(DBWebhookEvent).filter(DBWebhookEvent.event_id == event_id).first()
            if not row:
                return None
            return WebhookEventRecord(
                id=row.id,
                provider=row.provider,
                event_id=row.event_id,
                signature_verified=row.signature_verified,
                payload=json.loads(row.payload),
                status=row.status,
                created_at=row.created_at,
            )
