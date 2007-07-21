# Copyright (C) 2005-2007 Jelmer Vernooij <jelmer@samba.org>

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
"""Handles branch-specific operations."""

from bzrlib import ui
from bzrlib.branch import Branch, BranchFormat, BranchCheckResult, PullResult
from bzrlib.bzrdir import BzrDir
from bzrlib.errors import (NoSuchFile, DivergedBranches, NoSuchRevision, 
                           NotBranchError)
from bzrlib.inventory import (Inventory)
from bzrlib.trace import mutter
from bzrlib.workingtree import WorkingTree

import svn.client, svn.core
from svn.core import SubversionException

from commit import push
from errors import NotSvnBranchPath
from format import get_rich_root_format
from repository import SvnRepository
from transport import bzr_to_svn_url, svn_config


class FakeControlFiles(object):
    """Dummy implementation of ControlFiles.
    
    This is required as some code relies on controlfiles being 
    available."""
    def get_utf8(self, name):
        raise NoSuchFile(name)

    def get(self, name):
        raise NoSuchFile(name)

    def break_lock(self):
        pass


class SvnBranch(Branch):
    """Maps to a Branch in a Subversion repository """
    def __init__(self, base, repository, branch_path):
        """Instantiate a new SvnBranch.

        :param repos: SvnRepository this branch is part of.
        :param branch_path: Relative path inside the repository this
            branch is located at.
        :param revnum: Subversion revision number of the branch to 
            look at; none for latest.
        :param scheme: Branching scheme used for this branch.
        """
        super(SvnBranch, self).__init__()
        self.repository = repository
        assert isinstance(self.repository, SvnRepository)
        self._branch_path = branch_path
        self.control_files = FakeControlFiles()
        self.base = base.rstrip("/")
        self._format = SvnBranchFormat()
        self._lock_mode = None
        self._cached_revnum = None
        self._revision_history = None
        self._revision_history_revnum = None
        self.scheme = self.repository.get_scheme()
        if (not self.scheme.is_branch(branch_path) and 
            not self.scheme.is_tag(branch_path)):
            raise NotSvnBranchPath(branch_path, scheme=self.scheme)
        try:
            if self.repository.transport.check_path(branch_path.strip("/"), 
                self.get_revnum()) != svn.core.svn_node_dir:
                raise NotBranchError(self.base)
        except SubversionException, (_, num):
            if num == svn.core.SVN_ERR_FS_NO_SUCH_REVISION:
                raise NotBranchError(self.base)
            raise

    def get_branch_path(self, revnum=None):
        """Find the branch path of this branch in the specified revnum.

        :param revnum: Revnum to look for.
        """
        if revnum is None:
            return self._branch_path

        # TODO: Use revnum - this branch may have been moved in the past 
        return self._branch_path

    def get_revnum(self):
        if self._lock_mode == 'r' and self._cached_revnum:
            return self._cached_revnum
        self._cached_revnum = self.repository.transport.get_latest_revnum()
        return self._cached_revnum

    def check(self):
        """See Branch.Check.

        Doesn't do anything for Subversion repositories at the moment (yet).
        """
        return BranchCheckResult(self)

    def _create_heavyweight_checkout(self, to_location, revision_id=None):
        checkout_branch = BzrDir.create_branch_convenience(
            to_location, force_new_tree=False, format=get_rich_root_format())
        checkout = checkout_branch.bzrdir
        checkout_branch.bind(self)
        # pull up to the specified revision_id to set the initial 
        # branch tip correctly, and seed it with history.
        checkout_branch.pull(self, stop_revision=revision_id)
        return checkout.create_workingtree(revision_id)

    def lookup_revision_id(self, revid):
        """Look up the matching Subversion revision number on the mainline of 
        the branch.

        :param revid: Revision id to look up.
        :return: Revision number on the branch. 
        :raises NoSuchRevision: If the revision id was not found.
        """
        (bp, revnum, scheme) = self.repository.lookup_revision_id(revid, 
                                                             scheme=self.scheme)
        assert bp.strip("/") == self.get_branch_path(revnum).strip("/"), \
                "Got %r, expected %r" % (bp, self.get_branch_path(revnum))
        return revnum

    def _create_lightweight_checkout(self, to_location, revision_id=None):
        peg_rev = svn.core.svn_opt_revision_t()
        peg_rev.kind = svn.core.svn_opt_revision_head

        rev = svn.core.svn_opt_revision_t()
        if revision_id is None:
            rev.kind = svn.core.svn_opt_revision_head
        else:
            revnum = self.lookup_revision_id(revision_id)
            rev.kind = svn.core.svn_opt_revision_number
            rev.value.number = revnum

        client_ctx = svn.client.create_context()
        client_ctx.config = svn_config
        svn.client.checkout(bzr_to_svn_url(self.base), to_location, rev, 
                            True, client_ctx)

        return WorkingTree.open(to_location)

    def create_checkout(self, to_location, revision_id=None, lightweight=False):
        """See Branch.create_checkout()."""
        if lightweight:
            return self._create_lightweight_checkout(to_location, revision_id)
        else:
            return self._create_heavyweight_checkout(to_location, revision_id)

    def generate_revision_id(self, revnum):
        """Generate a new revision id for a revision on this branch."""
        assert isinstance(revnum, int)
        return self.repository.generate_revision_id(
                revnum, self.get_branch_path(revnum), str(self.scheme))
       
    def _generate_revision_history(self, last_revnum):
        """Generate the revision history up until a specified revision."""
        self._revision_history = []
        for (branch, rev) in self.repository.follow_branch(
                self.get_branch_path(last_revnum), last_revnum, self.scheme):
            self._revision_history.append(
                self.repository.generate_revision_id(rev, branch, str(self.scheme)))
        self._revision_history.reverse()
        self._revision_history_revnum = last_revnum
        self.repository.revmap.insert_revision_history(self._revision_history)

    def get_root_id(self):
        if self.last_revision() is None:
            inv = Inventory()
        else:
            inv = self.repository.get_inventory(self.last_revision())
        return inv.root.file_id

    def _get_nick(self):
        bp = self._branch_path.strip("/")
        if self._branch_path == "":
            return None
        return bp

    nick = property(_get_nick)

    def set_revision_history(self, rev_history):
        raise NotImplementedError(self.set_revision_history)

    def set_last_revision_info(self, revno, revid):
        pass

    def last_revision_info(self):
        last_revid = self.last_revision()
        return self.revision_id_to_revno(last_revid), last_revid

    def revno(self):
        return self.last_revision_info()[0]

    def revision_id_to_revno(self, revision_id):
        if revision_id is None:
            return 0
        revno = self.repository.revmap.lookup_dist_to_origin(revision_id)
        if revno is not None:
            return revno
        history = self.revision_history()
        try:
            return history.index(revision_id) + 1
        except ValueError:
            raise NoSuchRevision(self, revision_id)

    def set_push_location(self, location):
        raise NotImplementedError(self.set_push_location)

    def get_push_location(self):
        # get_push_location not supported on Subversion
        return None

    def revision_history(self, last_revnum=None):
        if last_revnum is None:
            last_revnum = self.get_revnum()
        if self._revision_history is None or self._revision_history_revnum != last_revnum:
            self._generate_revision_history(last_revnum)
        return self._revision_history

    def last_revision(self):
        # Shortcut for finding the tip. This avoids expensive generation time
        # on large branches.
        last_revnum = self.get_revnum()
        if self._revision_history is None:
            for (branch, rev) in self.repository.follow_branch(
                self.get_branch_path(), last_revnum, self.scheme):
                return self.repository.generate_revision_id(rev, branch, 
                                                            str(self.scheme))
            return None

        ph = self.revision_history(last_revnum)
        if ph:
            return ph[-1]
        else:
            return None

    def pull(self, source, overwrite=False, stop_revision=None, 
             _hook_master=None, run_hooks=True):
        result = PullResult()
        result.source_branch = source
        result.master_branch = None
        result.target_branch = self
        source.lock_read()
        try:
            (result.old_revno, result.old_revid) = self.last_revision_info()
            try:
                self.update_revisions(source, stop_revision)
            except DivergedBranches:
                if overwrite:
                    raise NotImplementedError('overwrite not supported for '
                                              'Subversion branches')
                raise
            (result.new_revno, result.new_revid) = self.last_revision_info()
            return result
        finally:
            source.unlock()

    def generate_revision_history(self, revision_id, last_rev=None, 
        other_branch=None):
        """Create a new revision history that will finish with revision_id.
        
        :param revision_id: the new tip to use.
        :param last_rev: The previous last_revision. If not None, then this
            must be a ancestory of revision_id, or DivergedBranches is raised.
        :param other_branch: The other branch that DivergedBranches should
            raise with respect to.
        """
        # stop_revision must be a descendant of last_revision
        # make a new revision history from the graph

    def _synchronize_history(self, destination, revision_id):
        """Synchronize last revision and revision history between branches.

        This version is most efficient when the destination is also a
        BzrBranch6, but works for BzrBranch5, as long as the destination's
        repository contains all the lefthand ancestors of the intended
        last_revision.  If not, set_last_revision_info will fail.

        :param destination: The branch to copy the history into
        :param revision_id: The revision-id to truncate history at.  May
          be None to copy complete history.
        """
        if revision_id is None:
            revno, revision_id = self.last_revision_info()
        else:
            revno = self.revision_id_to_revno(revision_id)
        destination.set_last_revision_info(revno, revision_id)

    def update_revisions(self, other, stop_revision=None):
        if (self.last_revision() == stop_revision or
            self.last_revision() == other.last_revision()):
            return
        if isinstance(other, SvnBranch) and \
            other.repository.uuid == self.repository.uuid:
            # FIXME: Make sure branches haven't diverged
            # FIXME: svn.ra.del_dir(self.base_path)
            # FIXME: svn.ra.copy_dir(other.base_path, self.base_path)
            raise NotImplementedError(self.pull)
        else:
            todo = self.missing_revisions(other, stop_revision)
            pb = ui.ui_factory.nested_progress_bar()
            try:
                for rev_id in todo:
                    pb.update("pushing revisions", todo.index(rev_id), 
                              len(todo))
                    push(self, other, rev_id)
            finally:
                pb.finished()

    def lock_write(self):
        # TODO: Obtain lock on the remote server?
        if self._lock_mode:
            assert self._lock_mode == 'w'
            self._lock_count += 1
        else:
            self._lock_mode = 'w'
            self._lock_count = 1
        
    def lock_read(self):
        if self._lock_mode:
            assert self._lock_mode in ('r', 'w')
            self._lock_count += 1
        else:
            self._lock_mode = 'r'
            self._lock_count = 1

    def unlock(self):
        self._lock_count -= 1
        if self._lock_count == 0:
            self._lock_mode = None
            self._cached_revnum = None

    def get_parent(self):
        return self.base

    def set_parent(self, url):
        pass

    def append_revision(self, *revision_ids):
        #raise NotImplementedError(self.append_revision)
        #FIXME: Make sure the appended revision is already 
        # part of the revision history
        pass

    def get_physical_lock_status(self):
        return False

    def sprout(self, to_bzrdir, revision_id=None):
        result = to_bzrdir.create_branch()
        self.copy_content_into(result, revision_id=revision_id)
        return result

    def __str__(self):
        return '%s(%r)' % (self.__class__.__name__, self.base)

    __repr__ = __str__


class SvnBranchFormat(BranchFormat):
    """Branch format for Subversion Branches."""
    def __init__(self):
        BranchFormat.__init__(self)

    def __get_matchingbzrdir(self):
        from format import SvnFormat
        return SvnFormat()

    _matchingbzrdir = property(__get_matchingbzrdir)

    def get_format_description(self):
        """See Branch.get_format_description."""
        return 'Subversion Smart Server'

    def get_format_string(self):
        return 'Subversion Smart Server'

    def initialize(self, to_bzrdir):
        raise NotImplementedError(self.initialize)

