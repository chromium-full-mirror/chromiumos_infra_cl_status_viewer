# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CL-Status-Viewer V1 API definitions."""

from __future__ import print_function

import flask

from google.protobuf.json_format import MessageToJson
# pylint: disable=import-error
from six.moves import http_client

import cl_status_server

from common.protos import viewer_message_pb2
from chromite.lib import cros_logging as logging


app = flask.Blueprint('v1', __name__)


@app.route('/index', methods=['GET'])
def Index():
  """Public index page.

  ---
  responses:
    200:
      description: "OK."
  """
  return flask.jsonify({'message': 'ChromeOS CL Viewer'})


@app.route('/internal_index', methods=['GET'])
def InternalIndex():
  """Internal index page (requires API security key).

  ---
  responses:
    200:
      description: "OK."
  """
  return flask.jsonify({'message': 'ChromeOS CL Viewer (internal)'})


@app.route('/gerrit/<gerrit_host>/changes/<int:change_number>'
           '/patches/<int:patch_number>/status',
           methods=['GET'])
def GetCLStatus(gerrit_host, change_number, patch_number):
  """Get status and relevant builds of the CL (requires API security key).

  ---
  definitions:
    - GetCLStatusResponse:
      properties:
        Data:
          type: "string"
          description: "The json string containing the CL, CL status and "
                       "relevant builds."
        Error:
          type: "string"
          description: "The json string containing the error type and error "
                       "messages."
  parameters:
    - description: "The gerrit host of the CL."
      in: path
      name: gerrit_host
      required: true
      type: string
      minimum: 1
    - description: "The change number of the CL."
      in: path
      name: change_number
      required: true
      type: integer
      minimum: 1
    - description: "The patch number (patch set) of the CL."
      in: path
      name: patch_number
      required: true
      type: integer
      minimum: 1
  responses:
    200:
      description: "The CL status and relevant builds in json string format."
      schema:
        $ref: '#/definitions/GetCLStatusResponse'
    400:
      description: "CL format is invalid."
    default:
      description: "Unexpected error."
  """
  change = viewer_message_pb2.Change()
  change.gerrit_host = gerrit_host
  change.change_number = change_number
  change.patch_number = patch_number

  response = viewer_message_pb2.GetCLStatusResponse()
  try:
    status, builds = cl_status_server.GetCLStatusAndBuilds(change)
    data = viewer_message_pb2.Data()
    data.change.CopyFrom(change)
    data.change_status = status
    data.builds.extend(builds)

    response.data.CopyFrom(data)
  except Exception as e:
    logging.error('Exception for getting CL status for change %s: %s',
                  change, e)
    error = response.errors.add()
    error.CopyFrom(ConstructError(e))

  return MessageToJson(response)


def ConstructError(e):
  """Construct the error message from an exception.

  Args:
    e: The exception to display in the response.

  Returns:
    An instance of viewer_message_pb2.Error.
  """
  error = viewer_message_pb2.Error()

  if isinstance(e, cl_status_server.InvalidGerritHost):
    error.status = http_client.BAD_REQUEST
    error.error_type = viewer_message_pb2.Error.ERROR_GERRIT_HOST
    error.details = str(e)
  else:
    error.status = http_client.INTERNAL_SERVER_ERROR
    error.error_type = viewer_message_pb2.Error.ERROR_UNKNOWN
    error.details = str(e)

  return error


@app.errorhandler(http_client.INTERNAL_SERVER_ERROR)
def unexpected_error(e):
  """Handle exceptions by returning swagger-compliant json.

  Args:
    e: The exception to handle.

  Returns:
    A json string containing the error code and the exception message.
  """
  logging.error('An error occured while processing the request: %s.', e)
  response = flask.jsonify({
      'code': http_client.INTERNAL_SERVER_ERROR,
      'message': 'Exception: {}'.format(e)})
  response.status_code = http_client.INTERNAL_SERVER_ERROR
  return response
