import enum


class BarPeriod(enum.Enum):
    SECOND = 32
    MINUTE = 33
    HOUR = 34
    DAY = 35


class OrderType(enum.Enum):
    MARKET = enum.auto()
    LIMIT = enum.auto()
    STOP = enum.auto()
    STOP_LIMIT = enum.auto()


class OrderSide(enum.Enum):
    BUY = enum.auto()
    SELL = enum.auto()


class InputSource(enum.Enum):
    OPEN = enum.auto()
    HIGH = enum.auto()
    LOW = enum.auto()
    CLOSE = enum.auto()
    VOLUME = enum.auto()
