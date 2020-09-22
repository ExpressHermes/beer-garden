# -*- coding: utf-8 -*-
from brewtils.errors import ModelValidationError, RequestProcessingError
from brewtils.models import Operation
from brewtils.schema_parser import SchemaParser

from beer_garden.api.http.authorization import authenticated, Permissions
from beer_garden.api.http.base_handler import BaseHandler


class InstanceIdAPI(BaseHandler):
    @authenticated(permissions=[Permissions.INSTANCE_READ])
    async def get(self, instance_id):
        """
        ---
        summary: Retrieve a specific Instance
        parameters:
          - name: instance_id
            in: path
            required: true
            description: The ID of the Instance
            type: string
        responses:
          200:
            description: Instance with the given ID
            schema:
              $ref: '#/definitions/Instance'
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """

        response = await self.client(
            Operation(operation_type="INSTANCE_READ", args=[instance_id])
        )

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(response)

    @authenticated(permissions=[Permissions.INSTANCE_DELETE])
    async def delete(self, instance_id):
        """
        ---
        summary: Delete a specific Instance
        parameters:
          - name: instance_id
            in: path
            required: true
            description: The ID of the Instance
            type: string
        responses:
          204:
            description: Instance has been successfully deleted
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """

        await self.client(
            Operation(operation_type="INSTANCE_DELETE", args=[instance_id])
        )

        self.set_status(204)

    @authenticated(permissions=[Permissions.INSTANCE_UPDATE])
    async def patch(self, instance_id):
        """
        ---
        summary: Partially update an Instance
        description: |
          The body of the request needs to contain a set of instructions detailing the
          updates to apply. Currently the only operations are:

          * initialize
          * start
          * stop
          * heartbeat
          * replace

          ```JSON
          [
            { "operation": "" }
          ]
          ```
        parameters:
          - name: instance_id
            in: path
            required: true
            description: The ID of the Instance
            type: string
          - name: patch
            in: body
            required: true
            description: Instructions for how to update the Instance
            schema:
              $ref: '#/definitions/Patch'
        responses:
          200:
            description: Instance with the given ID
            schema:
              $ref: '#/definitions/Instance'
          400:
            $ref: '#/definitions/400Error'
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """
        patch = SchemaParser.parse_patch(self.request.decoded_body, from_string=True)

        for op in patch:
            operation = op.operation.lower()

            if operation == "initialize":
                runner_id = None
                if op.value:
                    runner_id = op.value.get("runner_id")

                response = await self.client(
                    Operation(
                        operation_type="INSTANCE_INITIALIZE",
                        args=[instance_id],
                        kwargs={"runner_id": runner_id},
                    )
                )

            elif operation == "start":
                response = await self.client(
                    Operation(operation_type="INSTANCE_START", args=[instance_id])
                )

            elif operation == "stop":
                response = await self.client(
                    Operation(operation_type="INSTANCE_STOP", args=[instance_id])
                )

            elif operation == "heartbeat":
                response = await self.client(
                    Operation(
                        operation_type="INSTANCE_UPDATE",
                        args=[instance_id],
                        kwargs={"new_status": "RUNNING"},
                    )
                )

            elif operation == "replace":
                if op.path.lower() == "/status":

                    response = await self.client(
                        Operation(
                            operation_type="INSTANCE_UPDATE",
                            args=[instance_id],
                            kwargs={"new_status": op.value},
                        )
                    )
                else:
                    raise ModelValidationError(f"Unsupported path '{op.path}'")

            elif operation == "update":
                if op.path.lower() == "/metadata":
                    response = await self.client(
                        Operation(
                            operation_type="INSTANCE_UPDATE",
                            args=[instance_id],
                            kwargs={"metadata": op.value},
                        )
                    )
                else:
                    raise ModelValidationError(f"Unsupported path '{op.path}'")

            else:
                raise ModelValidationError(f"Unsupported operation '{op.operation}'")

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(response)


