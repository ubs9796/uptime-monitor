import socket
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from checker import check_http_status, get_ssl_days_left, is_internet_online, validate_url


def test_validate_url_happy_path() -> None:
    assert validate_url("  https://example.com/health  ") == "https://example.com/health"


def test_validate_url_rejects_bad_scheme() -> None:
    with pytest.raises(ValueError):
        validate_url("ftp://example.com")
    with pytest.raises(ValueError):
        validate_url("not-a-url")


def test_check_http_status_200_ok() -> None:
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.__enter__.return_value = mock_resp
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert check_http_status("https://example.com") == (True, 200)


def test_check_http_status_503_down() -> None:
    err = urllib.error.HTTPError("https://example.com", 503, "Service Unavailable", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        assert check_http_status("https://example.com") == (False, 503)


def test_check_http_status_timeout_down() -> None:
    with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
        assert check_http_status("https://example.com") == (False, 0)


def test_get_ssl_days_left_boundary() -> None:
    future_date = (datetime.now(timezone.utc) + timedelta(days=10, hours=2)).strftime("%b %d %H:%M:%S %Y GMT")
    mock_ssock = MagicMock()
    mock_ssock.getpeercert.return_value = {"notAfter": future_date}
    mock_ssock.__enter__.return_value = mock_ssock

    mock_sock = MagicMock()
    mock_sock.__enter__.return_value = mock_sock

    with patch("socket.create_connection", return_value=mock_sock):
        with patch("ssl.SSLContext.wrap_socket", return_value=mock_ssock):
            days = get_ssl_days_left("example.com")
            assert days == 10


def test_get_ssl_days_left_expired() -> None:
    past_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%b %d %H:%M:%S %Y GMT")
    mock_ssock = MagicMock()
    mock_ssock.getpeercert.return_value = {"notAfter": past_date}
    mock_ssock.__enter__.return_value = mock_ssock

    mock_sock = MagicMock()
    mock_sock.__enter__.return_value = mock_sock

    with patch("socket.create_connection", return_value=mock_sock):
        with patch("ssl.SSLContext.wrap_socket", return_value=mock_ssock):
            days = get_ssl_days_left("example.com")
            assert days < 0


def test_is_internet_online_false_when_probe_fails() -> None:
    with patch("checker.check_http_status", return_value=(False, 0)):
        assert is_internet_online() is False
