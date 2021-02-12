# -*- coding: utf-8 -*-
import logging
from brewtils.stoppable_thread import StoppableThread
from datetime import datetime, timedelta
from mongoengine import Q
from typing import List, Tuple

from beer_garden.db.mongo.models import Request, File


class MongoPruner(StoppableThread):
    def __init__(self, tasks=None, run_every=None):
        self.logger = logging.getLogger(__name__)
        self.display_name = "Mongo Pruner"
        self._run_every = (run_every or timedelta(minutes=15)).total_seconds()
        self._tasks = tasks or []

        super(MongoPruner, self).__init__(logger=self.logger, name="Remover")

    def add_task(
        self, collection=None, field=None, delete_after=None, additional_query=None
    ):
        self._tasks.append(
            {
                "collection": collection,
                "field": field,
                "delete_after": delete_after,
                "additional_query": additional_query,
            }
        )

    def run(self):
        self.logger.debug(self.display_name + " is started")

        while not self.wait(self._run_every):
            current_time = datetime.utcnow()

            for task in self._tasks:
                delete_older_than = current_time - task["delete_after"]

                query = Q(**{task["field"] + "__lt": delete_older_than})
                if task.get("additional_query", None):
                    query = query & task["additional_query"]

                self.logger.debug(
                    "Removing %ss older than %s"
                    % (task["collection"].__name__, str(delete_older_than))
                )
                task["collection"].objects(query).no_cache().delete()

        self.logger.debug(self.display_name + " is stopped")

    @staticmethod
    def determine_tasks(**kwargs) -> Tuple[List[dict], int]:
        """Determine tasks and run interval from TTL values

        Args:
            kwargs: TTL values for the different task types. Valid kwarg keys are:
                - info
                - action

        Returns:
            A tuple that contains:
                - A list of task configurations
                - The suggested interval between runs

        """
        file_ttl = kwargs.get("file", -1)

        prune_tasks = [{
            "collection": Request,
            "field": "expiration_date",
            "delete_after": timedelta(minutes=0),
            "additional_query": (
                                        Q(status="SUCCESS") | Q(status="CANCELED") | Q(status="ERROR")
                                )
                                & Q(has_parent=False),
        }]

        if file_ttl > 0:
            prune_tasks.append(
                {
                    "collection": File,
                    "field": "updated_at",
                    "delete_after": timedelta(minutes=file_ttl),
                    "additional_query": Q(owner_type=None)
                    | (
                        (Q(owner_type__iexact="JOB") | Q(owner_type__iexact="REQUEST"))
                        & Q(owner=None)
                    ),
                }
            )

        # Look at the various TTLs to determine how often to run
        real_ttls = [x for x in kwargs.values() if x > 0]
        run_every = min(real_ttls) / 2 if real_ttls else None

        return prune_tasks, run_every
