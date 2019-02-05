# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to retrieve status and relevant builds for CLs."""

from __future__ import print_function

import os
import time

# pylint: disable=import-error, no-name-in-module
from oauth2client.service_account import ServiceAccountCredentials

from chromite.lib import build_requests
from chromite.lib import buildbucket_lib
from chromite.lib import buildstore
from chromite.lib import clactions
from chromite.lib import constants
from chromite.lib import cros_logging as logging
from chromite.lib import factory
from chromite.lib import tree_status
from common.protos import viewer_message_pb2


AUTH_EMAIL_SCOPE = 'https://www.googleapis.com/auth/userinfo.email'

PROJECT_BASE_DIR = os.path.dirname(os.path.realpath(__file__))

CIDB_CREDS = os.environ.get('CIDB_CREDS', 'cidb_creds/prod_cidb_service')
CIDB_CREDS_PATH = os.path.join(PROJECT_BASE_DIR, CIDB_CREDS)

SERVICE_ACCOUNT_JSON = os.environ.get('SERVICE_ACCOUNT_JSON',
                                      'chromeos-cl-viewer-api.json')
SERVICE_ACCOUNT_JSON_PATH = os.path.join(PROJECT_BASE_DIR, SERVICE_ACCOUNT_JSON)

# Dict mapping from cidb build statuses to viewer_message_pb2 build statuses.
CIDB_BUILD_STATUS_DICT = {
    constants.BUILDER_STATUS_INFLIGHT: viewer_message_pb2.Build.STARTED,
    constants.BUILDER_STATUS_PASSED: viewer_message_pb2.Build.PASSED,
    constants.BUILDER_STATUS_FAILED: viewer_message_pb2.Build.FAILED,
    constants.BUILDER_STATUS_ABORTED: viewer_message_pb2.Build.CANCELED,
    constants.BUILDER_STATUS_MISSING: viewer_message_pb2.Build.UNKNOWN,
}


# pylint: disable=unused-argument
def GetTokenFromServiceAccount(**kwargs):
  """Get token from the ServiceAccount credential file.

  Returns:
    The access token string as issued by the authorization server.
  """
  credentials = ServiceAccountCredentials.from_json_keyfile_name(
      SERVICE_ACCOUNT_JSON_PATH, scopes=AUTH_EMAIL_SCOPE)
  return credentials.get_access_token().access_token


def GetBuildCategory(build_type):
  """Get build category given the build type.

  Args:
    build_type: The type of the build.

  Returns:
    A member of ExtraBuildInfo.BuildCategory to categorize the build.
  """
  if build_type == constants.PRE_CQ_TYPE:
    return viewer_message_pb2.ExtraBuildInfo.PRE_CQ
  elif build_type == constants.PALADIN_TYPE:
    return viewer_message_pb2.ExtraBuildInfo.CQ
  else:
    logging.warning('Invalid build_type %s', build_type)
    return viewer_message_pb2.ExtraBuildInfo.UNKNOWN


def GetChangeSource(gerrit_host):
  """Get change source given the gerrit host.

  Args:
    gerrit_host: The gerrit host (string) of the CL.

  Returns:
    The corresponding change_source for the gerrit_host.

  Raises:
    InvalidGerritHost if the gerrit_host is invalid.
  """
  if gerrit_host == constants.EXTERNAL_GERRIT_HOST:
    return constants.CHANGE_SOURCE_EXTERNAL
  elif gerrit_host == constants.INTERNAL_GERRIT_HOST:
    return constants.CHANGE_SOURCE_INTERNAL
  else:
    raise InvalidGerritHost(
        'Gerrit host must be one of %s' %
        ', '.join([constants.EXTERNAL_GERRIT_HOST,
                   constants.INTERNAL_GERRIT_HOST]))


