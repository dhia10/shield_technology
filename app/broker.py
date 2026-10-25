"""
Backward-compatibility re-export module for app.broker.
"""

from app.workers.broker import (
    BrokerInterface,
    MemoryMessageBroker,
    message_broker,
)

__all__ = ["BrokerInterface", "MemoryMessageBroker", "message_broker"]
