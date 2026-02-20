"""Tests for device-key (ed25519) authentication in gateway RPC.

Covers keypair generation/persistence, device auth block construction,
signature verification, connect param integration, and graceful fallback.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    _b64url,
    _build_connect_params,
    _build_device_auth,
    _ensure_connected,
    _get_or_create_device_keypair,
)


# ---------------------------------------------------------------------------
# _b64url
# ---------------------------------------------------------------------------


def test_b64url_encodes_without_padding() -> None:
    result = _b64url(b"\x00\x01\x02")
    assert "=" not in result
    assert isinstance(result, str)


def test_b64url_is_url_safe() -> None:
    # bytes that would produce + and / in standard base64
    data = b"\xfb\xff\xfe"
    result = _b64url(data)
    assert "+" not in result
    assert "/" not in result


# ---------------------------------------------------------------------------
# _get_or_create_device_keypair
# ---------------------------------------------------------------------------


def test_keypair_generates_new_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )
    private_key, pub_bytes, device_id = _get_or_create_device_keypair()

    assert isinstance(private_key, Ed25519PrivateKey)
    assert len(pub_bytes) == 32  # ed25519 public key is 32 bytes
    assert device_id == hashlib.sha256(pub_bytes).hexdigest()
    assert (tmp_path / "device.key").exists()


def test_keypair_reuses_existing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )
    _, pub_bytes_1, device_id_1 = _get_or_create_device_keypair()
    _, pub_bytes_2, device_id_2 = _get_or_create_device_keypair()

    assert pub_bytes_1 == pub_bytes_2
    assert device_id_1 == device_id_2


def test_keypair_persists_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )
    _get_or_create_device_keypair()

    key_file = tmp_path / "device.key"
    assert key_file.exists()
    assert len(key_file.read_bytes()) == 32  # raw ed25519 private key


def test_keypair_file_has_restricted_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )
    _get_or_create_device_keypair()

    key_file = tmp_path / "device.key"
    mode = key_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_keypair_creates_directory_if_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "nested" / "keys"
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", nested,
    )
    _get_or_create_device_keypair()

    assert nested.exists()
    assert (nested / "device.key").exists()


# ---------------------------------------------------------------------------
# _build_device_auth
# ---------------------------------------------------------------------------


def test_device_auth_block_has_required_fields() -> None:
    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    device_id = hashlib.sha256(pub_bytes).hexdigest()

    block = _build_device_auth(
        token="test-token",
        nonce="test-nonce-abc",
        scopes=["operator.read", "operator.admin"],
        device_id=device_id,
        private_key=private_key,
        pub_bytes=pub_bytes,
    )

    assert block["id"] == device_id
    assert "publicKey" in block
    assert "signature" in block
    assert "signedAt" in block
    assert block["nonce"] == "test-nonce-abc"


def test_device_auth_signature_is_verifiable() -> None:
    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    device_id = hashlib.sha256(pub_bytes).hexdigest()
    scopes = ["operator.read", "operator.admin"]

    block = _build_device_auth(
        token="my-token",
        nonce="my-nonce",
        scopes=scopes,
        device_id=device_id,
        private_key=private_key,
        pub_bytes=pub_bytes,
    )

    # Reconstruct the payload the same way the function does
    import base64

    scopes_str = ",".join(scopes)
    payload = (
        f"v2|{device_id}|gateway-client|ui|operator|"
        f"{scopes_str}|{block['signedAt']}|my-token|my-nonce"
    )
    # Decode the signature from the block
    sig_padded = block["signature"] + "=" * (-len(block["signature"]) % 4)
    signature = base64.urlsafe_b64decode(sig_padded)

    # Verify — raises InvalidSignature if bad
    private_key.public_key().verify(signature, payload.encode())


def test_device_auth_uses_v2_protocol_format() -> None:
    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    device_id = hashlib.sha256(pub_bytes).hexdigest()

    block = _build_device_auth(
        token="t",
        nonce="n",
        scopes=["operator.read"],
        device_id=device_id,
        private_key=private_key,
        pub_bytes=pub_bytes,
    )

    # signedAt should be a millisecond timestamp (13+ digits)
    assert isinstance(block["signedAt"], int)
    assert block["signedAt"] > 1_000_000_000_000


def test_device_auth_with_empty_nonce() -> None:
    """Device auth should work even when nonce is empty (first connect attempt)."""
    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    device_id = hashlib.sha256(pub_bytes).hexdigest()

    block = _build_device_auth(
        token="tok",
        nonce="",
        scopes=["operator.read"],
        device_id=device_id,
        private_key=private_key,
        pub_bytes=pub_bytes,
    )

    assert block["nonce"] == ""
    assert "signature" in block


# ---------------------------------------------------------------------------
# _build_connect_params — device block integration
# ---------------------------------------------------------------------------


def test_connect_params_includes_device_block_when_token_and_nonce(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )
    config = GatewayConfig(url="ws://gw.example/ws", token="my-token")
    params = _build_connect_params(config, nonce="challenge-nonce")

    assert "device" in params
    assert params["device"]["nonce"] == "challenge-nonce"
    assert "id" in params["device"]
    assert "publicKey" in params["device"]
    assert "signature" in params["device"]


def test_connect_params_no_device_block_without_token() -> None:
    config = GatewayConfig(url="ws://gw.example/ws")
    params = _build_connect_params(config, nonce="some-nonce")

    assert "device" not in params


def test_connect_params_device_block_survives_empty_nonce(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )
    config = GatewayConfig(url="ws://gw.example/ws", token="tok")
    params = _build_connect_params(config, nonce="")

    assert "device" in params
    assert params["device"]["nonce"] == ""


def test_connect_params_includes_operator_read_scope() -> None:
    config = GatewayConfig(url="ws://gw.example/ws")
    params = _build_connect_params(config)

    assert "operator.read" in params["scopes"]


def test_connect_params_device_auth_failure_falls_back_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If device keypair generation fails, connect params should still work without device block."""
    def _broken_keypair() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._get_or_create_device_keypair",
        _broken_keypair,
    )
    config = GatewayConfig(url="ws://gw.example/ws", token="tok")
    params = _build_connect_params(config, nonce="n")

    # Should still have auth but no device block
    assert params["auth"] == {"token": "tok"}
    assert "device" not in params


