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


"""
Amazon Web Services provider for stackd.io
"""

import os
import re
import stat
import logging
from uuid import uuid4
from time import sleep

import requests
from requests.exceptions import ConnectionError
import boto
import boto.ec2
import boto.vpc
import yaml
from boto.route53.record import ResourceRecordSets
from boto.exception import EC2ResponseError

from cloud.providers.base import (
    BaseCloudProvider,
    TimeoutException,
    MaxFailuresException,
)
from core.exceptions import BadRequest, InternalServerError


GROUP_PATTERN = re.compile('\d+:[a-zA-Z0-9-_]')
CIDR_PATTERN = re.compile('[0-9]+(?:\.[0-9]+){3}\/\d{1,2}')

# Boto Errors
BOTO_DUPLICATE_ERROR_CODE = 'InvalidPermission.Duplicate'

logger = logging.getLogger(__name__)

DEFAULT_ROUTE53_TTL = 30


class Route53Domain(object):
    def __init__(self, access_key, secret_key, domain):
        '''
        `access_key`
            The AWS access key id
        `secret_key`
            The AWS secret access key
        `domain`
            An existing Route53 domain to manage
        '''
        self.access_key = access_key
        self.secret_key = secret_key
        self.domain = domain

        # Loaded after connection is made
        self.hosted_zone = None
        self.zone_id = None
        self.rr_sets = None

        self.conn = boto.connect_route53(self.access_key,
                                         self.secret_key)
        self._load_domain()

    def _load_domain(self):
        '''
        Attempts to look up a Route53 hosted zone given a domain name (they're
        much easier to remember than a zone id). Once loaded, pulls out the
        zone id and stores it in `zone_id`
        '''
        # look up the hosted zone based on the domain
        response = self.conn.get_hosted_zone_by_name(self.domain)
        self.hosted_zone = response['GetHostedZoneResponse']['HostedZone']

        # Get the zone id, but strip off the first part /hostedzone/
        self.zone_id = self.hosted_zone['Id'][len('/hostedzone/'):]

    def get_rrnames_set(self, force=False):
        '''
        Returns a cached set of resource record names for our zone id, and
        builds the cached set if we haven't already.
        '''
        if not force and self.rr_sets is not None:
            return self.rr_sets
        self.rr_sets = {}
        for rr in self.conn.get_all_rrsets(self.zone_id):
            self.rr_sets[rr.name] = {
                'type': rr.type,
                'ttl': rr.ttl,
                'value': rr.to_print(),
            }
        return self.rr_sets

    def start_rr_transaction(self):
        '''
        Creates a new Route53 ResourceRecordSets object that is used
        internally like a transaction of sorts. You may add or delete
        many resource records using a single set by calling the
        `add_record` and `delete_record` methods. Finish the transaction
        with `finish_rr_transaction`

        NOTE: Calling this method again before finishing will not finish
        an existing transaction or delete it. To cancel an existing
        transaction use the `cancel_rr_transaction`.
        '''

        if not hasattr(self, '_rr_txn') or self._rr_txn is None:
            # Return a new ResourceRecordSets "transaction"
            self._rr_txn = ResourceRecordSets(self.conn, self.zone_id)

    def finish_rr_transaction(self):
        '''
        If a transaction exists, commit the changes to Route53
        '''
        if self._rr_txn is not None:
            self._rr_txn.commit()
            self._rr_txn = None

    def cancel_rr_transaction(self):
        '''
        Basically deletes the existing transaction.
        '''
        self._rr_txn = None

    def add_record(self, record_name, record_value, record_type,
                   ttl=DEFAULT_ROUTE53_TTL):
        '''
        NOTE: This method must be called after `start_rr_transaction`.

        Adds a new record to the existing resource record transaction.

        `record_name`
            The subdomain part of the record (e.g., web-1 for a domain
            like web-1.dev.example.com)

        `record_value`
            The host or IP the record will point to.

        `record_type`
            The type of the record (CNAME or A)

        `ttl`
            The TTL for the record in seconds, default is 30 seconds
        '''
        # Update the record name to be fully qualified with the domain
        # for this instance. The period on the end is required.
        record_name += '.{0}.'.format(self.domain)

        # Check for an existing record and remove it before
        # updating it
        rr_names = self.get_rrnames_set()
        if record_name in rr_names:
            self._delete_rr_record(record_name,
                                   [rr_names[record_name]['value']],
                                   rr_names[record_name]['type'],
                                   ttl=rr_names[record_name]['ttl'])
            # self._delete_rr_record(record_name,
            #                        [record_value],
            #                        record_type,
            #                        ttl=ttl)

        self._add_rr_record(record_name, [record_value], record_type, ttl=ttl)

    def delete_record(self, record_name, record_value, record_type,
                      ttl=DEFAULT_ROUTE53_TTL):
        '''
        Almost the same as `add_record` but it deletes an existing record

        NOTE: The name, value, and ttl must all match an existing record
        or Route53 will not allow it to be removed.
        '''
        # Update the record name to be fully qualified with the domain
        # for this instance. The period on the end is required.
        record_name += '.{0}.'.format(self.domain)

        # Only remove the record if it exists
        rr_names = self.get_rrnames_set()
        if record_name in rr_names:
            self._delete_rr_record(record_name,
                                   [rr_names[record_name]['value']],
                                   rr_names[record_name]['type'],
                                   ttl=rr_names[record_name]['ttl'])
            # self._delete_rr_record(record_name,
            #                        [record_value],
            #                        record_type,
            #                        ttl=ttl)
            return True
        return False

    def _add_rr_record(self, record_name, record_values, record_type,
                       **kwargs):
        rr = self._rr_txn.add_change('CREATE',
                                     record_name,
                                     record_type,
                                     **kwargs)
        for v in record_values:
            rr.add_value(v)

    def _delete_rr_record(self, record_name, record_values, record_type,
                          **kwargs):
        rr = self._rr_txn.add_change('DELETE',
                                     record_name,
                                     record_type,
                                     **kwargs)
        for v in record_values:
            rr.add_value(v)


