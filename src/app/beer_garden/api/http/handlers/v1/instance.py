from beer_garden.api.http.authorization import authenticated, Permissions
from beer_garden.api.http.base_handler import BaseHandler
from beer_garden.api.http.client import ExecutorClient


class InstanceAPI(BaseHandler):
    @authenticated(permissions=[Permissions.INSTANCE_READ])
    async def get(self, instance_id):
        """
        ---
        summary: Retrieve a specific Instance
        parameters:
          - name: bg-namespace
            in: header
            required: false
            description: Namespace to use
            type: string
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
        async with ExecutorClient() as client:
            thrift_response = await client.getInstance(
                self.request.namespace, instance_id
            )

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(thrift_response)

    @authenticated(permissions=[Permissions.INSTANCE_DELETE])
    async def delete(self, instance_id):
        """
        ---
        summary: Delete a specific Instance
        parameters:
          - name: bg-namespace
            in: header
            required: false
            description: Namespace to use
            type: string
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
        async with ExecutorClient() as client:
            await client.removeInstance(self.request.namespace, instance_id)

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

          ```JSON
          {
            "operations": [
              { "operation": "" }
            ]
          }
          ```
        parameters:
          - name: bg-namespace
            in: header
            required: false
            description: Namespace to use
            type: string
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
        async with ExecutorClient() as client:
            thrift_response = await client.updateInstance(
                self.request.namespace, instance_id, self.request.decoded_body
            )

        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(thrift_response)
