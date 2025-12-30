import abc

from ..core import Consumer, EventBus, Producer
from ..models import events


class Broker(Consumer, Producer, abc.ABC):

    def __init__(self, event_bus: EventBus) -> None:
        Consumer.__init__(self)
        Producer.__init__(self, event_bus)
        event_bus.subscribe(self, events.RequestOrderSubmission)
        event_bus.subscribe(self, events.RequestOrderCancellation)
        event_bus.subscribe(self, events.RequestOrderModification)

    def on_event(self, incoming_event: events.Event) -> None:
        match incoming_event:
            case events.RequestOrderSubmission() as submit_order:
                self.on_submit_order(submit_order)
            case events.RequestOrderCancellation() as cancel_order:
                self.on_cancel_order(cancel_order)
            case events.RequestOrderModification() as modify_order:
                self.on_modify_order(modify_order)

    @abc.abstractmethod
    def on_submit_order(self, event: events.RequestOrderSubmission) -> None:
        pass

    @abc.abstractmethod
    def on_cancel_order(self, event: events.RequestOrderCancellation) -> None:
        pass

    @abc.abstractmethod
    def on_modify_order(self, event: events.RequestOrderModification) -> None:
        pass