class IdLogAPI(BaseHandler):
    @authenticated(permissions=[Permissions.INSTANCE_UPDATE])
    async def get(self, instance_id):
        """
        ---
        summary: Retrieve a specific Instance
        parameters:
          - name: instance_id
            in: path
            required: true
            description: The ID of the Instance
            type: string
          - name: start_line
            in: query
            required: false
            description: Start line of logs to read from instance
            type: int
          - name: end_line
            in: query
            required: false
            description: End line of logs to read from instance
            type: int
          - name: timeout
            in: query
            required: false
            description: Max seconds to wait for request completion. (-1 = wait forever)
            type: float
            default: -1
        responses:
          200:
            description: Instance with the given ID
            schema:
              $ref: '#/definitions/Instance'
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """
        start_line = self.get_query_argument("start_line", default=None)
        if start_line == "":
            start_line = None
        elif start_line:
            start_line = int(start_line)

        end_line = self.get_query_argument("end_line", default=None)
        if end_line == "":
            end_line = None
        elif end_line:
            end_line = int(end_line)

        response = await self.client(
            Operation(
                operation_type="INSTANCE_LOGS",
                args=[instance_id],
                kwargs={
                    "wait_timeout": float(self.get_argument("timeout", default="-1")),
                    "start_line": start_line,
                    "end_line": end_line,
                },
            ),
            serialize_kwargs={"to_string": False},
        )

        if response["status"] == "ERROR":
            raise RequestProcessingError(response["output"])

        self.set_header("request_id", response["id"])
        self.set_header("Content-Type", "text/plain; charset=UTF-8")

        self.write(response["output"])


class IdQueuesAPI(BaseHandler):
    @authenticated(permissions=[Permissions.QUEUE_READ])
    async def get(self, instance_id):
        """
        ---
        summary: Retrieve queue information for instance
        parameters:
          - name: instance_id
            in: path
            required: true
            description: The instance ID to pull queues for
            type: string
        responses:
          200:
            description: List of queue information objects for this instance
            schema:
              type: array
              items:
                $ref: '#/definitions/Queue'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Queues
        """

        response = await self.client(
            Operation(operation_type="QUEUE_READ_INSTANCE", args=[instance_id])
        )

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(response)


class InstanceAPI(BaseHandler):
    @authenticated(permissions=[Permissions.INSTANCE_READ])
    async def get(self, system_id, instance_name):
        """
        ---
        summary: Retrieve a specific Instance
        parameters:
          - name: system_id
            in: path
            required: true
            description: The ID of the System
            type: string
          - name: instance_name
            in: path
            required: true
            description: The name of the Instance
            type: string
        responses:
          200:
            description: Instance with the given ID
            schema:
              $ref: '#/definitions/Instance'
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """

        response = await self.client(
            Operation(
                operation_type="INSTANCE_READ",
                # args=[instance_id],
                kwargs={
                    "system_id": system_id,
                    "instance_name": instance_name,
                },
            )
        )

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(response)

    @authenticated(permissions=[Permissions.INSTANCE_DELETE])
    async def delete(self, system_id, instance_name):
        """
        ---
        summary: Delete a specific Instance
        parameters:
          - name: system_id
            in: path
            required: true
            description: The ID of the System
            type: string
          - name: instance_name
            in: path
            required: true
            description: The name of the Instance
            type: string
        responses:
          204:
            description: Instance has been successfully deleted
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """

        await self.client(
            Operation(
                operation_type="INSTANCE_DELETE",
                # args=[instance_id],
                kwargs={
                    "system_id": system_id,
                    "instance_name": instance_name,
                },
            )
        )

        self.set_status(204)

    @authenticated(permissions=[Permissions.INSTANCE_UPDATE])
    async def patch(self, system_id, instance_name):
        """
        ---
        summary: Partially update an Instance
        description: |
          The body of the request needs to contain a set of instructions detailing the
          updates to apply. Currently the only operations are:

          * initialize
          * start
          * stop
          * heartbeat
          * replace

          ```JSON
          [
            { "operation": "" }
          ]
          ```
        parameters:
          - name: system_id
            in: path
            required: true
            description: The ID of the System
            type: string
          - name: instance_name
            in: path
            required: true
            description: The name of the Instance
            type: string
          - name: patch
            in: body
            required: true
            description: Instructions for how to update the Instance
            schema:
              $ref: '#/definitions/Patch'
        responses:
          200:
            description: Instance with the given ID
            schema:
              $ref: '#/definitions/Instance'
          400:
            $ref: '#/definitions/400Error'
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """
        patch = SchemaParser.parse_patch(self.request.decoded_body, from_string=True)

        for op in patch:
            operation = op.operation.lower()

            if operation == "initialize":
                runner_id = None
                if op.value:
                    runner_id = op.value.get("runner_id")

                response = await self.client(
                    Operation(
                        operation_type="INSTANCE_INITIALIZE",
                        kwargs={
                            "system_id": system_id,
                            "instance_name": instance_name,
                            "runner_id": runner_id,
                        },
                    )
                )

            elif operation == "start":
                response = await self.client(
                    Operation(
                        operation_type="INSTANCE_START",
                        kwargs={
                            "system_id": system_id,
                            "instance_name": instance_name,
                        },
                    )
                )

            elif operation == "stop":
                response = await self.client(
                    Operation(
                        operation_type="INSTANCE_STOP",
                        kwargs={
                            "system_id": system_id,
                            "instance_name": instance_name,
                        },
                    )
                )

            elif operation == "heartbeat":
                response = await self.client(
                    Operation(
                        operation_type="INSTANCE_UPDATE",
                        kwargs={
                            "system_id": system_id,
                            "instance_name": instance_name,
                            "new_status": "RUNNING",
                        },
                    )
                )

            elif operation == "replace":
                if op.path.lower() == "/status":

                    response = await self.client(
                        Operation(
                            operation_type="INSTANCE_UPDATE",
                            kwargs={
                                "system_id": system_id,
                                "instance_name": instance_name,
                                "new_status": op.value,
                            },
                        )
                    )
                else:
                    raise ModelValidationError(f"Unsupported path '{op.path}'")

            elif operation == "update":
                if op.path.lower() == "/metadata":
                    response = await self.client(
                        Operation(
                            operation_type="INSTANCE_UPDATE",
                            kwargs={
                                "system_id": system_id,
                                "instance_name": instance_name,
                                "metadata": op.value,
                            },
                        )
                    )
                else:
                    raise ModelValidationError(f"Unsupported path '{op.path}'")

            else:
                raise ModelValidationError(f"Unsupported operation '{op.operation}'")

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(response)


