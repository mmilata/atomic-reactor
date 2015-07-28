"""
Copyright (c) 2015 Red Hat, Inc
All rights reserved.

This software may be modified and distributed under the terms
of the BSD license. See the LICENSE file for details.
"""

from __future__ import unicode_literals

import json
import os
import subprocess
import time

import koji
from atomic_reactor.plugin import PostBuildPlugin
from atomic_reactor.source import GitSource


def get_os():
    cmd = '. /etc/os-release; echo "$ID-$VERSION_ID"'
    try:
        # py3
        return subprocess.getoutput(cmd)
    except AttributeError:
        # py2
        with open('/dev/null', 'r+') as devnull:
            p = subprocess.Popen(cmd,
                                 shell=True,
                                 stdin=devnull,
                                 stdout=subprocess.PIPE,
                                 stderr=devnull)

            (stdout, stderr) = p.communicate()
            return stdout.decode().rstrip()


def get_buildroot():
    buildroot = {
        'id': 1,
        'host': {
            'os': get_os(),
            'arch': os.uname()[4],
        },
        'content_generator': {
            'name': 'osbs',
            'version': 0,
        },
        'container': {
            'type': 'docker',
            'arch': os.uname()[4],
        },
        'tools': [
            {
                'name': 'docker',
                'version': 0,
            }
        ],
        'component_rpms': [],
        'component_archives': [],
        'extra': {},
    }

    return buildroot


class KojiPromotePlugin(PostBuildPlugin):
    """
    Promote this build to Koji
    """

    key = "koji_promote"
    can_fail = False

    def __init__(self, tasker, workflow, hub):
        """
        constructor

        :param tasker: DockerTasker instance
        :param workflow: DockerBuildWorkflow instance
        :param hub: string, koji hub (xmlrpc)
        """
        super(KojiPromotePlugin, self).__init__(tasker, workflow)
        self.xmlrpc = koji.ClientSession(hub)

    def run(self):
        try:
            build_json = json.loads(os.environ["BUILD"])
        except KeyError:
            self.log.error("No $BUILD env variable. Probably not running in build container.")
            raise

        try:
            metadata = build_json["metadata"]
            build_start_time = metadata["creationTimestamp"]
        except KeyError:
            self.log.error("No build metadata")
            raise

        try:
            # Decode UTC RFC3339 date with no fractional seconds
            # (the format we expect)
            start_time_struct = time.strptime(build_start_time,
                                              '%Y-%m-%dT%H:%M:%SZ')
            start_time = str(int(time.mktime(start_time_struct)))
        except ValueError:
            self.log.error("Invalid time format (%s)", build_start_time)
            raise

        name = None
        version = None
        release = None
        for image_name in self.workflow.tagconf.primary_images:
            if '_' in image_name.tag:
                name = image_name.repo
                version, release = image_name.tag.split('_', 1)

        if name is None or version is None or release is None:
            raise RuntimeError('Unable to determine name-version-release')

        source = self.workflow.source
        if not isinstance(source, GitSource):
            raise RuntimeError('git source required')

        buildroot = get_buildroot()

        koji_metadata = {
            'metadata_version': 0,
            'build': {
                'name': name,
                'version': version,
                'release': release,
                'source': "{0}#{1}".format(source.uri, source.commit_id),
                'start_time': start_time,
                'end_time': str(int(time.time()))
            },
            'buildroots': [buildroot],
            'output': [],
        }
        self.xmlrpc.importGeneratedContent(koji_metadata)

