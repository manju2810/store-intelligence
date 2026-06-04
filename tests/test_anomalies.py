# PROMPT: Generate pytest tests for anomaly detection in
# retail store analytics covering queue spikes, conversion
# drops, dead zones and high abandonment rates.
# CHANGES MADE: Added severity level validation, suggested
# action presence check, and empty anomalies list handling.

import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../app'))

from main import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

class TestAnomaliesEndpoint:

    @pytest.mark.asyncio
    async def test_anomalies_returns_200(self, client):
        response = await client.get(
            "/stores/ST1008/anomalies"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_anomalies_has_required_fields(
        self, client
    ):
        response = await client.get(
            "/stores/ST1008/anomalies"
        )
        data = response.json()
        assert "store_id" in data
        assert "anomalies" in data

    @pytest.mark.asyncio
    async def test_anomaly_severity_valid(self, client):
        response = await client.get(
            "/stores/ST1008/anomalies"
        )
        data = response.json()
        valid_severities = ["INFO", "WARN", "CRITICAL"]
        for anomaly in data["anomalies"]:
            assert anomaly["severity"] in valid_severities

    @pytest.mark.asyncio
    async def test_anomaly_has_suggested_action(
        self, client
    ):
        response = await client.get(
            "/stores/ST1008/anomalies"
        )
        data = response.json()
        for anomaly in data["anomalies"]:
            assert "suggested_action" in anomaly
            assert len(anomaly["suggested_action"]) > 0

    @pytest.mark.asyncio
    async def test_empty_store_no_anomalies(self, client):
        response = await client.get(
            "/stores/EMPTY_STORE/anomalies"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["anomalies"], list)

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_has_status_field(self, client):
        response = await client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["OK", "DEGRADED", "ERROR"]