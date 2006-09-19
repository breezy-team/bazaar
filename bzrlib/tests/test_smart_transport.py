# Copyright (C) 2006 Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Tests for smart transport"""

# all of this deals with byte strings so this is safe
from cStringIO import StringIO
import subprocess
import sys

import bzrlib
from bzrlib import (
        bzrdir,
        errors,
        tests,
        )
from bzrlib.transport import (
        get_transport,
        local,
        memory,
        smart,
        )


class SmartClientTests(tests.TestCase):

    def test_construct_smart_stream_client(self):
        # make a new client; this really wants a connector function that returns
        # two fifos or sockets but the constructor should not do any IO
        client = smart.SmartStreamClient(None)


class TCPClientTests(tests.TestCaseWithTransport):

    def setUp(self):
        super(TCPClientTests, self).setUp()
        # We're allowed to set  the transport class here, so that we don't use
        # the default or a parameterized class, but rather use the
        # TestCaseWithTransport infrastructure to set up a smart server and
        # transport.
        self.transport_server = smart.SmartTCPServer_for_testing

    def test_plausible_url(self):
        self.assert_(self.get_url().startswith('bzr://'))

    def test_probe_transport(self):
        t = self.get_transport()
        self.assertIsInstance(t, smart.SmartTransport)

    def test_get_client_from_transport(self):
        t = self.get_transport()
        client = t.get_smart_client()
        self.assertIsInstance(client, smart.SmartStreamClient)


class BasicSmartTests(tests.TestCase):
    
    def test_smart_query_version(self):
        """Feed a canned query version to a server"""
        to_server = StringIO('hello\n')
        from_server = StringIO()
        server = smart.SmartStreamServer(to_server, from_server, local.LocalTransport('file:///'))
        server._serve_one_request()
        self.assertEqual('ok\0011\n',
                         from_server.getvalue())

    def test_canned_get_response(self):
        transport = memory.MemoryTransport('memory:///')
        transport.put_bytes('testfile', 'contents\nof\nfile\n')
        to_server = StringIO('get\001./testfile\n')
        from_server = StringIO()
        server = smart.SmartStreamServer(to_server, from_server, transport)
        server._serve_one_request()
        self.assertEqual('ok\n'
                         '17\n'
                         'contents\nof\nfile\n'
                         'done\n',
                         from_server.getvalue())

    def test_get_error_unexpected(self):
        """Error reported by server with no specific representation"""
        class FlakyTransport(object):
            def get_bytes(self, path):
                raise Exception("some random exception from inside server")
        server = smart.SmartTCPServer(backing_transport=FlakyTransport())
        server.start_background_thread()
        try:
            transport = smart.SmartTCPTransport(server.get_url())
            try:
                transport.get('something')
            except errors.TransportError, e:
                self.assertContainsRe(str(e), 'some random exception')
            else:
                self.fail("get did not raise expected error")
        finally:
            server.stop_background_thread()

    def test_server_subprocess(self):
        """Talk to a server started as a subprocess
        
        This is similar to running it over ssh, except that it runs in the same machine 
        without ssh intermediating.
        """
        args = [sys.executable, sys.argv[0], 'serve', '--inet']
        child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 close_fds=True)
        conn = smart.SmartStreamClient(lambda: (child.stdout, child.stdin))
        conn.query_version()
        conn.query_version()
        conn.disconnect()
        returncode = child.wait()
        self.assertEquals(0, returncode)


class SmartTCPTests(tests.TestCase):
    """Tests for connection/end to end behaviour using the TCP server.

    All of these tests are run with a server running on another thread serving
    a MemoryTransport, and a connection to it already open.

    the server is obtained by calling self.setUpServer(readonly=False).
    """

    def setUpServer(self, readonly=False):
        """Setup the server.

        :param readonly: Create a readonly server.
        """
        self.backing_transport = memory.MemoryTransport()
        if readonly:
            self.real_backing_transport = self.backing_transport
            self.backing_transport = get_transport("readonly+" + self.backing_transport.abspath('.'))
        self.server = smart.SmartTCPServer(self.backing_transport)
        self.server.start_background_thread()
        self.transport = smart.SmartTCPTransport(self.server.get_url())

    def tearDown(self):
        if getattr(self, 'transport', None):
            self.transport.disconnect()
        if getattr(self, 'server', None):
            self.server.stop_background_thread()
        super(SmartTCPTests, self).tearDown()
        