def TranslateBuildbucketBuildStatus(bb_build_status, bb_build_result):
  """Translate buildbucket status to viewer_message_pb2.Build.BuildStatus.

  Args:
    bb_build_status: The build status in the Buildbucket response.
    bb_build_result: The build result in the Buildbucket response.

  Returns:
    The corresponding viewer_message_pb2.Build.BuildStatus.
  """
  if bb_build_status == constants.BUILDBUCKET_BUILDER_STATUS_SCHEDULED:
    return viewer_message_pb2.Build.SCHEDULED
  elif bb_build_status == constants.BUILDBUCKET_BUILDER_STATUS_STARTED:
    return viewer_message_pb2.Build.STARTED
  elif bb_build_status == constants.BUILDBUCKET_BUILDER_STATUS_COMPLETED:
    if bb_build_result == constants.BUILDBUCKET_BUILDER_RESULT_SUCCESS:
      return viewer_message_pb2.Build.PASSED
    elif bb_build_result == constants.BUILDBUCKET_BUILDER_RESULT_FAILURE:
      return viewer_message_pb2.Build.FAILED
    elif bb_build_result == constants.BUILDBUCKET_BUILDER_RESULT_CANCELED:
      return viewer_message_pb2.Build.CANCELED

  return viewer_message_pb2.Build.UNKNOWN


def GetBuildInfoFromCIDBBuild(build_status):
  """Get viewer_message_pb2.Build instance given the CIDB build status.

  Args:
    build_status: A dict of a single build information (see keys in
      cidb.CIDBConnection.BUILD_STATUS_KEYS) in the CIDB.

  Returns:
    An instance of viewer_message_pb2.Build containing the build information.
  """
  build_info = viewer_message_pb2.Build()
  build_info.build_namespace = viewer_message_pb2.Build.CROS_BUILD
  build_info.build_name = build_status['build_config']
  build_info.build_id = str(build_status['id'])
  build_info.build_status = CIDB_BUILD_STATUS_DICT.get(
      build_status['status'], viewer_message_pb2.Build.UNKNOWN)

  if build_status['start_time']:
    build_info.start_time = int(
        time.mktime(build_status['start_time'].timetuple()))
  if build_status['finish_time']:
    build_info.end_time = int(
        time.mktime(build_status['finish_time'].timetuple()))

  build_info.extra_build_info.build_category = GetBuildCategory(
      build_status['build_type'])

  # Old builds may not have buildbucket_id
  if build_status['buildbucket_id']:
    build_info.extra_build_info.buildbucket_id = build_status['buildbucket_id']
    url = tree_status.ConstructLegolandBuildURL(build_status['buildbucket_id'])
  else:
    url = tree_status.ConstructDashboardURL(
        build_status['waterfall'], build_status['builder_name'],
        build_status['build_number'])
  build_info.extra_build_info.url = url

  return build_info


def GetBuildInfoFromBuildbucketBuild(build_config, buildbucket_id,
                                     build_content):
  """Get viewer_message_pb2.Build instance given the Buildbucket build content

  Args:
    build_config: The build config (string) of the build.
    buildbucket_id: The buildbucket if of the build.
    build_content: The content of the build stored in the Buildbucket Server.

  Returns:
    An instance of viewer_message_pb2.Build containing the build information.
  """
  build_info = viewer_message_pb2.Build()
  build_info.build_namespace = viewer_message_pb2.Build.CROS_BUILD
  build_info.build_name = build_config
  build_info.build_status = TranslateBuildbucketBuildStatus(
      buildbucket_lib.GetBuildStatus(build_content),
      buildbucket_lib.GetBuildResult(build_content))

  start_time = buildbucket_lib.GetBuildStartedTS(build_content)
  if start_time:
    build_info.start_time = int(start_time[0:10])

  end_time = buildbucket_lib.GetBuildCompletedTS(build_content)
  if end_time:
    build_info.end_time = int(end_time[0:10])

  build_types = buildbucket_lib.GetBuildTags(build_content, 'build_type')
  if not build_types:
    logging.warning('Build (buildbucket_id: %s) has no build_type tags.',
                    buildbucket_id)
  elif len(build_types) > 1:
    logging.warning('Build (buildbucket_id: %s has more than 1 build_type'
                    ' tags, only the first one will be used.')
  else:
    build_info.extra_build_info.build_category = GetBuildCategory(
        build_types[0])

  build_info.extra_build_info.buildbucket_id = buildbucket_id
  build_info.extra_build_info.url = buildbucket_lib.GetBuildURL(build_content)

  return build_info


def GetLatestCQMasterBuildId(cl_actions):
  """Get the latest CQ master build id given the CL actions.

  Args:
    cl_actions: A list of clactions.CLAction.

  Returns:
    The build id of the latest CQ master which completed after the latest Pre-CQ
    verification.
  """
  master_build_id = None
  for cl_action in reversed(cl_actions):
    # Do not consider CQs completed before the latest Pre-CQ verification.
    if cl_action.action == constants.CL_ACTION_PRE_CQ_PASSED:
      break

    if cl_action.build_config == constants.CQ_MASTER:
      master_build_id = cl_action.build_id
      break

  return master_build_id


