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

    # Rules with description/total_risk have content,
    # rules without them simulate missing content (skipped in response)
    test_rules = [
        {"rule_fqdn": "ccx_rules_ocp.external.rules.rule_a", "error_key": "ERR1", "description": "Rule A fires when ...", "total_risk": 3},
        {"rule_fqdn": "ccx_rules_ocp.external.rules.rule_b", "error_key": "ERR2", "description": "Rule B detects ...", "total_risk": 1},
        {"rule_fqdn": "ccx_rules_ocp.external.rules.unknown", "error_key": "ERR3"},
    ]

    # Build stored report — rule_fqdn has .report suffix as stored by processor
    rule_hits = [
        {"rule_fqdn": r["rule_fqdn"] + ".report", "error_key": r["error_key"], "details": {}}
        for r in test_rules
    ]
    RequestReport.create(
        db=database,
        request_id=REQUEST_ID,
        cluster_id=CLUSTER_ID,
        report=json.dumps(rule_hits),
    )
    database.commit()

    # Mock content service — return content only for rules that have it
    mock_content = MagicMock()
    content_map = {
        (r["rule_fqdn"], r["error_key"]): {"description": r["description"], "total_risk": r["total_risk"]}
        for r in test_rules if "description" in r
    }
    mock_content.get_content.side_effect = lambda fqdn, ek: content_map.get((fqdn, ek))

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
    # Rules without content are skipped (matches smart-proxy behavior)
    expected = [r for r in test_rules if "description" in r]
    assert len(data["report"]) == len(expected)
    for i, exp in enumerate(expected):
        for key, value in exp.items():
            assert data["report"][i][key] == value
