from copy import deepcopy

import logging
from brewtils.models import Event, Events

import beer_garden.log
import beer_garden.requests
import beer_garden.router
import beer_garden.config as config
from beer_garden.api.stomp.transport import Connection, parse_header_list
from beer_garden.events import publish
from beer_garden.events.processors import BaseProcessor

logger = logging.getLogger(__name__)


class StompManager(BaseProcessor):
    """Manages Stomp connections and events for the Stomp entry point

    Will poll the multiprocessing.Connection for incoming events, and will invoke the
    handle_event method for any received.

    Also functions as the entry point's Event Manager. It simply sends any generated
    events across the multiprocessing.Connection.

    """

    def __init__(self, ep_conn):
        super().__init__(
            action=lambda item: self.ep_conn.send(item),
            name="StompManager",
            logger_name=".".join([self.__module__, self.__class__.__name__]),
        )

        self.conn_dict = {}
        self.ep_conn = ep_conn

    def add_connection(
        self, stomp_config=None, name: str = None, garden_name: str = None
    ) -> None:
        """Adds a connection

        Args:
            stomp_config: The connection configuration
            name: The connection name
            garden_name: The garden reachable using this connection

        Returns:
            None
        """
        if name in self.conn_dict:
            if garden_name not in self.conn_dict[name]["gardens"]:
                self.conn_dict[name]["gardens"].append(garden_name)
        else:
            conn = Connection(
                host=stomp_config.get("host"),
                port=stomp_config.get("port"),
                send_destination=stomp_config.get("send_destination"),
                subscribe_destination=stomp_config.get("subscribe_destination"),
                ssl=stomp_config.get("ssl"),
                username=stomp_config.get("username"),
                password=stomp_config.get("password"),
            )
            conn.connect()

            self.conn_dict[name] = {
                "conn": conn,
                "gardens": [garden_name],
                "headers": parse_header_list(stomp_config.get("headers")),
            }

    def run(self):
        while not self.stopped():
            if self.ep_conn.poll(0.1):
                self.handle_event(self.ep_conn.recv())

    def shutdown(self):
        self.logger.debug("Disconnecting connections")
        for value in self.conn_dict.values():
            value["conn"].disconnect()

        # This will almost definitely not be published because
        # it would need to make it up to the main process and
        # back down into this process. We just publish this
        # here in case the main process is looking for it.
        publish(
            Event(
                name=Events.ENTRY_STOPPED.name,
                metadata={"entry_point_type": "STOMP"},
            ),
        )

    def remove_garden_from_list(self, garden_name=None):
        """removes garden name from dict list of gardens for stomp subscriptions"""
        for key, value in self.conn_dict.items():
            if garden_name in value["gardens"]:
                logger.debug(f"Removing garden {garden_name} from connection {key}")
                value["gardens"].remove(garden_name)

            # If the list of gardens reachable is now empty, disconnect and remove
            if not value["gardens"]:
                logger.debug(f"Garden list for {key} is empty, disconnecting")
                value["conn"].disconnect()
                self.conn_dict.pop(key)

    def _event_handler(self, event):
        """Internal event handler"""
        if not event.error:
            if event.name == Events.GARDEN_REMOVED.name:
                self.remove_garden_from_list(garden_name=event.payload.name)

            elif (
                event.name == Events.GARDEN_UPDATED.name
                and event.garden == config.get("garden.name")
                and event.payload.connection_type
                and event.payload.connection_type.casefold() == "stomp"
            ):
                logger.debug(f"Garden update: {event.payload.name}")
                self.remove_garden_from_list(garden_name=event.payload.name)

                stomp_config = deepcopy(
                    event.payload.connection_params.get("stomp", {})
                )
                stomp_config["send_destination"] = None

                self.add_connection(stomp_config=stomp_config, name=event.payload.name)

        # Send events to the Connection's send_destination
        for connection_dict in self.conn_dict.values():
            conn = connection_dict["conn"]
            if conn and conn.is_connected():
                conn.send(event, headers=connection_dict.get("headers"))

    def handle_event(self, event):
        """Main event entry point

        This registers handlers that this entry point needs to care about.

        - All entry points need the router and log handlers
        - You might think that the requests handler isn't needed since the stomp entry
        point specifically doesn't support wait events. However, the request validator
        does use wait events internally, so we still need it.
        - And then the actually event handler logic for this entry point

        """
        for handler in [
            beer_garden.router.handle_event,
            beer_garden.log.handle_event,
            beer_garden.requests.handle_event,
            self._event_handler,
        ]:
            try:
                handler(event)
            except Exception as ex:
                logger.exception(f"Error executing callback for {event!r}: {ex}")
