import pytest

from brickworks.core.signals import BaseSignal, Signals


class TestSignal(BaseSignal):
    value: int


@pytest.mark.asyncio
async def test_sync_listener_called() -> None:
    signals: Signals = Signals()
    called = {}

    @signals.connect(TestSignal)
    def listener(sig: TestSignal) -> None:
        called["value"] = sig.value

    sig = TestSignal(value=42)
    await signals.emit(sig)
    assert called["value"] == 42


@pytest.mark.asyncio
async def test_async_listener_called() -> None:
    signals: Signals = Signals()
    called = {}

    @signals.connect(TestSignal)
    async def listener(sig: TestSignal) -> None:
        called["value"] = sig.value

    sig = TestSignal(value=99)
    await signals.emit(sig)
    assert called["value"] == 99


@pytest.mark.asyncio
async def test_disconnect() -> None:
    signals: Signals = Signals()
    called = {}

    @signals.connect(TestSignal)
    def listener(sig: TestSignal) -> None:
        called["value"] = sig.value

    signals.disconnect(listener)
    sig = TestSignal(value=123)
    await signals.emit(sig)
    assert "value" not in called


@pytest.mark.asyncio
async def test_emit_no_except() -> None:
    signals: Signals = Signals()
    called = {}

    @signals.connect(TestSignal)
    def listener(sig: TestSignal) -> None:
        called["value"] = sig.value
        raise ValueError("fail")

    # Should not raise
    sig = TestSignal(value=1)
    await signals.emit_no_except(sig)
    assert "value" in called