class WritableEndToEndTests(SmartTCPTests):
    """Client to server tests that require a writable transport."""

    def setUp(self):
        super(WritableEndToEndTests, self).setUp()
        self.setUpServer()

    def test_start_tcp_server(self):
        url = self.server.get_url()
        self.assertContainsRe(url, r'^bzr://127\.0\.0\.1:[0-9]{2,}/')

    def test_smart_transport_has(self):
        """Checking for file existence over smart."""
        self.backing_transport.put_bytes("foo", "contents of foo\n")
        self.assertTrue(self.transport.has("foo"))
        self.assertFalse(self.transport.has("non-foo"))

    def test_smart_transport_get(self):
        """Read back a file over smart."""
        self.backing_transport.put_bytes("foo", "contents\nof\nfoo\n")
        fp = self.transport.get("foo")
        self.assertEqual('contents\nof\nfoo\n', fp.read())

    def test_get_error_enoent(self):
        """Error reported from server getting nonexistent file."""
        # The path in a raised NoSuchFile exception should be the precise path
        # asked for by the client. This gives meaningful and unsurprising errors
        # for users.
        try:
            self.transport.get('not%20a%20file')
        except errors.NoSuchFile, e:
            self.assertEqual('not%20a%20file', e.path)
        else:
            self.fail("get did not raise expected error")

    def test_simple_clone_conn(self):
        """Test that cloning reuses the same connection."""
        # we create a real connection not a loopback one, but it will use the
        # same server and pipes
        conn2 = self.transport.clone('.')
        self.assertTrue(self.transport._client is conn2._client)

    def test__remote_path(self):
        self.assertEquals('/foo/bar',
                          self.transport._remote_path('foo/bar'))

    def test_clone_changes_base(self):
        """Cloning transport produces one with a new base location"""
        conn2 = self.transport.clone('subdir')
        self.assertEquals(self.transport.base + 'subdir/',
                          conn2.base)

    def test_open_dir(self):
        """Test changing directory"""
        transport = self.transport
        self.backing_transport.mkdir('toffee')
        self.backing_transport.mkdir('toffee/apple')
        self.assertEquals('/toffee', transport._remote_path('toffee'))
        toffee_trans = transport.clone('toffee')
        # Check that each transport has only the contents of its directory
        # directly visible. If state was being held in the wrong object, it's
        # conceivable that cloning a transport would alter the state of the
        # cloned-from transport.
        self.assertTrue(transport.has('toffee'))
        self.assertFalse(toffee_trans.has('toffee'))
        self.assertFalse(transport.has('apple'))
        self.assertTrue(toffee_trans.has('apple'))

    def test_open_bzrdir(self):
        """Open an existing bzrdir over smart transport"""
        transport = self.transport
        t = self.backing_transport
        bzrdir.BzrDirFormat.get_default_format().initialize_on_transport(t)
        result_dir = bzrdir.BzrDir.open_containing_from_transport(transport)


class ReadOnlyEndToEndTests(SmartTCPTests):
    """Tests from the client to the server using a readonly backing transport."""

    def test_mkdir_error_readonly(self):
        """TransportNotPossible should be preserved from the backing transport."""
        self.setUpServer(readonly=True)
        self.assertRaises(errors.TransportNotPossible, self.transport.mkdir,
            'foo')
        

class SmartServerTests(tests.TestCaseWithTransport):
    """Test that call directly into the server logic, bypassing the network."""

    def test_hello(self):
        server = smart.SmartServer(None)
        response = server.dispatch_command('hello', ())
        self.assertEqual(('ok', '1'), response.args)
        self.assertEqual(None, response.body)
        
    def test_get_bundle(self):
        from bzrlib.bundle import serializer
        wt = self.make_branch_and_tree('.')
        self.build_tree_contents([('hello', 'hello world')])
        wt.add('hello')
        rev_id = wt.commit('add hello')
        
        server = smart.SmartServer(self.get_transport())
        response = server.dispatch_command('get_bundle', ('.', rev_id))
        bundle = serializer.read_bundle(StringIO(response.body))

    def test_readonly_exception_becomes_transport_not_possible(self):
        """The response for a read-only error is ('ReadOnlyError')."""
        server = smart.SmartServer(self.get_readonly_transport())
        # send a mkdir for foo, with no explicit mode - should fail.
        response = server.dispatch_command('mkdir', ('foo', ''))
        # and the failure should be an explicit ReadOnlyError
        self.assertEqual(("ReadOnlyError", ), response.args)
        # XXX: TODO: test that other TransportNotPossible errors are
        # presented as TransportNotPossible - not possible to do that
        # until I figure out how to trigger that relatively cleanly via
        # the api. RBC 20060918


class SmartTransportRegistration(tests.TestCase):

    def test_registration(self):
        t = get_transport('bzr+ssh://example.com/path')
        self.assertIsInstance(t, smart.SmartSSHTransport)
        self.assertEqual('example.com', t._host)


class FakeClient(smart.SmartStreamClient):
    """Emulate a client for testing a transport's use of the client."""

    def __init__(self):
        smart.SmartStreamClient.__init__(self, None)
        self._calls = []

    def _call(self, *args):
        self._calls.append(('_call', args))
        return ('ok', )

    def _recv_bulk(self):
        return 'bar'


