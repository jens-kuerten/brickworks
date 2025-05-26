import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BaseSignal(BaseModel):
    """
    Base class for signals. All signals should inherit from this class.
    """

    pass


C = TypeVar("C", bound=BaseSignal)


class Signals:
    """
    Signal system for connecting and emitting events with type-safe signal classes.

    Usage:
        @signal.connect(MySignal)
        def my_listener(sig: MySignal):
            ...
        await signal.emit(MySignal(...))
    """

    def __init__(self) -> None:
        """
        Initialize the Signals system.
        """
        self.listeners: dict[type[BaseSignal], list[Callable[..., None | Awaitable[None]]]] = {}

    def connect(
        self, signal_type: type[C]
    ) -> Callable[[Callable[[C], None | Awaitable[None]]], Callable[[C], None | Awaitable[None]]]:
        """
        Register a listener for a specific signal type.
        The listener function must accept a single argument of the signal type.
        Usage:
            @signal.connect(MySignal)
            def on_my_signal(sig: MySignal):
                ...
        """

        def decorator(listener: Callable[[C], None | Awaitable[None]]) -> Callable[[C], None | Awaitable[None]]:
            self.listeners.setdefault(signal_type, []).append(listener)
            return listener

        return decorator

    async def emit(self, sig: BaseSignal) -> None:
        """
        Emit a signal instance, calling all registered listeners.
        Usage:
            await signal.emit(MySignal(...))
        """
        signal_type = type(sig)
        for listener in self.listeners.get(signal_type, []):
            if asyncio.iscoroutinefunction(listener):
                await listener(sig)
            else:
                listener(sig)

    def disconnect(self, listener: Callable[[C], None | Awaitable[None]]) -> None:
        """
        Disconnect a previously registered listener from all signal types.
        Usage:
            signal.disconnect(my_listener)
        """
        for listeners in self.listeners.values():
            if listener in listeners:
                listeners.remove(listener)

    async def emit_no_except(self, sig: BaseSignal) -> None:
        """
        Emit a signal instance, calling all registered listeners.
        Exceptions in listeners are caught and logged.
        Usage:
            await signal.emit_no_except(MySignal(...))
        """
        signal_type = type(sig)
        for listener in self.listeners.get(signal_type, []):
            if asyncio.iscoroutinefunction(listener):
                try:
                    await listener(sig)
                except Exception as e:
                    logger.error(f"Error firing signal {signal_type}: {e}")
            else:
                try:
                    listener(sig)
                except Exception as e:
                    logger.error(f"Error firing signal {signal_type}: {e}")


signals: Signals = Signals()
