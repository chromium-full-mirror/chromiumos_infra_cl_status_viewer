# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Defines appengine configs."""

from __future__ import print_function

# pylint: disable=no-name-in-module, import-error
from google.appengine.ext import vendor

# Add any libraries install in the "lib" folder.
vendor.add('lib')