class TestSmartTransport(tests.TestCase):
        
    def test_use_connection_factory(self):
        # We want to be able to pass a client as a parameter to SmartTransport.
        client = FakeClient()
        transport = smart.SmartTransport('bzr://localhost/', client=client)

        # We want to make sure the client is used when the first remote
        # method is called.  No method should have been called yet.
        self.assertEqual([], client._calls)

        # Now call a method that should result in a single request.
        self.assertEqual('bar', transport.get_bytes('foo'))
        # The only call to _call should have been to get /foo.
        self.assertEqual([('_call', ('get', '/foo'))], client._calls)

    def test__translate_error_readonly(self):
        """Sending a ReadOnlyError to _translate_error raises TransportNotPossible."""
        client = FakeClient()
        transport = smart.SmartTransport('bzr://localhost/', client=client)
        self.assertRaises(errors.TransportNotPossible,
            transport._translate_error, ("ReadOnlyError", ))


class InstrumentedClient(smart.SmartStreamClient):
    """A smart client whose writes are stored to a supplied list."""

    def __init__(self, write_output_list):
        smart.SmartStreamClient.__init__(self, None)
        self._write_output_list = write_output_list

    def _ensure_connection(self):
        """We are never strictly connected."""

    def _write_and_flush(self, bytes):
        self._write_output_list.append(bytes)


class InstrumentedServerProtocol(smart.SmartStreamServer):
    """A smart server which is backed by memory and saves its write requests."""

    def __init__(self, write_output_list):
        smart.SmartStreamServer.__init__(self, None, None,
            memory.MemoryTransport())
        self._write_output_list = write_output_list

    def _write_and_flush(self, bytes):
        self._write_output_list.append(bytes)


class TestSmartProtocol(tests.TestCase):
    """Tests for the smart protocol.

    Each test case gets a smart_server and smart_client created during setUp().

    It is planned that the client can be called with self.call_client() giving
    it an expected server response, which will be fed into it when it tries to
    read. Likewise, self.call_server will call a servers method with a canned
    serialised client request. Output done by the client or server for these
    calls will be captured to self.to_server and self.to_client. Each element
    in the list is a write call from the client or server respectively.
    """

    def setUp(self):
        super(TestSmartProtocol, self).setUp()
        self.to_server = []
        self.to_client = []
        self.smart_client = InstrumentedClient(self.to_server)
        self.smart_server = InstrumentedServerProtocol(self.to_client)

    def assertOffsetSerialisation(self, expected_offsets, expected_serialised,
        client, server_protocol):
        """Check that smart (de)serialises offsets as expected.
        
        We check both serialisation and deserialisation at the same time
        to ensure that the round tripping cannot skew: both directions should
        be as expected.
        
        :param expected_offsets: a readv offset list.
        :param expected_seralised: an expected serial form of the offsets.
        :param server: a SmartServer instance.
        """
        offsets = server_protocol.smart_server._deserialise_offsets(
            expected_serialised)
        self.assertEqual(expected_offsets, offsets)
        serialised = client._serialise_offsets(offsets)
        self.assertEqual(expected_serialised, serialised)

    def test_server_offset_serialisation(self):
        """The Smart protocol serialises offsets as a comma and \n string.

        We check a number of boundary cases are as expected: empty, one offset,
        one with the order of reads not increasing (an out of order read), and
        one that should coalesce.
        """
        self.assertOffsetSerialisation([], '',
            self.smart_client, self.smart_server)
        self.assertOffsetSerialisation([(1,2)], '1,2',
            self.smart_client, self.smart_server)
        self.assertOffsetSerialisation([(10,40), (0,5)], '10,40\n0,5',
            self.smart_client, self.smart_server)
        self.assertOffsetSerialisation([(1,2), (3,4), (100, 200)],
            '1,2\n3,4\n100,200', self.smart_client, self.smart_server)


# TODO: Client feature that does get_bundle and then installs that into a
# branch; this can be used in place of the regular pull/fetch operation when
# coming from a smart server.
#
# TODO: Eventually, want to do a 'branch' command by fetching the whole
# history as one big bundle.  How?  
#
# The branch command does 'br_from.sprout', which tries to preserve the same
# format.  We don't necessarily even want that.  
#
# It might be simpler to handle cmd_pull first, which does a simpler fetch()
# operation from one branch into another.  It already has some code for
# pulling from a bundle, which it does by trying to see if the destination is
# a bundle file.  So it seems the logic for pull ought to be:
# 
#  - if it's a smart server, get a bundle from there and install that
#  - if it's a bundle, install that
#  - if it's a branch, pull from there
#
# Getting a bundle from a smart server is a bit different from reading a
# bundle from a URL:
#
#  - we can reasonably remember the URL we last read from 
#  - you can specify a revision number to pull, and we need to pass it across
#    to the server as a limit on what will be requested
#
# TODO: Given a URL, determine whether it is a smart server or not (or perhaps
# otherwise whether it's a bundle?)  Should this be a property or method of
# the transport?  For the ssh protocol, we always know it's a smart server.
# For http, we potentially need to probe.  But if we're explicitly given
# bzr+http:// then we can skip that for now. 
