# -*- coding: utf-8 -*-

# Copyright 2014,  Digital Reasoning
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

__version_info__ = (0, 6, 1, 'beta', 0)


def get_version(version=None):
    """Returns a PEP 386-compliant version number from VERSION.

    Created by modifying django.utils.version.get_version"""

    # Now build the two parts of the version number:
    # major = X.Y[.Z]
    # sub = .devN - for pre-alpha releases
    #     | {a|b|c}N - for alpha, beta and rc releases

    major = get_major_version(version)

    sub = ''

    if version[3] != 'final':
        mapping = {'alpha': 'a', 'beta': 'b', 'rc': 'c'}
        sub = mapping[version[3]] + str(version[4])

    return str(major + sub)


def get_major_version(version):
    "Returns major version from VERSION."
    parts = 2 if version[2] == 0 else 3
    major = '.'.join(str(x) for x in version[:parts])
    return major


__version__ = get_version(__version_info__)
