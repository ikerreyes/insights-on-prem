"""Tests for RequestReport model and on-demand gathering endpoints."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import app
from app.models import RequestReport

client = TestClient(app)

REQUEST_ID = "00000000-0000-0000-0000-000000000000"
CLUSTER_ID = "00000000-0000-0000-0000-000000000001"


# --- Model tests ---


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_create_request_report(db_session):
    """Test creating a new request report."""
    report_data = json.dumps([
        {"rule_fqdn": "test.rule", "error_key": "ERROR1", "details": {}}
    ])

    record = RequestReport.create(
        db=db_session,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report=report_data,
    )
    db_session.commit()

    assert record.request_id == REQUEST_ID
    assert record.cluster_id == CLUSTER_ID
    assert record.report == report_data
    assert isinstance(record.created_at, datetime)


def test_get_by_cluster_and_request(db_session):
    """Test retrieving a request report by cluster and request ID."""
    RequestReport.create(
        db=db_session,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report="[]",
    )
    db_session.commit()

    found = RequestReport.get_by_cluster_and_request(
        db_session, CLUSTER_ID, REQUEST_ID
    )
    assert found is not None
    assert found.request_id == REQUEST_ID

    not_found = RequestReport.get_by_cluster_and_request(
        db_session, CLUSTER_ID, "nonexistent"
    )
    assert not_found is None


def test_get_by_cluster_and_request_wrong_cluster(db_session):
    """Test that lookup with wrong cluster_id returns None."""
    RequestReport.create(
        db=db_session,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report="[]",
    )
    db_session.commit()

    result = RequestReport.get_by_cluster_and_request(
        db_session, "wrong-cluster", REQUEST_ID
    )
    assert result is None


def test_delete_older_than(db_session):
    """Test deleting records older than a cutoff."""
    old_record = RequestReport(
        request_id="old-req",
        cluster_id=CLUSTER_ID,
        report="[]",
        created_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    new_record = RequestReport(
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report="[]",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([old_record, new_record])
    db_session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    deleted = RequestReport.delete_older_than(db_session, cutoff)
    db_session.commit()

    assert deleted == 1
    assert db_session.query(RequestReport).count() == 1
    remaining = db_session.query(RequestReport).first()
    assert remaining.request_id == REQUEST_ID


def test_delete_older_than_none_to_delete(db_session):
    """Test delete with no old records returns 0."""
    RequestReport.create(
        db=db_session,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report="[]",
    )
    db_session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    deleted = RequestReport.delete_older_than(db_session, cutoff)
    assert deleted == 0


# --- Endpoint tests ---


def test_request_status_not_found(database):
    """Test status endpoint returns 404 for unknown request."""
    response = client.get(
        f"/api/v2/cluster/{CLUSTER_ID}/request/nonexistent/status"
    )
    assert response.status_code == 404


def test_request_status_processed(database):
    """Test status endpoint returns processed for existing request."""
    RequestReport.create(
        db=database,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report="[]",
    )
    database.commit()

    response = client.get(
        f"/api/v2/cluster/{CLUSTER_ID}/request/{REQUEST_ID}/status"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cluster"] == CLUSTER_ID
    assert data["requestID"] == REQUEST_ID
    assert data["status"] == "processed"


def test_request_status_wrong_cluster(database):
    """Test status endpoint returns 404 when cluster_id doesn't match."""
    RequestReport.create(
        db=database,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report="[]",
    )
    database.commit()

    response = client.get(
        f"/api/v2/cluster/wrong-cluster/request/{REQUEST_ID}/status"
    )
    assert response.status_code == 404


def test_request_report_not_found(database):
    """Test report endpoint returns 404 for unknown request."""
    response = client.get(
        f"/api/v2/cluster/{CLUSTER_ID}/request/nonexistent/report"
    )
    assert response.status_code == 404


def test_request_report_returns_simplified_report(database):
    """Test report endpoint enriches rule hits with content (description, total_risk)."""
    from unittest.mock import MagicMock

    rule_hits = [
        {"rule_fqdn": "ccx_rules_ocp.external.rules.rule_a.report", "error_key": "ERR1", "details": {}},
        {"rule_fqdn": "ccx_rules_ocp.external.rules.rule_b.report", "error_key": "ERR2", "details": {}},
        {"rule_fqdn": "ccx_rules_ocp.external.rules.unknown.report", "error_key": "ERR3", "details": {}},
    ]
    RequestReport.create(
        db=database,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report=json.dumps(rule_hits),
    )
    database.commit()

    # Mock content service — return content for first two rules, None for the third
    mock_content = MagicMock()
    mock_content.get_content.side_effect = lambda fqdn, ek: {
        ("ccx_rules_ocp.external.rules.rule_a", "ERR1"): {
            "description": "Rule A fires when ...",
            "total_risk": 3,
        },
        ("ccx_rules_ocp.external.rules.rule_b", "ERR2"): {
            "description": "Rule B detects ...",
            "total_risk": 1,
        },
    }.get((fqdn, ek))

    app.state.content_service = mock_content
    try:
        response = client.get(
            f"/api/v2/cluster/{CLUSTER_ID}/request/{REQUEST_ID}/report"
        )
    finally:
        del app.state.content_service

    assert response.status_code == 200
    data = response.json()
    assert data["cluster"] == CLUSTER_ID
    assert data["requestID"] == REQUEST_ID
    assert data["status"] == "processed"
    # Third rule had no content — skipped (matches smart-proxy behavior)
    assert len(data["report"]) == 2
    assert data["report"][0]["rule_fqdn"] == "ccx_rules_ocp.external.rules.rule_a"
    assert data["report"][0]["description"] == "Rule A fires when ..."
    assert data["report"][0]["total_risk"] == 3
    assert data["report"][1]["error_key"] == "ERR2"
    assert data["report"][1]["total_risk"] == 1
