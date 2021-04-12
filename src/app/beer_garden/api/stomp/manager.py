import logging
from box import Box
from brewtils.models import Event, Events

from beer_garden.api.stomp.transport import Connection, format_connection_params
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

    @staticmethod
    def connect(stomp_config: Box) -> Connection:
        """Create and return a stomp connection """

        conn = Connection(
            host=stomp_config.get("host"),
            port=stomp_config.get("port"),
            send_destination=stomp_config.get("send_destination"),
            subscribe_destination=stomp_config.get("subscribe_destination"),
            ssl=stomp_config.get("ssl"),
            username=stomp_config.get("username"),
            password=stomp_config.get("password"),
        )

        if conn.connect():
            logger.info("Successfully connected")
        else:
            logger.info("Failed to connect")

        return conn

    def __init__(self, ep_conn):
        super().__init__(
            action=lambda item: self.ep_conn.send(item),
            name="StompManager",
            logger_name=".".join([self.__module__, self.__class__.__name__]),
        )

        self.conn_dict = {}
        self.ep_conn = ep_conn

    def add_connection(self, stomp_config=None, name=None, is_main=False):
        if stomp_config.get("subscribe_destination"):
            host_and_ports = [(stomp_config.get("host"), stomp_config.get("port"))]
            subscribe_destination = stomp_config.get("subscribe_destination")

            ssl = stomp_config.get("ssl") or {}
            use_ssl = ssl.get("use_ssl") or False

            conn_dict_key = f"{host_and_ports}{subscribe_destination}{use_ssl}"

            if conn_dict_key in self.conn_dict:
                if {"name": name, "main": is_main} not in self.conn_dict[conn_dict_key][
                    "gardens"
                ]:
                    self.conn_dict[conn_dict_key]["gardens"].append(
                        {"name": name, "main": is_main}
                    )
            else:
                self.conn_dict[conn_dict_key] = {
                    "conn": self.connect(stomp_config),
                    "gardens": [{"name": name, "main": is_main}],
                }

            if "headers_list" not in self.conn_dict:
                self.conn_dict[conn_dict_key]["headers_list"] = []

            if stomp_config.get("headers") and is_main:
                headers = self.convert_header_to_dict(stomp_config.get("headers"))

                if headers not in self.conn_dict[conn_dict_key]["headers_list"]:
                    self.conn_dict[conn_dict_key]["headers_list"].append(headers)

            return conn_dict_key

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
                gardens = self.conn_dict[key]["gardens"]

                for garden in gardens:
                    if garden_name == garden["name"] and not garden["main"]:
                        gardens.remove(garden)

                if not gardens:
                    self.conn_dict[key]["conn"].disconnect()
                    self.conn_dict.pop(key)

    def handle_event(self, event):
        if event.name == Events.GARDEN_REMOVED.name:
            self.remove_garden_from_list(garden_name=event.payload.name)

        elif event.name == Events.GARDEN_UPDATED.name:
            skip_key = None

            if event.payload.connection_type:
                if event.payload.connection_type.casefold() == "stomp":
                    stomp_config = format_connection_params(
                        event.payload.connection_params
                    )
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

    @staticmethod
    def convert_header_to_dict(headers):
        tmp_headers = {}
        key_to_key = None
        key_to_value = None

        for header in headers:
            header = eval(header)

            for key in header.keys():
                if "key" in key:
                    key_to_key = key
                elif "value" in key:
                    key_to_value = key

            tmp_headers[header[key_to_key]] = header[key_to_value]

        return tmp_headers