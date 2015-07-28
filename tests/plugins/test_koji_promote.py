"""
Copyright (c) 2015 Red Hat, Inc
All rights reserved.

This software may be modified and distributed under the terms
of the BSD license. See the LICENSE file for details.
"""

from __future__ import unicode_literals

import json
import os

try:
    import koji
except ImportError:
    import inspect
    import os
    import sys

    # Find out mocked koji module
    mock_koji_path = os.path.dirname(inspect.getfile(koji.ClientSession))
    if mock_koji_path not in sys.path:
        sys.path.append(os.path.dirname(mock_koji_path))

    # Now load it properly, the same way the plugin will
    del koji
    import koji

from atomic_reactor.core import DockerTasker
from atomic_reactor.plugins.post_koji_promote import KojiPromotePlugin
from atomic_reactor.plugin import PostBuildPluginsRunner, PluginFailedException
from atomic_reactor.inner import DockerBuildWorkflow, TagConf
from atomic_reactor.util import ImageName
from atomic_reactor.source import GitSource, PathSource
from tests.constants import SOURCE

from flexmock import flexmock
import pytest


class X(object):
    pass


class MockedClientSession(object):
    def __init__(self, hub):
        pass

    def importGeneratedContent(self, metadata):
        self.metadata = metadata


def prepare(session, name=None, version=None, release=None):
    tasker = DockerTasker()
    workflow = DockerBuildWorkflow(SOURCE, "test-image")
    setattr(workflow, 'builder', X())
    setattr(workflow.builder, 'image_id', 'asd123')
    setattr(workflow.builder, 'base_image', ImageName(repo='Fedora', tag='22'))
    setattr(workflow.builder, 'source', X())
    setattr(workflow.builder.source, 'dockerfile_path', None)
    setattr(workflow.builder.source, 'path', None)
    setattr(workflow, 'tagconf', TagConf())
    flexmock(koji, ClientSession=lambda hub: session)
    flexmock(GitSource)
    setattr(workflow, 'source', GitSource('git', 'git://hostname/path'))
    setattr(workflow.source, 'lg', X())
    setattr(workflow.source.lg, 'commit_id', '123456')

    if name and version and release:
        workflow.tagconf.add_primary_images(["{0}:{1}_{2}".format(name,
                                                                  version,
                                                                  release),
                                             "{0}:{1}".format(name, version),
                                             "{0}:latest".format(name)])
    return tasker, workflow


def test_koji_promote():
    session = MockedClientSession('')
    name = 'name'
    version = '1.0'
    release = '1'
    tasker, workflow = prepare(session,
                               name=name,
                               version=version,
                               release=release)
    runner = PostBuildPluginsRunner(tasker, workflow,
                                    [
                                        {
                                            'name': KojiPromotePlugin.key,
                                            'args': {
                                                'hub': ''
                                            }
                                        }
                                    ])

    os.environ["BUILD"] = json.dumps({
        "metadata": {
            "creationTimestamp": "2015-07-27T09:24:00Z"
        }
    })
    runner.run()

    data = session.metadata
    assert data['metadata_version'] in ['0', 0]

    build = data['build']
    assert isinstance(build, dict)

    buildroots = data['buildroots']
    assert isinstance(buildroots, list)

    output = data['output']
    assert isinstance(output, list)

    assert 'name' in build
    assert build['name'] == name
    assert 'version' in build
    assert build['version'] == version
    assert 'release' in build
    assert build['release'] == release
    assert 'source' in build
    assert build['source'] == 'git://hostname/path#123456'
    assert 'start_time' in build
    assert int(build['start_time']) > 0
    assert 'end_time' in build
    assert int(build['end_time']) > 0

    for buildroot in buildroots:
        assert isinstance(buildroot, dict)

        assert 'host' in buildroot
        host = buildroot['host']
        assert 'os' in host
        assert 'arch' in host

        assert 'content_generator' in buildroot
        content_generator = buildroot['content_generator']
        assert 'name' in content_generator
        assert 'version' in content_generator
        #assert int(content_generator['version']) > 0

        assert 'container' in buildroot
        container = buildroot['container']
        assert 'type' in container
        assert 'arch' in container

        assert 'tools' in buildroot
        assert isinstance(buildroot['tools'], list)
        for tool in buildroot['tools']:
            assert isinstance(tool, dict)
            assert 'name' in tool
            assert 'version' in tool
            #assert int(tool['version']) > 0

        assert 'component_rpms' in buildroot
        assert isinstance(buildroot['component_rpms'], list)

        assert 'component_archives' in buildroot
        assert isinstance(buildroot['component_archives'], list)

        assert 'extra' in buildroot
        assert isinstance(buildroot['extra'], dict)


def test_koji_promote_no_tagconf():
    session = MockedClientSession('')
    tasker, workflow = prepare(session)
    runner = PostBuildPluginsRunner(tasker, workflow,
                                    [
                                        {
                                            'name': KojiPromotePlugin.key,
                                            'args': {
                                                'hub': ''
                                            }
                                        }
                                    ])

    # No tag config
    os.environ["BUILD"] = json.dumps({
        "metadata": {
            "creationTimestamp": "2015-07-27T09:24:00Z"
        }
    })
    with pytest.raises(PluginFailedException):
        runner.run()


def test_koji_promote_no_build_env():
    session = MockedClientSession('')
    tasker, workflow = prepare(session, name='name', version='1.0', release='1')
    runner = PostBuildPluginsRunner(tasker, workflow,
                                    [
                                        {
                                            'name': KojiPromotePlugin.key,
                                            'args': {
                                                'hub': ''
                                            }
                                        }
                                    ])

    # No BUILD environment variable
    if "BUILD" in os.environ:
        del os.environ["BUILD"]
    with pytest.raises(PluginFailedException):
        runner.run()


def test_koji_promote_no_build_metadata():
    session = MockedClientSession('')
    tasker, workflow = prepare(session, name='name', version='1.0', release='1')
    runner = PostBuildPluginsRunner(tasker, workflow,
                                    [
                                        {
                                            'name': KojiPromotePlugin.key,
                                            'args': {
                                                'hub': ''
                                            }
                                        }
                                    ])

    # No BUILD metadata
    os.environ["BUILD"] = json.dumps({})
    with pytest.raises(PluginFailedException):
        runner.run()


def test_koji_promote_invalid_creation_timestamp():
    session = MockedClientSession('')
    tasker, workflow = prepare(session, name='name', version='1.0', release='1')
    runner = PostBuildPluginsRunner(tasker, workflow,
                                    [
                                        {
                                            'name': KojiPromotePlugin.key,
                                            'args': {
                                                'hub': ''
                                            }
                                        }
                                    ])

    # Invalid timestamp format
    os.environ["BUILD"] = json.dumps({
        "metadata": {
            "creationTimestamp": "2015-07-27 09:24 UTC"
        }
    })
    with pytest.raises(PluginFailedException):
        runner.run()


def test_koji_promote_wrong_source_type():
    session = MockedClientSession('')
    tasker, workflow = prepare(session, name='name', version='1.0', release='1')

    # Wrong source type
    setattr(workflow, 'source', PathSource('path', 'file:///dev/null'))

    runner = PostBuildPluginsRunner(tasker, workflow,
                                    [
                                        {
                                            'name': KojiPromotePlugin.key,
                                            'args': {
                                                'hub': ''
                                            }
                                        }
                                    ])

    os.environ["BUILD"] = json.dumps({
        "metadata": {
            "creationTimestamp": "2015-07-27T09:24:00Z"
        }
    })
    with pytest.raises(PluginFailedException):
        runner.run()
