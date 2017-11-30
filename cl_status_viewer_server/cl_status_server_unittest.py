# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for cl_status_server."""

from __future__ import print_function

import unittest
import json
import mock

import cl_status_server

from chromite.lib import build_requests
from chromite.lib import clactions
from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import fake_cidb
from chromite.lib.const import waterfall
from common.protos import viewer_message_pb2


BINHOST_PRE_CQ_CONTENT = json.loads(r"""
{
 "build": {
  "status": "SCHEDULED",
  "created_ts": "1507846228795130",
  "canary_preference": "AUTO",
  "tags": [
   "build_type:pre_cq",
   "builder:Generic",
   "cbb_branch:master",
   "cbb_config:binhost-pre-cq",
   "cbb_display_group:Tryjob",
   "cbb_email:test@chromium.org",
   "cbb_master_build_id:"
  ],
  "url": "https://uberchromegw.corp.google.com/i/chromiumos.tryserver/builders/pre_cq/builds/61283",
  "bucket": "master.chromiumos.tryserver",
  "result_details_json": "null",
  "status_changed_ts": "1507846318257790",
  "canary": false,
  "lease_expiration_ts": "1507849845307045",
  "updated_ts": "1507846318258090",
  "created_by": "user:test@google.com",
  "utcnow_ts": "1507846327580340",
  "id": "8965902348753351216",
  "started_ts": "1507846318257790"
 },
 "kind": "buildbucket#resourcesItem",
 "etag": "\"-r4KAq-P_bvansxLIsxZcRh_-kQ/Y_N2HHVJmE6FQl0_K_mKwHXNZzQ\""
}
""")


CYAN_PALADIN_CONTENT = json.loads(r"""
{
 "build": {
  "status": "SCHEDULED",
  "created_ts": "1507846228795130",
  "canary_preference": "AUTO",
  "tags": [
   "board:cyan",
   "bot_id:cros-beefy276-c2",
   "build_type:paladin",
   "builder:cyan-paladin",
   "buildset:cbuildbot/master/master-paladin/2004460",
   "cbb_branch:master",
   "cbb_config:cyan-paladin",
   "cbb_master_build_id:2004460",
   "master:False",
   "master_config:master-paladin"
  ],
  "url": "https://uberchromegw.corp.google.com/i/chromeos/builders/cyan-paladin/builds/4376",
  "bucket": "master.chromeos",
  "result_details_json": "null",
  "status_changed_ts": "1507846318257790",
  "canary": false,
  "lease_expiration_ts": "1507849845307045",
  "updated_ts": "1507846318258090",
  "created_by": "user:test@google.com",
  "utcnow_ts": "1507846327580340",
  "id": "8965902348753351216",
  "started_ts": "1507846318257790"
 },
 "kind": "buildbucket#resourcesItem",
 "etag": "\"-r4KAq-P_bvansxLIsxZcRh_-kQ/Y_N2HHVJmE6FQl0_K_mKwHXNZzQ\""
}
""")


# pylint: disable=protected-access
class CLStatusServerHelperMethodsTests(cros_test_lib.MockTestCase):
  """Tests for CLStatusServer helper methods."""