class AWSCloudProvider(BaseCloudProvider):
    SHORT_NAME = 'ec2'
    LONG_NAME = 'Amazon Web Services'

    # The account/owner id
    ACCOUNT_ID = 'account_id'

    # The AWS access key id
    ACCESS_KEY = 'access_key_id'

    # The AWS secret access key
    SECRET_KEY = 'secret_access_key'

    # The AWS keypair name
    KEYPAIR = 'keypair'

    # The AWS security groups
    # SECURITY_GROUPS = 'security_groups'

    # The path to the private key for SSH
    PRIVATE_KEY = 'private_key'

    # VPC fields
    VPC_ID = 'vpc_id'
    # VPC_SUBNETS = 'vpc_subnets'

    # The route53 zone to use for managing DNS
    ROUTE53_DOMAIN = 'route53_domain'

    REGION = 'region'

    STATE_STOPPED = 'stopped'
    STATE_RUNNING = 'running'
    STATE_SHUTTING_DOWN = 'shutting-down'
    STATE_TERMINATED = 'terminated'

    @classmethod
    def get_required_fields(self):
        return [
            self.ACCOUNT_ID,
            self.ACCESS_KEY,
            self.SECRET_KEY,
            self.KEYPAIR,
            self.PRIVATE_KEY,
            self.ROUTE53_DOMAIN,
            # self.SECURITY_GROUPS
        ]

    @classmethod
    def get_available_actions(self):
        return [
            self.ACTION_STOP,
            self.ACTION_START,
            self.ACTION_TERMINATE,
            self.ACTION_LAUNCH,
            self.ACTION_PROVISION,
            self.ACTION_ORCHESTRATE,
            self.ACTION_CUSTOM,
        ]

    def get_private_key_path(self):
        return os.path.join(self.provider_storage, 'id_rsa')

    def get_config_file_path(self):
        return os.path.join(self.provider_storage, 'config')

    def get_config(self):
        with open(self.get_config_file_path(), 'r') as f:
            config_data = yaml.safe_load(f)
        return config_data

    def get_credentials(self):
        config_data = self.get_config()
        return config_data['location'], config_data['id'], config_data['key']

    def get_provider_data(self, data, files=None):
        # write the private key to the proper location
        private_key_path = self.get_private_key_path()
        with open(private_key_path, 'w') as f:
            f.write(data[self.PRIVATE_KEY])

        # change the file permissions of the RSA key
        os.chmod(private_key_path, stat.S_IRUSR)

        config_data = {
            'provider': self.SHORT_NAME,
            'id': data[self.ACCESS_KEY],
            'key': data[self.SECRET_KEY],
            'keyname': data[self.KEYPAIR],
            'private_key': private_key_path,
            'append_domain': data[self.ROUTE53_DOMAIN],
            'location': data[self.REGION],

            'ssh_connect_timeout': 300,
            'wait_for_passwd_timeout': 5,
            'rename_on_destroy': True,
            'delvol_on_destroy': True,
        }

        r = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document')

        master_region = r.json()['region']

        if master_region == data[self.REGION]:
            config_data['ssh_interface'] = 'private_ips'
        else:
            config_data['ssh_interface'] = 'public_ips'

        # Save the data out to a file that can be reused by this provider
        # later if necessary
        with open(self.get_config_file_path(), 'w') as f:
            f.write(yaml.safe_dump(config_data, default_flow_style=False))

        return config_data

    # TODO: Ignoring code complexity issues...
    def validate_provider_data(self, data, files=None):  # NOQA

        errors = super(AWSCloudProvider, self) \
            .validate_provider_data(data, files)

        if errors:
            return errors

        # check authentication credentials
        try:
            ec2 = boto.ec2.connect_to_region(
                data[self.REGION],
                aws_access_key_id=data[self.ACCESS_KEY],
                aws_secret_access_key=data[self.SECRET_KEY])
            ec2.get_all_zones()
        except boto.exception.EC2ResponseError, e:
            err_msg = 'Unable to authenticate to AWS with the provided keys.'
            errors.setdefault(self.ACCESS_KEY, []).append(err_msg)
            errors.setdefault(self.SECRET_KEY, []).append(err_msg)

        if errors:
            return errors

        # check keypair
        try:
            ec2.get_all_key_pairs(data[self.KEYPAIR])
        except boto.exception.EC2ResponseError, e:
            errors.setdefault(self.KEYPAIR, []).append(
                'The keypair \'{0}\' does not exist in this account.'
                ''.format(data[self.KEYPAIR])
            )

        # check route 53 domain
        try:
            if self.ROUTE53_DOMAIN in data:
                # connect to route53 and check that the domain is available
                r53 = boto.connect_route53(data[self.ACCESS_KEY],
                                           data[self.SECRET_KEY])
                found_domain = False
                domain = data[self.ROUTE53_DOMAIN]

                hosted_zones = r53.get_all_hosted_zones()
                hosted_zones = \
                    hosted_zones['ListHostedZonesResponse']['HostedZones']
                for hosted_zone in hosted_zones:
                    if hosted_zone['Name'].startswith(domain):
                        found_domain = True
                        break

                if not found_domain:
                    err = 'The Route53 domain \'{0}\' does not exist in ' \
                          'this account.'.format(domain)
                    errors.setdefault(self.ROUTE53_DOMAIN, []).append(err)
        # except boto.exception.DNSServerError, e:
        except Exception, e:
            logger.exception('Route53 issue?')
            errors.setdefault(self.ROUTE53_DOMAIN, []).append(str(e))

        # check VPC required fields
        if self.VPC_ID in data and data[self.VPC_ID]:
            vpc_id = data[self.VPC_ID]

            try:
                vpc = boto.vpc.connect_to_region(
                    data[self.REGION],
                    aws_access_key_id=data[self.ACCESS_KEY],
                    aws_secret_access_key=data[self.SECRET_KEY])
            except boto.exception.EC2ResponseError, e:
                err_msg = ('Unable to authenticate to AWS VPC with the '
                           'provided keys.')
                errors.setdefault(self.ACCESS_KEY, []).append(err_msg)
                errors.setdefault(self.SECRET_KEY, []).append(err_msg)

            if not errors:
                try:
                    vpc.get_all_vpcs([vpc_id])
                except boto.exception.EC2ResponseError, e:
                    errors.setdefault(self.VPC_ID, []).append(
                        'The VPC \'{0}\' does not exist in this account.'
                        .format(vpc_id)
                    )

        return errors

    def validate_image_id(self, image_id):
        ec2 = self.connect_ec2()
        try:
            ec2.get_all_images(image_ids=[image_id])
            return True, ''
        except boto.exception.EC2ResponseError, e:
            return False, e.error_message

    def connect_route53(self):

        # Load the configuration file to get a few things we'll need
        # to manage DNS
        config_data = self.get_config()

        access_key = config_data['id']
        secret_key = config_data['key']
        domain = config_data['append_domain']

        # load a new Route53Domain class and return it
        return Route53Domain(access_key, secret_key, domain)

    def connect_ec2(self):
        if not hasattr(self, '_ec2_connection'):
            region, access_key, secret_key = self.get_credentials()
            self._ec2_connection = boto.ec2.connect_to_region(
                region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key)

        return self._ec2_connection

    def connect_vpc(self):
        if not hasattr(self, '_vpc_connection'):
            region, access_key, secret_key = self.get_credentials()
            self._vpc_connection = boto.vpc.connect_to_region(
                region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key)

        return self._vpc_connection

    def is_cidr_rule(self, rule):
        '''
        Determines if the rule string conforms to the CIDR pattern.
        '''
        return CIDR_PATTERN.match(rule)

    def create_security_group(self,
                              security_group_name,
                              description,
                              delete_if_exists=False):
        '''
        Returns the identifier of the group.
        '''
        if not description:
            description = 'Default description provided by stackd.io'

        if delete_if_exists:
            try:
                self.delete_security_group(security_group_name)
                logger.warn('create_security_group has deleted existing group '
                            '{0} prior to creating it.'.format(
                                security_group_name))
            except BadRequest:
                logger.debug('security group did not already exist')

        # create the group in the VPC or classic
        kwargs = {}
        if self.obj.vpc_id:
            kwargs['vpc_id'] = self.obj.vpc_id

        ec2 = self.connect_ec2()
        group = ec2.create_security_group(security_group_name,
                                          description,
                                          **kwargs)

        return group.id

    def _security_group_rule_to_kwargs(self, rule):
        kwargs = {
            'ip_protocol': rule['protocol'],
            'from_port': rule['from_port'],
            'to_port': rule['to_port'],
        }
        if GROUP_PATTERN.match(rule['rule']):
            src_owner_id, src_group_name = rule['rule'].split(':')
            kwargs['src_security_group_owner_id'] = src_owner_id
            kwargs['src_security_group_name'] = src_group_name
        elif CIDR_PATTERN.match(rule['rule']):
            kwargs['cidr_ip'] = rule['rule']
        else:
            raise Exception('Security group rule \'{0}\' has an invalid '
                            'format.'.format(rule['rule']))
        return kwargs

    def delete_security_group(self, group_name):
        from django.core.exceptions import ObjectDoesNotExist

        if self.obj.vpc_id:
            try:
                sg = self.obj.security_groups.get(name=group_name)
                kwargs = {'group_id': sg.group_id}
            except ObjectDoesNotExist:
                return
        else:
            kwargs = {'name': group_name}

        ec2 = self.connect_ec2()
        try:
            ec2.delete_security_group(**kwargs)
        except boto.exception.EC2ResponseError, e:
            logger.exception('Error deleting security group {0}'.format(
                group_name)
            )
            if e.status == 400:
                raise BadRequest(e.error_message)
            raise InternalServerError(e.error_message)

    def authorize_security_group(self, group_id, rule):
        '''
        @group_id: string, the group id to add the rule to
        @rule: dict {
            'protocol': tcp | udp | icmp
            'from_port': [1-65535]
            'to_port': [1-65535]
            'rule': string (ex. \
                19.38.48.12/32, 0.0.0.0/0, 4328737383:stackdio-group)
        }
        '''
        ec2 = self.connect_ec2()
        kwargs = self._security_group_rule_to_kwargs(rule)
        kwargs['group_id'] = group_id

        try:
            ec2.authorize_security_group(**kwargs)
        except boto.exception.EC2ResponseError, e:
            if e.status == 400:
                if e.error_message.startswith('Unable to find group'):
                    account_id = kwargs['src_security_group_owner_id']
                    err_msg = e.error_message + ' on account \'{0}\''.format(
                        account_id)
                    raise BadRequest(err_msg)
                raise BadRequest(e.error_message)
            raise InternalServerError(e.error_message)

    def revoke_security_group(self, group_id, rule):
        '''
        See `authorize_security_group`
        '''
        ec2 = self.connect_ec2()
        kwargs = self._security_group_rule_to_kwargs(rule)
        kwargs['group_id'] = group_id
        ec2.revoke_security_group(**kwargs)

    def revoke_all_security_groups(self, group_id):
        '''
        Revokes ALL rules on the security group.
        '''
        groups = self.get_security_groups(group_id)
        for group_name, group in groups.iteritems():
            for rule in group['rules']:
                self.revoke_security_group(group_id, rule)

    # FIXME(abe): Ignoring code complexity
    def get_security_groups(self, group_ids=[]):  # NOQA
        if not isinstance(group_ids, list):
            group_ids = [group_ids]

        ec2 = self.connect_ec2()
        groups = ec2.get_all_security_groups(group_ids=group_ids)

        result = {}
        for group in groups:
            if self.obj.vpc_enabled and not group.vpc_id:
                continue
            if not self.obj.vpc_enabled and group.vpc_id:
                continue

            rules_ingress, rules_egress = [], []
            group_rules = [(0, r) for r in group.rules] + \
                [(1, r) for r in group.rules_egress]
            for rule_type, rule in group_rules:
                for grant in rule.grants:
                    if grant.cidr_ip:
                        rule_string = grant.cidr_ip
                    elif grant.name:
                        rule_string = '{0.owner_id}:{0.name}'.format(grant)
                    else:
                        rule_string = None

                    d = {
                        'protocol': rule.ip_protocol,
                        'from_port': rule.from_port,
                        'to_port': rule.to_port,
                        'rule': rule_string,
                    }
                    if rule_type == 0:
                        rules_ingress.append(d)
                    else:
                        rules_egress.append(d)

            result[group.name] = {
                'group_id': group.id,
                'name': group.name,
                'description': group.description,
                'rules': rules_ingress,
                'rules_egress': rules_egress,
                'vpc_id': group.vpc_id,
            }

        return result

    def get_instances_for_group(self, group_id):
        ec2 = self.connect_ec2()

        reservations = ec2.get_all_instances(filters={'group-id': group_id})

        result = []
        for r in reservations:
            for instance in r.instances:
                if instance.state != 'terminated':
                    result.append({
                        'id': instance.id,
                        'dns': instance.dns_name,
                        'name': instance.tags.get('Name', '')
                    })

        return result

    def get_vpc_subnets(self, subnet_ids=[]):
        try:
            vpc = self.connect_vpc()
            subnets = vpc.get_all_subnets(subnet_ids)
            return subnets
        except boto.exception.EC2ResponseError:
            logger.exception('Error looking up subnet_ids: {0}'.format(
                subnet_ids
            ))
            return None

    def has_image(self, image_id):
        '''
        Checks to see if the given ami is available in the account
        '''
        ec2 = self.connect_ec2()
        try:
            ec2.get_all_images(image_id)
            return True, ''
        except boto.exception.EC2ResponseError:
            return False, 'The image id \'{0}\' does not exist in this ' \
                          'account.'.format(image_id)

    def has_snapshot(self, snapshot_id):
        '''
        Checks to see if the given snapshot is available in the account
        '''
        ec2 = self.connect_ec2()
        try:
            ec2.get_all_snapshots(snapshot_id)
            return True, ''
        except boto.exception.EC2ResponseError:
            return False, 'The snapshot id \'{0}\' does not exist in this ' \
                          'account.'.format(snapshot_id)

    def register_dns(self, hosts):
        '''
        Given a list of 'stacks.Host' objects, this method's
        implementation should handle the registration of DNS
        for the given cloud provider (e.g., Route53 on AWS)
        '''
        # Start a resource record "transaction"
        r53_domain = self.connect_route53()
        r53_domain.start_rr_transaction()

        # for each host, create a new record in Route 53
        for host in hosts:
            if self.obj.vpc_id:
                record_value = host.provider_private_ip
                record_type = 'A'
            else:
                record_value = host.provider_dns
                record_type = 'CNAME'

            logger.info('Registering DNS: {0} - {1}'.format(
                host.hostname,
                record_value
            ))

            r53_domain.add_record(host.hostname,
                                  record_value,
                                  record_type,
                                  ttl=DEFAULT_ROUTE53_TTL)

        # Finish the transaction
        r53_domain.finish_rr_transaction()

        # update hosts to include fqdn
        for host in hosts:
            host.fqdn = '{0}.{1}'.format(host.hostname, r53_domain.domain)
            host.save()

    def unregister_dns(self, hosts):
        '''
        Given a list of 'stacks.Host' objects, this method's
        implementation should handle the de-registration of DNS
        for the given cloud provider (e.g., Route53 on AWS)
        '''

        # Start a resource record "transaction"
        r53_domain = self.connect_route53()
        r53_domain.start_rr_transaction()

        # for each host, delete the existing record
        finish = False
        for host in hosts:
            if self.obj.vpc_id:
                record_value = host.provider_private_ip
                record_type = 'A'
            else:
                record_value = host.provider_dns
                record_type = 'CNAME'

            if not record_value:
                logger.warn(
                    'Host {0} has no provider_dns or provider_private_ip...'
                    'skipping DNS deregister.'.format(host)
                )
                continue

            logger.info('Unregistering DNS: {0} - {1}'.format(
                host.hostname,
                record_value
            ))

            if r53_domain.delete_record(host.hostname,
                                        record_value,
                                        record_type,
                                        ttl=DEFAULT_ROUTE53_TTL):
                finish = True

        if finish:
            # Finish the transaction
            r53_domain.finish_rr_transaction()

        # update hosts to remove fqdn
        hosts.update(fqdn='')

    def register_volumes_for_delete(self, hosts):
        ec2 = self.connect_ec2()

        # for each host, modify the instance attribute to enable automatic
        # volume deletion automatically when the host is terminated
        for h in hosts:
            if not h.instance_id:
                logger.warn('Host {0} has no instance ID...skipping volume '
                            'delete.'.format(h))
                continue

            # get current block device mappings
            _, devices = ec2.get_instance_attribute(
                h.instance_id,
                'blockDeviceMapping').popitem()

            # find those devices that aren't already registered for deletion
            # and build a list of the modify strings
            mods = []
            for device_name, device in devices.iteritems():
                if not device.delete_on_termination:
                    mods.append('{0}=true'.format(device_name))

            # use the modify strings to change the existing volumes flag
            if mods:
                ec2.modify_instance_attribute(h.instance_id,
                                              'blockDeviceMapping',
                                              mods)

            # for each volume, rename them so we can create new volumes with
            # the same now, just in case
            for v in h.volumes.all():
                if not v.volume_id:
                    logger.warn('{0!r} missing volume_id. Skipping delete '
                                'retag.'.format(v))
                    continue
                name = 'stackdio::volume::{0!s}-DEL-{1}'.format(v.id,
                                                                uuid4().hex)
                logger.info('tagging volume {0}: {1}'.format(v.volume_id,
                                                             name))
                ec2.create_tags([v.volume_id], {
                    'Name': name,
                })

    def tag_resources(self, stack, hosts=[], volumes=[]):
        ec2 = self.connect_ec2()

        # Tag each volume with a unique name. This makes it easier to view
        # the volumes in the AWS console
        for v in volumes:
            name = 'stackdio::volume::{0!s}'.format(v.id)
            logger.info('tagging volume {0}: {1}'.format(v.volume_id, name))
            ec2.create_tags([v.volume_id], {
                'Name': name,
            })

        # Next tag all resources with a set of common fields
        resource_ids = [v.volume_id for v in volumes] + \
                       [h.instance_id for h in hosts]

        # filter out empty strings
        resource_ids = filter(None, resource_ids)

        if resource_ids:
            logger.info('tagging {0!r}'.format(resource_ids))
            ec2.create_tags(resource_ids, {
                'stack_id': str(stack.id),
                'owner': stack.owner.username,
            })

    def get_ec2_instances(self, hosts):
        ec2 = self.connect_ec2()

        instance_ids = [i.instance_id for i in hosts]
        return [i
                for r in ec2.get_all_instances(instance_ids)
                for i in r.instances]

    @classmethod
    def get_current_instance_data(cls):
        # Get most of the instance data (region, size, etc)
        r = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document')

        if r.status_code != 200:
            raise ConnectionError()

        ret = r.json()

        # Grab the hostnames
        ret['private-hostname'] = requests.get('http://169.254.169.254/latest/meta-data/local-hostname').text
        ret['public-hostname'] = requests.get('http://169.254.169.254/latest/meta-data/public-hostname').text

        return ret

    def _wait(self,
              fun,
              fun_args=None,
              fun_kwargs=None,
              timeout=5 * 60,
              interval=5,
              max_failures=5):
        '''
        Generic function that will call the given function `fun` with
        `fun_args` and `fun_kwargs` until the function returns a valid result
        or the `timeout` or `max_failures` is reached. A valid result is a
        tuple with the first element being boolean True and the second element
        being the return value for `fun`. If False is the first element of the
        tuple it will *not* be considered a failure and the loop will continue
        waiting for a valid result. All exceptions from `fun` will be
        considered failures.
        '''

        if fun_args is None:
            fun_args = ()
        if fun_kwargs is None:
            fun_kwargs = {}

        # start the loop
        while True:
            logger.debug(
                'Calling given method {0!r}. Giving up in '
                '00:{1:02d}:{2:02d}'.format(
                    fun,
                    int(timeout // 60),
                    int(timeout % 60)
                )
            )
            try:
                ok, result = fun(*fun_args, **fun_kwargs)
                if ok:
                    return result
            except Exception:
                logger.exception('Function {0!r} threw exception. Remaining '
                                 'failures: {1}'.format(fun, max_failures))

                max_failures -= 1
                if max_failures <= 0:
                    raise MaxFailuresException(
                        'Too many failures occurred while waiting for '
                        'valid return value. Giving up.'
                    )

            if timeout < 0:
                raise TimeoutException()
            sleep(interval)
            timeout -= interval

    def wait_for_state(self, hosts, state, timeout=5 * 60):
        if not hosts:
            return (True, 'No hosts defined.')

        logger.debug('wait_for_state {0}'.format(hosts))

        try:
            instances = self._wait(
                self._wait_for_state,
                fun_args=(hosts, state),
                timeout=timeout,
            )
            return (True, instances)
        except MaxFailuresException:
            err_msg = 'Max number of failures reached while waiting ' \
                      'for state: {0}'.format(state)
        except TimeoutException:
            err_msg = 'Timeout reached while waiting for state: ' \
                      '{0}'.format(state)

        return (False, err_msg)

    def _wait_for_state(self, hosts, state):
        '''
        Checks if all hosts are in the given state. Returns a 2-element tuple
        with the first element a boolean representing if all hosts are in the
        required state and the second element being the list of EC2 instance
        objects. This method is suitable as a handler for the `_wait` method.
        '''
        logger.debug('_wait_for_state {0}'.format(hosts))
        instances = self.get_ec2_instances(hosts)
        if not instances:
            raise RuntimeError('get_ec2_instances returned zero results!')

        # get the state for all instances
        states = set(i.update() for i in instances)

        # Multiple states found, requirement failed
        if len(states) > 1:
            return False, instances

        # One state found, return true if the state requirement has been met
        return states.pop() == state, instances

    ##
    # ACTION IMPLEMENTATIONS BELOW
    ##

    def _execute_action(self, stack, status, success_state, state_fun,
                        *args, **kwargs):
        '''
        Generic function to handle most all states accordingly. If you need
        custom logic in the state handling, do so in the _action* methods.
        '''
        stack.set_status(status, status,
                         '%s all hosts in this stack.' % status.capitalize())

        hosts = stack.get_hosts()
        instance_ids = [h.instance_id for h in hosts]

        state_fun(instance_ids, *args, **kwargs)

        # Wait for success_state
        try:
            self.wait_for_state(hosts, success_state)
            return True
        except MaxFailuresException:
            logger.error('Max number of failures reached while waiting '
                         'for state: %s' % success_state)
        except TimeoutException:
            logger.error('Timeout reached while waiting for state: '
                         '%s.' % success_state)

        return False

    def _action_stop(self, stack, *args, **kwargs):
        '''
        Stop all of the hosts on the given stack.
        '''
        ec2 = self.connect_ec2()
        return self._execute_action(stack,
                                    stack.STOPPING,
                                    self.STATE_STOPPED,
                                    ec2.stop_instances,
                                    *args,
                                    **kwargs)

    def _action_start(self, stack, *args, **kwargs):
        '''
        Starts all of the hosts on the given stack.
        '''
        ec2 = self.connect_ec2()
        return self._execute_action(stack,
                                    stack.STARTING,
                                    self.STATE_RUNNING,
                                    ec2.start_instances,
                                    *args,
                                    **kwargs)

    def _action_terminate(self, stack, *args, **kwargs):
        '''
        Terminates all of the hosts on the given stack.
        '''
        ec2 = self.connect_ec2()
        return self._execute_action(stack,
                                    stack.TERMINATING,
                                    self.STATE_TERMINATED,
                                    ec2.terminate_instances,
                                    *args,
                                    **kwargs)
    ##
    # END ACTION IMPLEMENTATIONS
    ##
