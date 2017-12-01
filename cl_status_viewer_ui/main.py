# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The frontend server to handle cl_status requests from clients."""

from __future__ import print_function

# pylint: disable=no-name-in-module, import-error
from google.appengine.api import users

import datetime
import jinja2
import json
import httplib2
# pylint: disable=cros-logging-import
import logging
import os
# pylint: disable=import-error
import webapp2


KEYS_PATH = os.environ.get('KEYS_PATH', 'chromeos-cl-viewer-ui-keys.json')
CL_STATUS_PAGE_HTML = 'cl_status_page.html'

PROJECT_BASE_DIR = os.path.dirname(os.path.realpath(__file__))
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(PROJECT_BASE_DIR))
template = env.get_template(CL_STATUS_PAGE_HTML)


def GetAPIKey():
  """Get API key from file.

  Returns:
    A API Key string.

  Raises:
    DeploymentException containing the errors.
  """
  try:
    with open(KEYS_PATH) as f:
      keys = json.loads(f.read())
      return keys['api_key']
  except IOError as e:
    logging.error('Error reading the file %s: %s', KEYS_PATH, e)
    raise DeploymentException(e)
  except KeyError as e:
    logging.error('api_key not found in the file %s: %s', KEYS_PATH, e)
    raise DeploymentException(e)


def GetNicknameAndSessionURL(dest_url='/'):
  """Get user nickname and the login/logout urls.

  Args:
    dest_url: String that is the desired final destination URL. Default to '/'.

  Returns:
    If the current user is logged in, return nick name, "Sign out" string, and
    the url to log out; else, return null, "Sign in" string and a url to log in.
  """
  user = users.get_current_user()
  if user:
    nickname = user.nickname()
    logout_url = users.create_logout_url(dest_url)

    return nickname, "Sign out", logout_url
  else:
    login_url = users.create_login_url(dest_url)

    return None, "Sign in", login_url


class DeploymentException(Exception):
  """The app was deployed with exceptions, fix and re-deploy it."""


class CLStatusViwerServerException(Exception):
  """cl_status_viwer_server returns exceptions, check the server logs."""


# pylint: disable=no-init
class MainPage(webapp2.RequestHandler):
  """Class to serve the main page."""

  def get(self):
    """Handles the GET request on the main page."""
    nick_name, session_page, session_url = GetNicknameAndSessionURL()
    response_str = template.render(nick_name=nick_name,
                                   session_page=session_page,
                                   session_url=session_url)
    self.response.write(response_str)


# pylint: disable=no-init
class CLStatusPage(webapp2.RequestHandler):
  """Class to server the cl_status page."""

  _DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
  _REQUEST_URL_FORMAT = ('https://chromeos-cl-viewer-api.appspot.com/v1/gerrit/'
                         '%s/changes/%d/patches/%d/status?key=%s')

  def get(self, gerrit_host, change_number, patch_number):
    """Handles the GET requests on the cl_status page.

    Args:
      gerrit_host: The gerrit host (string) of the CL to check.
      change_number: The change id (string) of the CL to check.
      patch_number: The patch set (string) of the CL to check.
    """
    api_key = GetAPIKey()
    change_number = int(change_number)
    patch_number = int(patch_number)
    dest_url = '/cl_status/%s/%d/%d' % (
        gerrit_host, change_number, patch_number)

    nick_name, session_page, session_url = GetNicknameAndSessionURL(
        dest_url=dest_url)

    if not nick_name:
      response_str = template.render(
          nick_name=nick_name,
          session_page=session_page,
          session_url=session_url)
      self.response.write(response_str)
      return

    # TODO(nxia): consider requests library as another option.
    http = httplib2.Http()
    request_url = self._REQUEST_URL_FORMAT % (
        gerrit_host, change_number, patch_number, api_key)
    method = 'GET'
    body = None
    headers = {'Content-Type': 'application/json'}
    response, content = http.request(request_url, method, body, headers)

    if int(response['status']) // 100 != 2:
      raise CLStatusViwerServerException(
          'Response %s.\nContent %s.', response, content)

    content_json = json.loads(content)
    data = content_json.get('data')
    if not data:
      errors = content_json.get('errors', [])
      error_rows = []
      for error in errors:
        error_status = error.get('status', '')
        error_type = error.get('errorType', '')
        error_details = error.get('details', '')
        error_rows.append('Status: %s; Error Type: %s; Details: %s' % (
            error_status, error_type, error_details))

      response_str = template.render(
          nick_name=nick_name,
          session_page=session_page,
          session_url=session_url,
          error_rows=error_rows)
      self.response.write(response_str)
      return

    change_url = 'https://%s/%s' % (gerrit_host, change_number)
    change_status = data.get('changeStatus')
    builds = data.get('builds', [])
    build_raws = []
    for build in builds:
      build_name = build.get('buildName', '')
      status = build.get('buildStatus', '')
      build_id = build.get('buildId', '')
      start_time = build.get('startTime', '')
      if start_time:
        start_time = datetime.datetime.fromtimestamp(
            int(start_time)).strftime(self._DATETIME_FORMAT)
      end_time = build.get('endTime', '')
      if end_time:
        end_time = datetime.datetime.fromtimestamp(
            int(end_time)).strftime(self._DATETIME_FORMAT)
      extra_build_info = build.get('extraBuildInfo')
      if extra_build_info:
        buildbucket_id = extra_build_info.get('buildbucketId')
        url = extra_build_info.get('url')
        category = extra_build_info.get('buildCategory', '')

        build_raw = dict(
            build_name=build_name,
            status=status,
            category=category,
            build_id=build_id,
            start_time=start_time,
            end_time=end_time,
            buildbucket_id=buildbucket_id,
            url=url)
        build_raws.append(build_raw)

    response_str = template.render(
        nick_name=nick_name,
        session_page=session_page,
        session_url=session_url,
        change_url=change_url,
        change_status=change_status,
        patch_number=patch_number,
        build_raws=build_raws)
    self.response.write(response_str)


app = webapp2.WSGIApplication([
    ('/', MainPage),
    (r'/cl_status/(\S+)/(\d+)/(\d+)', CLStatusPage)
], debug=True)
