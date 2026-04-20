"""Tests for on-demand gathering endpoints."""
import json

from fastapi.testclient import TestClient

from app.main import app
from app.models import RequestReport

client = TestClient(app)

REQUEST_ID = "00000000-0000-0000-0000-000000000000"
CLUSTER_ID = "00000000-0000-0000-0000-000000000001"


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
