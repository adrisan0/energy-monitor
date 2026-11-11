from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from app.cli.main import app as cli_app
from app.db.session import get_session_factory
from app.main import app
from app.models import SystemEvent
from app.services.backup import run_backup
from app.services.meter_client import MeterFetchResult
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload
from app.workers import poller

XML = """
<root>
  <variable><id>pac1</id><value>2954.41</value></variable>
  <variable><id>pac2</id><value>3409.05</value></variable>
  <variable><id>fpot1</id><value>-1.000</value></variable>
</root>
"""


def seed_sample() -> None:
    with get_session_factory()() as db:
        parsed = parse_meter_xml(XML, timestamp_utc=datetime(2026, 7, 2, 14, 0, tzinfo=UTC))
        store_parsed_payload(db, parsed, poll_duration_ms=7)
        db.commit()


def test_latest_api_response() -> None:
    seed_sample()
    with TestClient(app) as client:
        response = client.get("/api/v1/latest")
        assert response.status_code == 200
        body = response.json()
        assert round(body["house_consumption_w"]) == 455
        assert body["grid_export_w"] == 2954.41


def test_latest_api_prefers_last_usable_sample() -> None:
    with get_session_factory()() as db:
        valid = parse_meter_xml(XML, timestamp_utc=datetime(2026, 7, 2, 14, 0, tzinfo=UTC))
        invalid = parse_meter_xml("<!DOCTYPE html><html><script>window.location.href='/en/login.html'</script></html>")
        store_parsed_payload(db, valid, poll_duration_ms=7)
        store_parsed_payload(db, invalid, poll_duration_ms=8)
        db.commit()

    with TestClient(app) as client:
        response = client.get("/api/v1/latest")
        assert response.status_code == 200
        body = response.json()
        assert body["data_quality"] == "valid"
        assert round(body["house_consumption_w"]) == 455


def test_cli_status_json() -> None:
    seed_sample()
    runner = CliRunner()
    result = runner.invoke(cli_app, ["status", "--json"])
    assert result.exit_code == 0
    assert '"house_consumption_w": 454.64' in result.stdout


@pytest.mark.asyncio
async def test_worker_records_meter_down(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    async def broken_fetch() -> MeterFetchResult:
        raise RuntimeError("meter down")

    async def fake_apply_meter_outage_failsafe(db) -> None:
        del db
        called["count"] += 1

    monkeypatch.setattr(poller, "fetch_meter_payload", broken_fetch)
    monkeypatch.setattr(poller, "apply_meter_outage_failsafe", fake_apply_meter_outage_failsafe)
    with get_session_factory()() as db:
        result = await poller.poll_once(db)
        events = db.query(SystemEvent).all()
        assert not result.ok
        assert events[-1].event_type == "meter_poll_failed"
        assert events[-1].metadata_json == {"outage_failsafe_applied": True}
    assert called["count"] == 1


@pytest.mark.asyncio
async def test_worker_stores_corrupt_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    async def corrupt_fetch() -> MeterFetchResult:
        return MeterFetchResult(payload="<root><variable>", duration_ms=2, source="test")

    monkeypatch.setattr(poller, "fetch_meter_payload", corrupt_fetch)
    with get_session_factory()() as db:
        result = await poller.poll_once(db)
        assert result.ok
        assert result.sample_id is not None


@pytest.mark.asyncio
async def test_worker_records_empty_values_as_poll_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    async def empty_fetch() -> MeterFetchResult:
        raise RuntimeError("No se pudo obtener XML del medidor: http://meter/: respuesta sin XML util")

    async def fake_apply_meter_outage_failsafe(db) -> None:
        del db
        called["count"] += 1

    monkeypatch.setattr(poller, "fetch_meter_payload", empty_fetch)
    monkeypatch.setattr(poller, "apply_meter_outage_failsafe", fake_apply_meter_outage_failsafe)
    with get_session_factory()() as db:
        result = await poller.poll_once(db)
        events = db.query(SystemEvent).all()
        assert not result.ok
        assert events[-1].event_type == "meter_poll_failed"
        assert events[-1].metadata_json == {"outage_failsafe_applied": True}
    assert called["count"] == 1


@pytest.mark.asyncio
async def test_detect_prolonged_outage_applies_white_failsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    async def fake_apply_meter_outage_failsafe(db) -> None:
        del db
        called["count"] += 1

    monkeypatch.setattr(poller, "apply_meter_outage_failsafe", fake_apply_meter_outage_failsafe)

    with get_session_factory()() as db:
        parsed = parse_meter_xml(
            XML,
            timestamp_utc=datetime(2026, 7, 2, 14, 0, tzinfo=UTC),
        )
        store_parsed_payload(db, parsed, poll_duration_ms=7)
        db.commit()

        latest = db.query(__import__("app.models", fromlist=["MeterSample"]).MeterSample).order_by(
            __import__("app.models", fromlist=["MeterSample"]).MeterSample.timestamp_utc.desc()
        ).first()
        latest.timestamp_utc = datetime(2026, 7, 2, 13, 0, tzinfo=UTC)
        db.commit()

        await poller.detect_prolonged_outage(db)
        events = db.query(SystemEvent).all()

    assert called["count"] == 1
    assert events[-1].event_type == "meter_outage"


def test_maybe_record_meter_recovery_marks_first_valid_sample_after_outage() -> None:
    with get_session_factory()() as db:
        record = SystemEvent(
            timestamp_utc=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
            event_type="meter_outage",
            severity="warning",
            message="outage",
            metadata_json={},
        )
        db.add(record)
        parsed = parse_meter_xml(XML, timestamp_utc=datetime(2026, 7, 2, 14, 0, tzinfo=UTC))
        sample = store_parsed_payload(db, parsed, poll_duration_ms=7)
        sample_id = sample.id

        poller.maybe_record_meter_recovery(db, sample)
        db.commit()
        events = db.query(SystemEvent).order_by(SystemEvent.id.asc()).all()

    assert events[-1].event_type == "meter_recovered"
    assert events[-1].metadata_json["sample_id"] == sample_id


def test_backup_creates_compressed_file() -> None:
    with get_session_factory()() as db:
        record = run_backup(db)
        db.commit()
        assert record.status == "ok"
        assert record.filename.endswith(".sql.gz")
        assert record.size_bytes and record.size_bytes > 0
