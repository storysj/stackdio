import logging
import collections
import socket

from django.conf import settings
from django.db import models, transaction
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

import yaml
import model_utils.models

from django_extensions.db.models import TimeStampedModel, TitleSlugDescriptionModel
from model_utils import Choices

from core.fields import DeletingFileField
from cloud.models import CloudProfile, CloudInstanceSize

logger = logging.getLogger(__name__)


def get_map_file_path(obj, filename):
    return "stacks/{0}/{1}.map".format(obj.user.username, obj.slug)


class StatusDetailModel(model_utils.models.StatusModel):
    status_detail = models.TextField(blank=True)

    class Meta:
        abstract = True


class StackManager(models.Manager):

    @transaction.commit_on_success
    def create_stack(self, user, data):
        '''
        data is a JSON object that looks something like:

        {
            "title": "Abe's CDH4 Cluster",
            "description": "Abe's personal cluster for testing CDH4 and stuff...",
            "hosts": [
                {
                    "host_count": 1,
                    "host_size": 1,         # what instance_size object to use
                    "host_pattern": "foo",  # the naming pattern for the host's
                                            # hostname, in this case the hostname
                                            # would become 'foo-1'
                    "cloud_profile": 1,     # what cloud_profile object to use
                    "salt_roles": [1,2,3],  # what salt_roles to use
                    "host_security_groups": "foo,bar,baz",
                },
                {
                    ...
                    more hosts
                    ...
                }
            ]
        }
        '''

        stack_obj = self.model(title=data['title'],
                               description=data.get('description'),
                               user=user)
        stack_obj.save()

        for host in data['hosts']:
            host_count = host['host_count']
            host_size = host['host_size']
            host_pattern = host['host_pattern']
            cloud_profile = host['cloud_profile']
            salt_roles = host['salt_roles']

            # Get the security group objects
            security_group_objs = [
                SecurityGroup.objects.get_or_create(group_name=g)[0] for
                g in filter(
                    None,
                    set(h.strip() for
                        h in host['host_security_groups'].split(','))
                )]

            # lookup other objects
            role_objs = SaltRole.objects.filter(id__in=salt_roles)
            cloud_profile_obj = CloudProfile.objects.get(id=cloud_profile)
            host_size_obj = CloudInstanceSize.objects.get(id=host_size)

            # create hosts
            for i in xrange(1, host_count+1):
                host_obj = stack_obj.hosts.create(
                    stack=stack_obj,
                    cloud_profile=cloud_profile_obj,
                    instance_size=host_size_obj,
                    hostname='%s-%d' % (host_pattern, i),
                )

                # set security groups
                host_obj.security_groups.add(*security_group_objs)

                # set roles
                host_obj.roles.add(*role_objs)

        # generate stack
        stack_obj._generate_map_file()

        return stack_obj


class Stack(TimeStampedModel, TitleSlugDescriptionModel, StatusDetailModel):
    STATUS = Choices('pending', 'launching', 'provisioning', 'finished', 'error')

    class Meta:

        unique_together = ('user', 'title')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='stacks')

    map_file = DeletingFileField(
        max_length=255,
        upload_to=get_map_file_path,
        null=True,
        blank=True,
        default=None,
        storage=FileSystemStorage(location=settings.FILE_STORAGE_DIRECTORY))

    objects = StackManager()

    def __unicode__(self):
        return self.title

    def _generate_map_file(self):

        # TODO: Should we store this somewhere instead of assuming
        # the master will always be this box?
        master = socket.getfqdn()

        profiles = collections.defaultdict(list)

        for host in self.hosts.all():
            # load provider yaml to extract default security groups
            cloud_provider = host.cloud_profile.cloud_provider
            cloud_provider_yaml = yaml.safe_load(
                cloud_provider.yaml)[cloud_provider.slug]

            # pull various stuff we need for a host
            roles = [r.role_name for r in host.roles.all()]
            instance_size = host.instance_size.title
            security_groups = set([
                sg.group_name for
                sg in host.security_groups.all()
            ])

            # add in cloud provider security groups
            security_groups.add(*cloud_provider_yaml['securitygroup'])

            profiles[host.cloud_profile.slug].append({
                host.hostname: {
                    'size': instance_size,
                    'securitygroup': list(security_groups),
                    'minion': {
                        'master': master,
                        'grains': {
                            'roles': roles,
                            'stack_id': int(self.id),
                        }
                    },
                }
            })
        map_file_yaml = yaml.safe_dump(dict(profiles),
                                       default_flow_style=False)

        if not self.map_file:
            self.map_file.save(self.slug+'.map', ContentFile(map_file_yaml))
        else:
            with open(self.map_file.file, 'w') as f:
                f.write(map_file_yaml)


class SaltRole(TimeStampedModel, TitleSlugDescriptionModel):
    role_name = models.CharField(max_length=64)

    def __unicode__(self):
        return self.title


class Host(TimeStampedModel):
    # TODO: We should be using generic foreign keys here to a cloud provider
    # specific implementation of a Host object. I'm not exactly sure how this
    # will work, but I think by using Django's content type system we can make
    # it work...just not sure how easy it will be to extend, maintain, etc.

    stack = models.ForeignKey('Stack',
                              related_name='hosts')
    cloud_profile = models.ForeignKey('cloud.CloudProfile',
                                      related_name='hosts')
    instance_size = models.ForeignKey('cloud.CloudInstanceSize',
                                      related_name='hosts')
    roles = models.ManyToManyField('stacks.SaltRole',
                                   related_name='hosts')

    hostname = models.CharField(max_length=64)
    security_groups = models.ManyToManyField('stacks.SecurityGroup',
                                             related_name='hosts')

    def __unicode__(self):
        return self.hostname


class SecurityGroup(TimeStampedModel):
    group_name = models.CharField(max_length=64)