"""
Tests for SEC-002 anomaly detection — failed logins, token abuse, impossible velocity.
All Redis operations are mocked to allow tests without a live Redis instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.django_db


def _make_redis_mock(current_value: int):
    """Return a Redis mock where incr() always returns current_value."""
    r = MagicMock()
    r.incr.return_value = current_value
    r.expire.return_value = True
    r.get.return_value = None
    r.setex.return_value = True
    return r


class TestRecordFailedLogin:
    @patch("apps.common.security.anomaly_detection._redis")
    def test_below_threshold_returns_false(self, mock_redis_factory):
        mock_redis_factory.return_value = _make_redis_mock(current_value=3)
        from apps.common.security.anomaly_detection import record_failed_login
        result = record_failed_login("1.2.3.4")
        assert result is False

    @patch("apps.common.security.anomaly_detection._redis")
    def test_at_threshold_returns_true(self, mock_redis_factory):
        mock_redis_factory.return_value = _make_redis_mock(current_value=5)
        from apps.common.security.anomaly_detection import record_failed_login
        result = record_failed_login("1.2.3.4")
        assert result is True

    @patch("apps.common.security.anomaly_detection._redis")
    def test_no_redis_returns_false(self, mock_redis_factory):
        mock_redis_factory.return_value = None
        from apps.common.security.anomaly_detection import record_failed_login
        result = record_failed_login("1.2.3.4")
        assert result is False  # Fail open


class TestRecordTokenAbuse:
    @patch("apps.common.security.anomaly_detection._redis")
    def test_below_threshold_safe(self, mock_redis_factory):
        mock_redis_factory.return_value = _make_redis_mock(current_value=2)
        from apps.common.security.anomaly_detection import record_token_abuse
        assert record_token_abuse("2.3.4.5") is False

    @patch("apps.common.security.anomaly_detection._redis")
    def test_at_threshold_flagged(self, mock_redis_factory):
        mock_redis_factory.return_value = _make_redis_mock(current_value=3)
        from apps.common.security.anomaly_detection import record_token_abuse
        assert record_token_abuse("2.3.4.5") is True

    @patch("apps.common.security.anomaly_detection._redis")
    def test_redis_error_returns_false(self, mock_redis_factory):
        r = MagicMock()
        r.incr.side_effect = Exception("connection error")
        mock_redis_factory.return_value = r
        from apps.common.security.anomaly_detection import record_token_abuse
        assert record_token_abuse("9.9.9.9") is False


class TestCheckImpossibleVelocity:
    @patch("apps.common.security.anomaly_detection._redis")
    def test_first_login_no_alert(self, mock_redis_factory):
        r = _make_redis_mock(current_value=1)
        r.get.return_value = None  # No previous IP.
        mock_redis_factory.return_value = r
        from apps.common.security.anomaly_detection import check_impossible_velocity
        assert check_impossible_velocity(user_id=1, ip="10.0.0.1") is False

    @patch("apps.common.security.anomaly_detection._redis")
    def test_same_ip_no_alert(self, mock_redis_factory):
        r = _make_redis_mock(current_value=1)
        r.get.return_value = "10.0.0.1"
        mock_redis_factory.return_value = r
        from apps.common.security.anomaly_detection import check_impossible_velocity
        assert check_impossible_velocity(user_id=1, ip="10.0.0.1") is False

    @patch("apps.common.security.anomaly_detection._redis")
    def test_different_subnet_alerts(self, mock_redis_factory):
        r = _make_redis_mock(current_value=1)
        r.get.return_value = "192.168.1.1"
        mock_redis_factory.return_value = r
        from apps.common.security.anomaly_detection import check_impossible_velocity
        result = check_impossible_velocity(user_id=1, ip="10.0.0.1")
        assert result is True

    @patch("apps.common.security.anomaly_detection._redis")
    def test_same_subnet_no_alert(self, mock_redis_factory):
        r = _make_redis_mock(current_value=1)
        r.get.return_value = "10.0.0.2"
        mock_redis_factory.return_value = r
        from apps.common.security.anomaly_detection import check_impossible_velocity
        result = check_impossible_velocity(user_id=1, ip="10.0.0.5")
        assert result is False  # Same /16 — not flagged


class TestDifferentSubnet:
    def test_same_subnet_returns_false(self):
        from apps.common.security.anomaly_detection import _different_subnet
        assert _different_subnet("192.168.1.1", "192.168.2.50") is False

    def test_different_subnet_returns_true(self):
        from apps.common.security.anomaly_detection import _different_subnet
        assert _different_subnet("10.0.0.1", "172.16.0.1") is True

    def test_invalid_ip_does_not_raise(self):
        from apps.common.security.anomaly_detection import _different_subnet
        # Invalid IPs should not raise an exception — result is implementation-defined.
        result = _different_subnet("invalid", "also-invalid")
        assert isinstance(result, bool)
