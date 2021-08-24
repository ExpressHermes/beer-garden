from copy import deepcopy

import logging
from brewtils.models import Event, Events

import beer_garden.log
import beer_garden.requests
import beer_garden.router
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
        if stomp_config.get("subscribe_destination"):

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

                self.conn_dict[name] = {"conn": conn, "gardens": [garden_name]}

            if "headers_list" not in self.conn_dict:
                self.conn_dict[name]["headers_list"] = []

            if stomp_config.get("headers"):
                headers = parse_header_list(stomp_config.get("headers"))

                if headers not in self.conn_dict[name]["headers_list"]:
                    self.conn_dict[name]["headers_list"].append(headers)

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

    def remove_garden_from_list(self, garden_name=None, skip_key=None):
        """removes garden name from dict list of gardens for stomp subscriptions"""
        for key in list(self.conn_dict):
            if not key == skip_key:
                if garden_name in self.conn_dict[key]["gardens"]:
                    self.conn_dict[key]["gardens"].remove(garden_name)

                # If the list of gardens reachable is now empty, disconnect and remove
                if not self.conn_dict[key]["gardens"]:
                    self.conn_dict[key]["conn"].disconnect()
                    self.conn_dict.pop(key)

    def _event_handler(self, event):
        """Internal event handler"""
        if not event.error:
            if event.name == Events.GARDEN_REMOVED.name:
                self.remove_garden_from_list(garden_name=event.payload.name)

            elif event.name == Events.GARDEN_UPDATED.name:
                skip_key = None

                if event.payload.connection_type:
                    if event.payload.connection_type.casefold() == "stomp":
                        stomp_config = event.payload.connection_params.get("stomp", {})
                        stomp_config = deepcopy(stomp_config)
                        stomp_config["send_destination"] = None
                        skip_key = self.add_connection(
                            stomp_config=stomp_config, name=event.payload.name
                        )

                self.remove_garden_from_list(
                    garden_name=event.payload.name, skip_key=skip_key
                )

        for value in self.conn_dict.values():
            conn = value["conn"]
            if conn:
                if conn.is_connected():
                    if value["headers_list"]:
                        for headers in value["headers_list"]:
                            conn.send(event, headers=headers)
                    else:
                        conn.send(event)

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