# TODO: exclude slaves that passed SyncStage and don't have picked_up actions.
def GetIrrelevantSlaves(cl_actions, slave_statuses):
  """Get slaves which are marked as irrelevant to the CL.

  Args:
    cl_actions: A list of clactions.CLAction of this CL.
    slave_statuses: A list of dicts containing the status and information
      of slaves (see return type of db.GetSlaveStatuses).

  Returns:
    A list of irrelevant slave build configs (string).
  """
  build_ids = set(status['id'] for status in slave_statuses)
  return set(c.build_config for c in cl_actions
             if c.build_id in build_ids and
             c.action == constants.CL_ACTION_IRRELEVANT_TO_SLAVE)

@factory.CachedFunctionCall
def GetBuildStore():
  return buildstore.BuildStore(cidb_creds=CIDB_CREDS_PATH,
                               for_service=True)

@factory.CachedFunctionCall
def GetBuildbucketClient():
  return buildbucket_lib.BuildbucketClient(
      GetTokenFromServiceAccount, buildbucket_lib.BUILDBUCKET_HOST)


def GetCLStatusAndBuilds(change):
  """Get the status and relevant Pre-CQ and CQ builds given a change (CL).

  Args:
    change: A viewer_message_pb2.Change instance.

  Returns:
    A pair of status and builds. status is a memeber of
    viewer_message_pb2.Data.ChangeStatus. builds is a list of
    viewer_message_pb2.Build instances of relevant Pre-CQs and CQs.
  """
  change_source = GetChangeSource(change.gerrit_host)
  db = GetBuildStore().GetCIDBHandle()

  # TODO: check whether the CL patch exsits on Gerrit.
  gerrit_patch = clactions.GerritPatchTuple(
      gerrit_number=change.change_number,
      patch_number=change.patch_number,
      internal=(change_source == constants.CHANGE_SOURCE_INTERNAL))
  cl_actions = db.GetActionsForChanges(
      [gerrit_patch], ignore_patch_number=False)
  status = _GetStatus(gerrit_patch, cl_actions)
  builds = []

  if status == viewer_message_pb2.Data.UNKNOWN:
    # No Pre-CQ or CQ builds for CL in UNKNOWN.
    return status, builds

  builds.extend(_GetPreCQBuilds(gerrit_patch, cl_actions))

  if status == viewer_message_pb2.Data.PENDING_FOR_PRE_CQ_VALIDATION:
    # Return Pre-CQ builds for CL in PENDING_FOR_PRE_CQ_VALIDATION.
    return status, builds

  builds.extend(_GetCQBuilds(cl_actions))

  return status, builds

def _GetStatus(gerrit_patch, cl_actions):
  """Get status given a CL.

  Args:
    gerrit_patch: An instance of clactions.GerritPatchTuple of the CL.
    cl_actions: A list of clactions.CLAction of the CL.

  Returns:
    The status of this CL (a member of viewer_message_pb2.Build.BuildStatus).
  """
  status = None

  if not cl_actions:
    status = viewer_message_pb2.Data.UNKNOWN
  elif cl_actions[-1].action == constants.CL_ACTION_SUBMITTED:
    status = viewer_message_pb2.Data.SUBMITTED
  else:
    pre_cq_status = clactions.GetCLPreCQStatus(gerrit_patch, cl_actions)

    if pre_cq_status != constants.CL_STATUS_PASSED:
      status = viewer_message_pb2.Data.PENDING_FOR_PRE_CQ_VALIDATION
    else:
      status = viewer_message_pb2.Data.PENDING_FOR_CQ_VALIDATION

  return status

