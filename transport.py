# Copyright (C) 2006 Jelmer Vernooij <jelmer@samba.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""Simple transport for accessing Subversion smart servers."""

from bzrlib import debug
from bzrlib.errors import (NoSuchFile, NotBranchError, TransportNotPossible, 
                           FileExists, NotLocalUrl)
from bzrlib.trace import mutter
from bzrlib.transport import Transport
import bzrlib.urlutils as urlutils

from svn.core import SubversionException, Pool
import svn.ra
import svn.core
import svn.client

from errors import convert_svn_error

svn_config = svn.core.svn_config_get_config(None)


def _create_auth_baton(pool):
    """Create a Subversion authentication baton. """
    # Give the client context baton a suite of authentication
    # providers.h
    providers = [
        svn.client.get_simple_provider(pool),
        svn.client.get_username_provider(pool),
        svn.client.get_ssl_client_cert_file_provider(pool),
        svn.client.get_ssl_client_cert_pw_file_provider(pool),
        svn.client.get_ssl_server_trust_file_provider(pool),
        ]
    return svn.core.svn_auth_open(providers, pool)


# Don't run any tests on SvnTransport as it is not intended to be 
# a full implementation of Transport
def get_test_permutations():
    return []


def get_svn_ra_transport(bzr_transport):
    """Obtain corresponding SvnRaTransport for a stock Bazaar transport."""
    if isinstance(bzr_transport, SvnRaTransport):
        return bzr_transport

    return SvnRaTransport(bzr_transport.base)


def bzr_to_svn_url(url):
    """Convert a Bazaar URL to a URL understood by Subversion.

    This will possibly remove the svn+ prefix.
    """
    if (url.startswith("svn+http://") or 
        url.startswith("svn+file://") or
        url.startswith("svn+https://")):
        url = url[len("svn+"):] # Skip svn+

    # The SVN libraries don't like trailing slashes...
    return url.rstrip('/')


class Editor:
    """Simple object wrapper around the Subversion delta editor interface."""
    def __init__(self, (editor, editor_baton)):
        self.editor = editor
        self.editor_baton = editor_baton

    def open_root(self, base_revnum):
        return svn.delta.editor_invoke_open_root(self.editor, 
                self.editor_baton, base_revnum)

    def close_directory(self, *args, **kwargs):
        svn.delta.editor_invoke_close_directory(self.editor, *args, **kwargs)

    def close(self):
        svn.delta.editor_invoke_close_edit(self.editor, self.editor_baton)

    def apply_textdelta(self, *args, **kwargs):
        return svn.delta.editor_invoke_apply_textdelta(self.editor, 
                *args, **kwargs)

    def change_dir_prop(self, *args, **kwargs):
        return svn.delta.editor_invoke_change_dir_prop(self.editor, *args, 
                                                       **kwargs)

    def delete_entry(self, *args, **kwargs):
        return svn.delta.editor_invoke_delete_entry(self.editor, *args, **kwargs)

    def add_file(self, *args, **kwargs):
        return svn.delta.editor_invoke_add_file(self.editor, *args, **kwargs)

    def open_file(self, *args, **kwargs):
        return svn.delta.editor_invoke_open_file(self.editor, *args, **kwargs)

    def change_file_prop(self, *args, **kwargs):
        svn.delta.editor_invoke_change_file_prop(self.editor, *args, **kwargs)

    def close_file(self, *args, **kwargs):
        svn.delta.editor_invoke_close_file(self.editor, *args, **kwargs)

    def add_directory(self, *args, **kwargs):
        return svn.delta.editor_invoke_add_directory(self.editor, *args, 
                                                     **kwargs)

    def open_directory(self, *args, **kwargs):
        return svn.delta.editor_invoke_open_directory(self.editor, *args, 
                                                      **kwargs)


