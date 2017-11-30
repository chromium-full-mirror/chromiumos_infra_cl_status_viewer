#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper script to deploy the app."""

from __future__ import print_function

import contextlib
import fire
import jinja2
import os

from chromite.lib import cros_build_lib
from chromite.lib import osutils


PROJECT_BASE_DIR = os.path.dirname(os.path.realpath(__file__))
_APP_TEMPLATE_YAML = 'app_template.yaml'
_APP_YAML = 'app.yaml'
_OPENAPI_YAML = 'openapi-appengine.yaml'
_ENDPOINTS_SERVICE = 'chromeos-cl-viewer-api.appspot.com'


@contextlib.contextmanager
def _PrepareAppFolder():
  """Copies this folder and its symlink'd dependencies into a temporary dir.

  Returns:
    A contextmanager that yields a temporary directory and cleans up afterward.
  """
  with osutils.TempDir() as tempdir:
    # This is rsync in 'archive' mode, but symlinks are followed to copy actual
    # files/directories.
    rsync_cmd = ['rsync', '-qrLgotD',
                 '--exclude', '*.pyc',
                 '--exclude', 'venv', # Needed to avoid infinite chromite loop
                 '--exclude', 'env',  # Our development virtualenv
                 '--exclude', '*.pem', # Sensitive cidb files
                 '--exclude', '*.git']
    cros_build_lib.RunCommand(rsync_cmd + ['.', tempdir], cwd=PROJECT_BASE_DIR)
    yield tempdir


def _FillAppTemplate(tempdir, config_id):
  """Fills the values in app.yaml template.

  Args:
    tempdir: The tempdir where the project was copied to.
    config_id: The config if of the deployed Endpoints Service.
  """
  env = jinja2.Environment(
      loader=jinja2.FileSystemLoader(tempdir))
  contents = env.get_template(_APP_TEMPLATE_YAML).stream(
      endpoints_service_config_id=config_id)
  contents.dump(os.path.join(tempdir, _APP_YAML))


def Main():
  """Deploys the app."""
  with _PrepareAppFolder() as tempdir:
    print('Deployment directory:\n%s ' % tempdir)
    result = cros_build_lib.RunCommand(
        ['gcloud', 'endpoints', 'services', 'deploy', _OPENAPI_YAML],
        cwd=tempdir, mute_output=False)
    result = cros_build_lib.RunCommand(
        ['gcloud', 'endpoints', 'configs', 'list',
         '--service=%s' % _ENDPOINTS_SERVICE, '--limit=1'], cwd=tempdir)
    print('Endpoints configs list:\n%s ' % result.output)
    config = result.output.splitlines()[1]
    config_id = config.split(' ')[0].strip()
    _FillAppTemplate(tempdir, config_id)
    result = cros_build_lib.RunCommand(
        ['gcloud', 'app', 'deploy', _APP_YAML], cwd=tempdir, mute_output=False)


if __name__ == '__main__':
  fire.Fire(Main)
