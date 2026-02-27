"""Tests for GET /v1/preferences/catalog endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EXPECTED_KEYS = [
    "revHappiness",
    "acousticDrama",
    "steeringFeel",
    "dailyCompliance",
    "trackReadiness",
    "depreciationStability",
]


def test_catalog_returns_200():
    response = client.get("/v1/preferences/catalog")
    assert response.status_code == 200


def test_catalog_returns_six_axes():
    response = client.get("/v1/preferences/catalog")
    data = response.json()
    assert len(data["axes"]) == 6


def test_catalog_keys_match_exactly():
    response = client.get("/v1/preferences/catalog")
    data = response.json()
    actual_keys = [axis["key"] for axis in data["axes"]]
    assert actual_keys == EXPECTED_KEYS


def test_catalog_scale_min_max_correct():
    response = client.get("/v1/preferences/catalog")
    data = response.json()
    for axis in data["axes"]:
        assert axis["scaleMin"] == 0
        assert axis["scaleMax"] == 10


def test_catalog_default_weight_sums_to_one():
    response = client.get("/v1/preferences/catalog")
    data = response.json()
    total_weight = sum(axis["defaultWeight"] for axis in data["axes"])
    assert abs(total_weight - 1.0) < 0.01
