import io
import json

import pytest

from analitix import updates


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v0.10.0", "0.9.0", True),  # no son decimales: 10 > 9
        ("0.9.1", "0.9.0", True),
        ("v1.0.0", "0.9.9", True),
        ("v0.9.0", "0.9.0", False),
        ("0.8.5", "0.9.0", False),
    ],
)
def test_is_newer(latest, current, expected):
    assert updates.is_newer(latest, current) is expected


def _fake_urlopen(payload):
    def fake(req, timeout):
        assert req.full_url == updates.API_URL
        return io.BytesIO(json.dumps(payload).encode())
    return fake


def test_fetch_latest_release(monkeypatch):
    monkeypatch.setattr(
        updates.urllib.request, "urlopen",
        _fake_urlopen([{"tag_name": "v0.10.0", "html_url": "https://example.invalid/r"}]),
    )
    assert updates.fetch_latest_release() == ("0.10.0", "https://example.invalid/r")


def test_fetch_latest_release_without_releases(monkeypatch):
    monkeypatch.setattr(updates.urllib.request, "urlopen", _fake_urlopen([]))
    assert updates.fetch_latest_release() is None
