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


import logging

from rest_framework import serializers

from . import models

logger = logging.getLogger(__name__)


class FormulaPropertiesSerializer(serializers.Serializer):
    properties = serializers.Field('properties')

    class Meta:
        model = models.Formula
        fields = ('properties',)


class FormulaComponentSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = models.FormulaComponent
        fields = (
            'id',
            'title',
            'description',
            'formula',
            'sls_path',
        )


class FormulaSerializer(serializers.HyperlinkedModelSerializer):

    owner = serializers.Field()
    components = FormulaComponentSerializer(many=True)
    properties = serializers.HyperlinkedIdentityField(view_name='formula-properties')
    action = serializers.HyperlinkedIdentityField(view_name='formula-action')
    private_git_repo = serializers.Field()

    class Meta:
        model = models.Formula 
        fields = (
            'id',
            'url',
            'title',
            'description',
            'owner',
            'public',
            'git_username',
            'private_git_repo',
            'access_token',
            'uri',
            'root_path',
            'properties',
            'components',
            'created',
            'modified',
            'status',
            'status_detail',
            'action',
        )