class SvnRaTransport(Transport):
    """Fake transport for Subversion-related namespaces.
    
    This implements just as much of Transport as is necessary 
    to fool Bazaar. """
    @convert_svn_error
    def __init__(self, url=""):
        self.pool = Pool()
        bzr_url = url
        self.svn_url = bzr_to_svn_url(url)
        Transport.__init__(self, bzr_url)

        self._client = svn.client.create_context(self.pool)
        self._client.auth_baton = _create_auth_baton(self.pool)
        self._client.config = svn_config

        try:
            if 'transport' in debug.debug_flags:
                mutter('opening SVN RA connection to %r' % self.svn_url)
            self._ra = svn.client.open_ra_session(self.svn_url.encode('utf8'), 
                    self._client, self.pool)
        except SubversionException, (_, num):
            if num in (svn.core.SVN_ERR_RA_ILLEGAL_URL, \
                       svn.core.SVN_ERR_RA_LOCAL_REPOS_OPEN_FAILED, \
                       svn.core.SVN_ERR_BAD_URL):
                raise NotBranchError(path=url)
            raise

    class Reporter:
        def __init__(self, (reporter, report_baton)):
            self._reporter = reporter
            self._baton = report_baton

        def set_path(self, path, revnum, start_empty, lock_token, pool=None):
            svn.ra.reporter2_invoke_set_path(self._reporter, self._baton, 
                        path, revnum, start_empty, lock_token, pool)

        def delete_path(self, path, pool=None):
            svn.ra.reporter2_invoke_delete_path(self._reporter, self._baton,
                    path, pool)

        def link_path(self, path, url, revision, start_empty, lock_token, 
                      pool=None):
            svn.ra.reporter2_invoke_link_path(self._reporter, self._baton,
                    path, url, revision, start_empty, lock_token,
                    pool)

        def finish_report(self, pool=None):
            svn.ra.reporter2_invoke_finish_report(self._reporter, 
                    self._baton, pool)

        def abort_report(self, pool=None):
            svn.ra.reporter2_invoke_abort_report(self._reporter, 
                    self._baton, pool)

    def has(self, relpath):
        """See Transport.has()."""
        # TODO: Raise TransportNotPossible here instead and 
        # catch it in bzrdir.py
        return False

    def get(self, relpath):
        """See Transport.get()."""
        # TODO: Raise TransportNotPossible here instead and 
        # catch it in bzrdir.py
        raise NoSuchFile(path=relpath)

    def stat(self, relpath):
        """See Transport.stat()."""
        raise TransportNotPossible('stat not supported on Subversion')

    @convert_svn_error
    def get_uuid(self):
        mutter('svn get-uuid')
        return svn.ra.get_uuid(self._ra)

    @convert_svn_error
    def get_repos_root(self):
        mutter("svn get-repos-root")
        return svn.ra.get_repos_root(self._ra)

    @convert_svn_error
    def get_latest_revnum(self):
        mutter("svn get-latest-revnum")
        return svn.ra.get_latest_revnum(self._ra)

    @convert_svn_error
    def do_switch(self, switch_rev, switch_target, recurse, switch_url, *args, **kwargs):
        mutter('svn switch -r %d %r -> %r' % (switch_rev, switch_target, switch_url))
        return self.Reporter(svn.ra.do_switch(self._ra, switch_rev, switch_target, recurse, switch_url, *args, **kwargs))

    @convert_svn_error
    def get_log(self, path, from_revnum, to_revnum, *args, **kwargs):
        mutter('svn log %r:%r %r' % (from_revnum, to_revnum, path))
        return svn.ra.get_log(self._ra, [path], from_revnum, to_revnum, *args, **kwargs)

    @convert_svn_error
    def reparent(self, url):
        url = url.rstrip("/")
        if url == self.svn_url:
            return
        self.base = url
        self.svn_url = url
        if hasattr(svn.ra, 'reparent'):
            mutter('svn reparent %r' % url)
            svn.ra.reparent(self._ra, url, self.pool)
        else:
            self._ra = svn.client.open_ra_session(self.svn_url.encode('utf8'), 
                    self._client, self.pool)
    @convert_svn_error
    def get_dir(self, path, revnum, pool=None, kind=False):
        mutter("svn ls -r %d '%r'" % (revnum, path))
        path = path.rstrip("/")
        # ra_dav backends fail with strange errors if the path starts with a 
        # slash while other backends don't.
        assert len(path) == 0 or path[0] != "/"
        if hasattr(svn.ra, 'get_dir2'):
            fields = 0
            if kind:
                fields += svn.core.SVN_DIRENT_KIND
            return svn.ra.get_dir2(self._ra, path, revnum, fields)
        else:
            return svn.ra.get_dir(self._ra, path, revnum)

    @convert_svn_error
    def list_dir(self, relpath):
        assert len(relpath) == 0 or relpath[0] != "/"
        if relpath == ".":
            relpath = ""
        try:
            (dirents, _, _) = self.get_dir(relpath.rstrip("/"), 
                                           self.get_latest_revnum())
        except SubversionException, (msg, num):
            if num == svn.core.SVN_ERR_FS_NOT_DIRECTORY:
                raise NoSuchFile(relpath)
            raise
        return dirents.keys()

    @convert_svn_error
    def get_lock(self, path):
        return svn.ra.get_lock(self._ra, path)

    class SvnLock:
        def __init__(self, transport, tokens):
            self._tokens = tokens
            self._transport = transport

        def unlock(self):
            self.transport.unlock(self.locks)


    @convert_svn_error
    def unlock(self, locks, break_lock=False):
        def lock_cb(baton, path, do_lock, lock, ra_err, pool):
            pass
        return svn.ra.unlock(self._ra, locks, break_lock, lock_cb)

    @convert_svn_error
    def lock_write(self, path_revs, comment=None, steal_lock=False):
        tokens = {}
        def lock_cb(baton, path, do_lock, lock, ra_err, pool):
            tokens[path] = lock
        svn.ra.lock(self._ra, path_revs, comment, steal_lock, lock_cb)
        return SvnLock(self, tokens)

    @convert_svn_error
    def check_path(self, path, revnum, *args, **kwargs):
        assert len(path) == 0 or path[0] != "/"
        mutter("svn check_path -r%d %s" % (revnum, path))
        return svn.ra.check_path(self._ra, path.encode('utf-8'), revnum, *args, **kwargs)

    @convert_svn_error
    def mkdir(self, relpath, mode=None):
        path = "%s/%s" % (self.svn_url, relpath)
        try:
            svn.client.mkdir([path.encode("utf-8")], self._client)
        except SubversionException, (msg, num):
            if num == svn.core.SVN_ERR_FS_NOT_FOUND:
                raise NoSuchFile(path)
            if num == svn.core.SVN_ERR_FS_ALREADY_EXISTS:
                raise FileExists(path)
            raise

    @convert_svn_error
    def do_update(self, revnum, path, *args, **kwargs):
        mutter('svn update -r %r %r' % (revnum, path))
        return self.Reporter(svn.ra.do_update(self._ra, revnum, path, *args, **kwargs))

    @convert_svn_error
    def get_commit_editor(self, *args, **kwargs):
        return Editor(svn.ra.get_commit_editor(self._ra, *args, **kwargs))

    def listable(self):
        """See Transport.listable().
        """
        return True

    # There is no real way to do locking directly on the transport 
    # nor is there a need to as the remote server will take care of 
    # locking
    class PhonyLock:
        def unlock(self):
            pass

    def lock_read(self, relpath):
        """See Transport.lock_read()."""
        return self.PhonyLock()

    def clone(self, offset=None):
        """See Transport.clone()."""
        if offset is None:
            return SvnRaTransport(self.base)

        return SvnRaTransport(urlutils.join(self.base, offset))

    def local_abspath(self, relpath):
        """See Transport.local_abspath()."""
        absurl = self.abspath(relpath)
        if self.base.startswith("file:///"):
            return urlutils.local_path_from_url(absurl)
        raise NotLocalUrl(absurl)

    def abspath(self, relpath):
        """See Transport.abspath()."""
        return urlutils.join(self.base, relpath)