def _GetPreCQBuilds(gerrit_patch, cl_actions):
  """Get relevant Pre-CQ builds given a CL

  Args:
    gerrit_patch: An instance of clactions.GerritPatchTuple of the CL.
    cl_actions: A list of clactions.CLAction of the CL.

  Returns:
    A list of viewer_message_pb2.Build instances of the Pre-CQ builds.
  """
  pre_cq_build_dict = {}
  launched_builds = {}
  started_builds = {}
  pre_cq_progress_map = clactions.GetCLPreCQProgress(gerrit_patch, cl_actions)
  for build_config, pre_cq_progress in pre_cq_progress_map.iteritems():
    if (pre_cq_progress.status == constants.CL_PRECQ_CONFIG_STATUS_LAUNCHED
        and pre_cq_progress.buildbucket_id is not None):
      # 'forgiven' status is translated to trybot_launching
      # and the cl_action with 'forgiven' status doesn't have buildbucket_id.
      launched_builds[build_config] = pre_cq_progress.buildbucket_id
    else:
      started_builds[build_config] = pre_cq_progress.build_id

  bs = GetBuildStore()
  buildbucket_client = GetBuildbucketClient()

  if started_builds:
    # Get started builds from CDIB.
    started_build_statuses = bs.GetBuildStatuses(
        build_ids=started_builds.values())
    for build_status in started_build_statuses:
      if build_status['build_type'] != constants.PRE_CQ_TYPE:
        # Filter out Pre-CQ-Launcher builds
        continue

      build_info = GetBuildInfoFromCIDBBuild(build_status)
      pre_cq_build_dict[build_info.build_name] = build_info

  # Get luanched but not started builds from Buildbucket.
  for build_config, buildbucket_id in launched_builds.iteritems():
    if build_config in pre_cq_build_dict:
      # Skip already started builds.
      continue

    build_content = buildbucket_client.GetBuildRequest(
        buildbucket_id, False)
    build_info = GetBuildInfoFromBuildbucketBuild(
        build_config, buildbucket_id, build_content)
    pre_cq_build_dict[build_config] = build_info

  return pre_cq_build_dict.values()

def _GetCQBuilds(cl_actions):
  """Get relevant CQ builds of a CL.

  Args:
    cl_actions: A list of clactions.CLAction of the CL.

  Returns:
    A list of viewer_message_pb2.Build instances of the CQ builds.
  """
  cq_build_dict = {}
  master_build_id = GetLatestCQMasterBuildId(cl_actions)

  if master_build_id is None:
    return cq_build_dict

  bs = GetBuildStore()
  db = bs.GetCIDBHandle()
  buildbucket_client = GetBuildbucketClient()

  # Add CQ master to cq_build_dict
  master_status = bs.GetBuildStatuses(build_ids=[master_build_id])[0]
  cq_build_dict[master_status['build_config']] = (
      GetBuildInfoFromCIDBBuild(master_status))

  # Only get important CQ slaves.
  build_reqs = db.GetBuildRequestsForRequesterBuild(
      master_build_id,
      request_reason=build_requests.REASON_IMPORTANT_CQ_SLAVE)

  scheduled_slaves = {}
  for build_req in build_reqs:
    # De-dup retried builds.
    scheduled_slaves[build_req.request_build_config] = build_req
  scheduled_buildbucket_ids = set(b.request_buildbucket_id
                                  for b in scheduled_slaves.values())

  # Get started CQ slaves.
  started_slave_statuses = db.GetSlaveStatuses(
      master_build_id=master_build_id,
      buildbucket_ids=scheduled_buildbucket_ids)

  irrelevant_slaves = GetIrrelevantSlaves(
      cl_actions, started_slave_statuses)

  for started_slave_status in started_slave_statuses:
    if started_slave_status['build_config'] in irrelevant_slaves:
      logging.debug('Build %s is irrelevant.', started_slave_status)
      continue

    build_info = GetBuildInfoFromCIDBBuild(started_slave_status)
    cq_build_dict[build_info.build_name] = build_info

  # Get scheduled but not started CQ slaves.
  for build_config, slave_build_request in scheduled_slaves.iteritems():
    if build_config in irrelevant_slaves:
      logging.debug('Build %s is irrelevant.', build_config)
      continue
    elif build_config in cq_build_dict:
      logging.debug('Build %s already started.', build_config)
      continue
    else:
      scheduled_buildbucket_id = slave_build_request.request_buildbucket_id
      build_content = buildbucket_client.GetBuildRequest(
          scheduled_buildbucket_id, False)
      build_info = GetBuildInfoFromBuildbucketBuild(
          build_config, scheduled_buildbucket_id, build_content)
      cq_build_dict[build_config] = build_info

  return cq_build_dict.values()


class InvalidGerritHost(Exception):
  """Raised when the gerrit host is invalid."""