class CLStatusServerTests(cros_test_lib.MockTestCase):
  """Tests for CLStatusServer."""

  def setUp(self):
    self.db = fake_cidb.FakeCIDBConnection()
    self.buildbucket_client = mock.Mock()
    self.PatchObject(cl_status_server, 'GetCIDBConnection',
                     return_value=self.db)
    self.PatchObject(cl_status_server, 'GetBuildbucketClient',
                     return_value=self.buildbucket_client)

    change_number = 1000
    patch_number = 2
    change_source = constants.CHANGE_SOURCE_EXTERNAL

    self.change = viewer_message_pb2.Change()
    self.change.gerrit_host = constants.EXTERNAL_GERRIT_HOST
    self.change.change_number = change_number
    self.change.patch_number = patch_number

    self.patch = clactions.GerritPatchTuple(
        gerrit_number=change_number,
        patch_number=patch_number,
        internal=change_source == constants.CHANGE_SOURCE_INTERNAL)

    self.pre_cq_launcher_build_id = self.db.InsertBuild(
        'pre-cq-launcher', waterfall.WATERFALL_INTERNAL, 1, 'pre-cq-launcher',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT)

    self.cq_master_build_id = self.db.InsertBuild(
        'master-paladin', waterfall.WATERFALL_INTERNAL, 2, 'master-paladin',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PALADIN_TYPE)

  def _GetCLActions(self, patch):
    return self.db.GetActionsForChanges([patch], ignore_patch_number=False)

  def _VerifyBuild(self, builds, build_name, build_namespace=None,
                   build_id=None, build_status=None, start_time=None,
                   end_time=None, extra_info_build_category=None,
                   extra_info_buildbucket_id=None, extra_info_url=None):

    build = None
    for b in builds:
      if b.build_name == build_name:
        build = b
        break

    self.assertTrue(build is not None, 'No build %s found.' % build_name)

    if build_namespace:
      self.assertEqual(build.build_namespace, build_namespace)
    if build_id:
      self.assertEqual(build.build_id, build_id)
    if build_status:
      self.assertEqual(build.build_status, build_status)
    if start_time:
      self.assertEqual(build.start_time, start_time)
    if end_time:
      self.assertEqual(build.end_time, end_time)
    if extra_info_build_category:
      self.assertEqual(build.extra_build_info.build_category,
                       extra_info_build_category)
    if extra_info_buildbucket_id:
      self.assertEqual(build.extra_build_info.buildbucket_id,
                       extra_info_buildbucket_id)
    if extra_info_url:
      self.assertEqual(build.extra_build_info.url, extra_info_url)

  def testGetBuildCategory(self):
    """Test GetBuildCategory."""
    self.assertEqual(cl_status_server.GetBuildCategory(constants.PRE_CQ_TYPE),
                     viewer_message_pb2.ExtraBuildInfo.PRE_CQ)
    self.assertEqual(cl_status_server.GetBuildCategory(constants.PALADIN_TYPE),
                     viewer_message_pb2.ExtraBuildInfo.CQ)
    self.assertEqual(cl_status_server.GetBuildCategory(constants.PFQ_TYPE),
                     None)

  def testGetChangeSource(self):
    """Test GetChangeSource."""
    self.assertEqual(
        cl_status_server.GetChangeSource(
            'chromium-review.googlesource.com'),
        'external')
    self.assertEqual(
        cl_status_server.GetChangeSource(
            'chrome-internal-review.googlesource.com'),
        'internal')
    self.assertRaises(cl_status_server.InvalidGerritHost,
                      cl_status_server.GetChangeSource, 'invalid_host.com')

  def testTranslateBuildbucketBuildStatus(self):
    """Test _TranslateBuildbucketBuildStatus."""
    self.assertEqual(viewer_message_pb2.Build.PASSED,
                     cl_status_server.TranslateBuildbucketBuildStatus(
                         constants.BUILDBUCKET_BUILDER_STATUS_COMPLETED,
                         constants.BUILDBUCKET_BUILDER_RESULT_SUCCESS))
    self.assertEqual(viewer_message_pb2.Build.SCHEDULED,
                     cl_status_server.TranslateBuildbucketBuildStatus(
                         constants.BUILDBUCKET_BUILDER_STATUS_SCHEDULED, None))

  def testGetStatusReturnsUNKNOWN(self):
    """_GetStatus returns UNKNOWN when no CLActions."""
    cl_actions = self._GetCLActions(self.patch)
    status = cl_status_server._GetStatus(self.patch, cl_actions)
    self.assertEqual(status, viewer_message_pb2.Data.UNKNOWN)

  def testGetStatusReturnsPendingForPreCQ(self):
    """_GetStatus returns PENDING_FOR_PRE_CQ_VALIDATION."""
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    cl_actions = self._GetCLActions(self.patch)
    status = cl_status_server._GetStatus(self.patch, cl_actions)
    self.assertEqual(status,
                     viewer_message_pb2.Data.PENDING_FOR_PRE_CQ_VALIDATION)

  def testGetStatusReturnsPendingForCQ(self):
    """_GetStatus with pre_cq_passed action."""
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_PASSED)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    cl_actions = self._GetCLActions(self.patch)
    status = cl_status_server._GetStatus(self.patch, cl_actions)
    self.assertEqual(status, viewer_message_pb2.Data.PENDING_FOR_CQ_VALIDATION)

  def testGetStatusReturnsSubmitted(self):
    """_GetStatus returns SUBMITTED."""
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_SUBMITTED)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    cl_actions = self._GetCLActions(self.patch)
    status = cl_status_server._GetStatus(self.patch, cl_actions)
    self.assertEqual(status, viewer_message_pb2.Data.SUBMITTED)

  def testGetPreCQBuildsWithoutCLActionsReturnsEmpty(self):
    """_GetPreCQBuilds without cl_actions returns empty."""
    cl_actions = self._GetCLActions(self.patch)
    pre_cq_builds = cl_status_server._GetPreCQBuilds(
        self.patch, cl_actions)
    self.assertEqual(pre_cq_builds, [])

  def testGetPreCQBuildsWithPendingPreCQActionReturnsEmpty(self):
    """_GetPreCQBuilds with CL_ACTION_VALIDATION_PENDING_PRE_CQ action."""
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    cl_actions = self._GetCLActions(self.patch)
    pre_cq_builds = cl_status_server._GetPreCQBuilds(
        self.patch, cl_actions)
    self.assertEqual(pre_cq_builds, [])

  def testGetPreCQBuildsWithPickedUpAction(self):
    """_GetPreCQBuilds with CL_ACTION_PICKED_UP."""
    pre_cq_build_id = self.db.InsertBuild(
        'binhost-pre-cq', waterfall.WATERFALL_TRYBOT, 1, 'binhost-pre-cq',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PRE_CQ_TYPE, buildbucket_id='8965902348753351216')
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_TRYBOT_LAUNCHING,
        reason='binhost-pre-cq', buildbucket_id='8965902348753351216')
    a3 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    a4 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_INFLIGHT)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1, a2])
    self.db.InsertCLActions(pre_cq_build_id, [a3])
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a4])
    cl_actions = self._GetCLActions(self.patch)
    self.buildbucket_client.GetBuildRequest.return_value = (
        BINHOST_PRE_CQ_CONTENT)
    pre_cq_builds = cl_status_server._GetPreCQBuilds(
        self.patch, cl_actions)

    self._VerifyBuild(
        pre_cq_builds,
        'binhost-pre-cq',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_id=str(pre_cq_build_id),
        build_status=viewer_message_pb2.Build.STARTED,
        extra_info_buildbucket_id='8965902348753351216',
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.PRE_CQ)

  def testGetPreCQBuildsWithVerifiedAction(self):
    """_GetPreCQBuilds with CL_ACTION_VERIFIED."""
    pre_cq_build_id = self.db.InsertBuild(
        'binhost-pre-cq', waterfall.WATERFALL_TRYBOT, 1, 'binhost-pre-cq',
        'bot_hostname', status=constants.BUILDER_STATUS_PASSED,
        build_type=constants.PRE_CQ_TYPE, buildbucket_id='bb_id_1')
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    a3 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_INFLIGHT)
    a4 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VERIFIED)
    a5 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_PASSED)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    self.db.InsertCLActions(pre_cq_build_id, [a2])
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a3, a4, a5])

    cl_actions = self._GetCLActions(self.patch)
    pre_cq_builds = cl_status_server._GetPreCQBuilds(
        self.patch, cl_actions)

    self._VerifyBuild(
        pre_cq_builds,
        'binhost-pre-cq',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_id=str(pre_cq_build_id),
        build_status=viewer_message_pb2.Build.PASSED,
        extra_info_buildbucket_id='bb_id_1',
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.PRE_CQ,
        extra_info_url=('https://luci-milo.appspot.com/buildbot/'
                        'chromiumos.tryserver/binhost-pre-cq/1'))

  def testGetPreCQBuildsWithMultiPreCQActions(self):
    """_GetPreCQBuilds with multiple pre-cq cl_actions."""
    pre_cq_build_id_1 = self.db.InsertBuild(
        'pre-cq', waterfall.WATERFALL_TRYBOT, 1, 'binhost-pre-cq',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PRE_CQ_TYPE, buildbucket_id='bb_id_1')
    pre_cq_build_id_2 = self.db.InsertBuild(
        'pre-cq', waterfall.WATERFALL_TRYBOT, 1, 'lumpy-pre-cq',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PRE_CQ_TYPE, buildbucket_id='bb_id_2')

    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='lumpy-pre-cq')
    a3 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    a4 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    a5 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_INFLIGHT)

    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1, a2])
    self.db.InsertCLActions(pre_cq_build_id_1, [a3])
    self.db.InsertCLActions(pre_cq_build_id_2, [a4])
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a5])

    cl_actions = self._GetCLActions(self.patch)
    pre_cq_builds = cl_status_server._GetPreCQBuilds(
        self.patch, cl_actions)

    self._VerifyBuild(
        pre_cq_builds,
        'binhost-pre-cq',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_id=str(pre_cq_build_id_1),
        build_status=viewer_message_pb2.Build.STARTED,
        extra_info_buildbucket_id='bb_id_1',
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.PRE_CQ)
    self._VerifyBuild(
        pre_cq_builds,
        'lumpy-pre-cq',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_id=str(pre_cq_build_id_2),
        build_status=viewer_message_pb2.Build.STARTED,
        extra_info_buildbucket_id='bb_id_2',
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.PRE_CQ)

  def testGetPreCQBuildsWithLaunchedPreCQs(self):
    """_GetPreCQBuilds with launched Pre-CQs."""
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_TRYBOT_LAUNCHING,
        reason='binhost-pre-cq', buildbucket_id='8965902348753351216')
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1, a2])

    self.buildbucket_client.GetBuildRequest.return_value = (
        BINHOST_PRE_CQ_CONTENT)

    cl_actions = self._GetCLActions(self.patch)
    pre_cq_builds = cl_status_server._GetPreCQBuilds(
        self.patch, cl_actions)
    self._VerifyBuild(
        pre_cq_builds,
        'binhost-pre-cq',
        build_status=viewer_message_pb2.Build.SCHEDULED,
        start_time=1507846318257790,
        extra_info_buildbucket_id='8965902348753351216',
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.PRE_CQ)

  def _InsertPickedUpByMasterCLAction(self):
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    self.db.InsertCLActions(self.cq_master_build_id, [a1])

  def _InsertBuildRequest(self, build_name, buildbucket_id):
    scheduled_build_reqs = [build_requests.BuildRequest(
        None, self.cq_master_build_id, build_name, None, buildbucket_id,
        build_requests.REASON_IMPORTANT_CQ_SLAVE, None)]
    self.db.InsertBuildRequests(scheduled_build_reqs)

  def testGetCQBuildsWithoutMasterCQReturnsEmpty(self):
    """_GetCQBuilds without master CQ returns empty."""
    cq_builds_dict = cl_status_server._GetCQBuilds([])
    self.assertEqual(cq_builds_dict, {})

    self._InsertPickedUpByMasterCLAction()
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_PASSED)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a2])
    cl_actions = self._GetCLActions(self.patch)
    cq_builds_dict = cl_status_server._GetCQBuilds(cl_actions)
    self.assertEqual(cq_builds_dict, {})

  def testGetCQBuildsReturnsMasterCQ(self):
    """_GetCQBuilds without slaves only returns master CQ."""
    self._InsertPickedUpByMasterCLAction()
    cl_actions = self._GetCLActions(self.patch)

    cq_builds = cl_status_server._GetCQBuilds(cl_actions)
    self.assertEqual(len(cq_builds), 1)
    self._VerifyBuild(
        cq_builds,
        'master-paladin',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_id=str(self.cq_master_build_id),
        build_status=viewer_message_pb2.Build.STARTED,
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.CQ,
        extra_info_url=('https://luci-milo.appspot.com/buildbot/chromeos/'
                        'master-paladin/2'))

  def testGetCQBuildsWithScheduledBuilds(self):
    """_GetCQBuilds with scheduled slave builds."""
    self._InsertPickedUpByMasterCLAction()
    self._InsertBuildRequest('cyan-paladin', 'bb_id_1')
    self.buildbucket_client.GetBuildRequest.return_value = (
        CYAN_PALADIN_CONTENT)

    cl_actions = self._GetCLActions(self.patch)
    cq_builds = cl_status_server._GetCQBuilds(cl_actions)
    self.assertEqual(len(cq_builds), 2)
    self._VerifyBuild(
        cq_builds,
        'cyan-paladin',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_status=viewer_message_pb2.Build.SCHEDULED,
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.CQ,
        extra_info_buildbucket_id='bb_id_1',
        extra_info_url=('https://uberchromegw.corp.google.com/i/chromeos/'
                        'builders/cyan-paladin/builds/4376'))

  def testGetCQBuildsWithStartedBuilds(self):
    """_GetCQBuilds with started slave builds."""
    self._InsertPickedUpByMasterCLAction()
    self._InsertBuildRequest('cyan-paladin', 'bb_id_1')
    self.buildbucket_client.GetBuildRequest.return_value = (
        CYAN_PALADIN_CONTENT)

    cyan_build_id = self.db.InsertBuild(
        'cyan-paladin', waterfall.WATERFALL_INTERNAL, 1, 'cyan-paladin',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PALADIN_TYPE, buildbucket_id='bb_id_1',
        master_build_id=self.cq_master_build_id)

    cl_actions = self._GetCLActions(self.patch)
    cq_builds = cl_status_server._GetCQBuilds(cl_actions)
    self.assertEqual(len(cq_builds), 2)

    self._VerifyBuild(
        cq_builds,
        'cyan-paladin',
        build_namespace=viewer_message_pb2.Build.CROS_BUILD,
        build_id=str(cyan_build_id),
        build_status=viewer_message_pb2.Build.STARTED,
        extra_info_build_category=viewer_message_pb2.ExtraBuildInfo.CQ,
        extra_info_buildbucket_id='bb_id_1',
        extra_info_url=('https://luci-milo.appspot.com/buildbot/chromeos/'
                        'cyan-paladin/1'))

  def testGetCQBuildsWithIrrelevantBuilds(self):
    """_GetCQBuilds with irrelevant slaves."""
    self._InsertPickedUpByMasterCLAction()
    self._InsertBuildRequest('cyan-paladin', 'bb_id_1')
    self.buildbucket_client.GetBuildRequest.return_value = (
        CYAN_PALADIN_CONTENT)

    cyan_build_id = self.db.InsertBuild(
        'cyan-paladin', waterfall.WATERFALL_TRYBOT, 1, 'cyan-paladin',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PALADIN_TYPE, buildbucket_id='bb_id_1',
        master_build_id=self.cq_master_build_id)

    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_IRRELEVANT_TO_SLAVE)
    self.db.InsertCLActions(cyan_build_id, [a1, a2])

    cl_actions = self._GetCLActions(self.patch)
    cq_builds = cl_status_server._GetCQBuilds(cl_actions)
    self.assertEqual(len(cq_builds), 1)
    self._VerifyBuild(cq_builds, 'master-paladin')

  def testGetCLStatusAndBuildsWithNoActions(self):
    """GetCLStatusAndBuilds without cl actions."""
    status, builds = cl_status_server.GetCLStatusAndBuilds(self.change)
    self.assertEqual(status, viewer_message_pb2.Data.UNKNOWN)
    self.assertEqual(builds, [])

  def testGetCLStatusAndBuildsWithPreCQActions(self):
    """GetCLStatusAndBuilds with Pre-CQ actions."""
    pre_cq_build_id = self.db.InsertBuild(
        'pre-cq', waterfall.WATERFALL_TRYBOT, 1, 'binhost-pre-cq',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PRE_CQ_TYPE, buildbucket_id='bb_id_1')
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    self.db.InsertCLActions(pre_cq_build_id, [a2])

    status, builds = cl_status_server.GetCLStatusAndBuilds(self.change)
    self.assertEqual(status,
                     viewer_message_pb2.Data.PENDING_FOR_PRE_CQ_VALIDATION)
    self.assertItemsEqual([x.build_name for x in builds], ['binhost-pre-cq'])

  def testGetCLStatusAndBuildsWithPreCQAndCQActions(self):
    """GetCLStatusAndBuilds with Pre-CQ and CQ actions."""
    pre_cq_build_id = self.db.InsertBuild(
        'pre-cq', waterfall.WATERFALL_TRYBOT, 1, 'binhost-pre-cq',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PRE_CQ_TYPE, buildbucket_id='bb_id_1')
    a1 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_VALIDATION_PENDING_PRE_CQ,
        reason='binhost-pre-cq')
    a2 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PICKED_UP)
    a3 = clactions.CLAction.FromGerritPatchAndAction(
        self.patch, constants.CL_ACTION_PRE_CQ_PASSED)
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a1])
    self.db.InsertCLActions(pre_cq_build_id, [a2])
    self.db.InsertCLActions(self.pre_cq_launcher_build_id, [a3])

    self._InsertPickedUpByMasterCLAction()
    self._InsertBuildRequest('cyan-paladin', 'bb_id_1')
    self._InsertBuildRequest('lumpy-paladin', 'bb_id_1')
    self.buildbucket_client.GetBuildRequest.return_value = (
        CYAN_PALADIN_CONTENT)
    self.db.InsertBuild(
        'cyan-paladin', waterfall.WATERFALL_INTERNAL, 1, 'cyan-paladin',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PALADIN_TYPE, buildbucket_id='bb_id_1',
        master_build_id=self.cq_master_build_id)
    self.db.InsertBuild(
        'lumpy-paladin', waterfall.WATERFALL_INTERNAL, 1, 'lumpy-paladin',
        'bot_hostname', status=constants.BUILDER_STATUS_INFLIGHT,
        build_type=constants.PALADIN_TYPE, buildbucket_id='bb_id_2',
        master_build_id=self.cq_master_build_id)

    status, builds = cl_status_server.GetCLStatusAndBuilds(self.change)
    self.assertEqual(status, viewer_message_pb2.Data.PENDING_FOR_CQ_VALIDATION)
    self.assertItemsEqual([x.build_name for x in builds],
                          ['binhost-pre-cq', 'master-paladin', 'cyan-paladin',
                           'lumpy-paladin'])


# TODO: run the unittests in UnitTestStage.cros_run_unit_tests
if __name__ == '__main__':
  unittest.main()