class LogAPI(BaseHandler):
    @authenticated(permissions=[Permissions.INSTANCE_UPDATE])
    async def get(self, system_id, instance_name):
        """
        ---
        summary: Retrieve a specific Instance
        parameters:
          - name: system_id
            in: path
            required: true
            description: The ID of the System
            type: string
          - name: instance_name
            in: path
            required: true
            description: The name of the Instance
            type: string
          - name: start_line
            in: query
            required: false
            description: Start line of logs to read from instance
            type: int
          - name: end_line
            in: query
            required: false
            description: End line of logs to read from instance
            type: int
          - name: timeout
            in: query
            required: false
            description: Max seconds to wait for request completion. (-1 = wait forever)
            type: float
            default: -1
        responses:
          200:
            description: Instance with the given ID
            schema:
              $ref: '#/definitions/Instance'
          404:
            $ref: '#/definitions/404Error'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Instances
        """
        start_line = self.get_query_argument("start_line", default=None)
        if start_line == "":
            start_line = None
        elif start_line:
            start_line = int(start_line)

        end_line = self.get_query_argument("end_line", default=None)
        if end_line == "":
            end_line = None
        elif end_line:
            end_line = int(end_line)

        response = await self.client(
            Operation(
                operation_type="INSTANCE_LOGS",
                kwargs={
                    "system_id": system_id,
                    "instance_name": instance_name,
                    "wait_timeout": float(self.get_argument("timeout", default="-1")),
                    "start_line": start_line,
                    "end_line": end_line,
                },
            ),
            serialize_kwargs={"to_string": False},
        )

        if response["status"] == "ERROR":
            raise RequestProcessingError(response["output"])

        self.set_header("request_id", response["id"])
        self.set_header("Content-Type", "text/plain; charset=UTF-8")

        self.write(response["output"])


class QueuesAPI(BaseHandler):
    @authenticated(permissions=[Permissions.QUEUE_READ])
    async def get(self, system_id, instance_name):
        """
        ---
        summary: Retrieve queue information for instance
        parameters:
          - name: system_id
            in: path
            required: true
            description: The ID of the System
            type: string
          - name: instance_name
            in: path
            required: true
            description: The name of the Instance
            type: string
        responses:
          200:
            description: List of queue information objects for this instance
            schema:
              type: array
              items:
                $ref: '#/definitions/Queue'
          50x:
            $ref: '#/definitions/50xError'
        tags:
          - Queues
        """

        response = await self.client(
            Operation(
                operation_type="QUEUE_READ_INSTANCE",
                kwargs={"system_id": system_id, "instance_name": instance_name},
            )
        )

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(response)