# ---------------------------------------------------------------------------
# _ensure_connected — nonce extraction from connect.challenge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_connected_extracts_nonce_from_challenge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )

    challenge = json.dumps({
        "type": "event",
        "event": "connect.challenge",
        "payload": {"nonce": "server-nonce-xyz"},
    })

    sent_messages: list[str] = []

    class _FakeWs:
        async def send(self, msg: str) -> None:
            sent_messages.append(msg)

        async def recv(self) -> str:
            return json.dumps({"type": "res", "id": "__any__", "result": {"ok": True}})

    fake_ws = _FakeWs()

    # Mock _await_response to avoid real websocket recv loop
    async def _fake_await(ws: object, req_id: str) -> dict:
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._await_response", _fake_await,
    )

    config = GatewayConfig(url="ws://gw.example/ws", token="tok")
    await _ensure_connected(fake_ws, challenge, config)  # type: ignore[arg-type]

    assert len(sent_messages) == 1
    connect_msg = json.loads(sent_messages[0])
    assert connect_msg["method"] == "connect"
    assert connect_msg["params"]["device"]["nonce"] == "server-nonce-xyz"


@pytest.mark.asyncio
async def test_ensure_connected_handles_no_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When first_message is None, nonce should be empty."""
    sent_messages: list[str] = []

    class _FakeWs:
        async def send(self, msg: str) -> None:
            sent_messages.append(msg)

    async def _fake_await(ws: object, req_id: str) -> dict:
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._await_response", _fake_await,
    )

    config = GatewayConfig(url="ws://gw.example/ws")
    await _ensure_connected(_FakeWs(), None, config)  # type: ignore[arg-type]

    connect_msg = json.loads(sent_messages[0])
    assert connect_msg["method"] == "connect"
    # No token means no device block
    assert "device" not in connect_msg["params"]


@pytest.mark.asyncio
async def test_ensure_connected_handles_unexpected_first_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-challenge first message should still proceed with empty nonce."""
    sent_messages: list[str] = []

    class _FakeWs:
        async def send(self, msg: str) -> None:
            sent_messages.append(msg)

    async def _fake_await(ws: object, req_id: str) -> dict:
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._await_response", _fake_await,
    )

    unexpected = json.dumps({"type": "event", "event": "something.else"})
    config = GatewayConfig(url="ws://gw.example/ws", token="tok")
    await _ensure_connected(_FakeWs(), unexpected, config)  # type: ignore[arg-type]

    connect_msg = json.loads(sent_messages[0])
    # Should still connect, device nonce will be empty
    assert connect_msg["method"] == "connect"


@pytest.mark.asyncio
async def test_ensure_connected_handles_bytes_first_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First message as bytes (not str) should be decoded and handled."""
    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._DEVICE_KEY_DIR", tmp_path,
    )

    challenge = json.dumps({
        "type": "event",
        "event": "connect.challenge",
        "payload": {"nonce": "bytes-nonce"},
    }).encode("utf-8")

    sent_messages: list[str] = []

    class _FakeWs:
        async def send(self, msg: str) -> None:
            sent_messages.append(msg)

    async def _fake_await(ws: object, req_id: str) -> dict:
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.openclaw.gateway_rpc._await_response", _fake_await,
    )

    config = GatewayConfig(url="ws://gw.example/ws", token="tok")
    await _ensure_connected(_FakeWs(), challenge, config)  # type: ignore[arg-type]

    connect_msg = json.loads(sent_messages[0])
    assert connect_msg["params"]["device"]["nonce"] == "bytes-nonce"
