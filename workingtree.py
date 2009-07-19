# Copyright (C) 2008 Jelmer Vernooij <jelmer@samba.org>
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


"""An adapter between a Git index and a Bazaar Working Tree"""


from cStringIO import (
    StringIO,
    )
from dulwich.objects import (
    Blob,
    )
import os
import stat

from bzrlib import (
    errors,
    ignores,
    lockable_files,
    lockdir,
    osutils,
    transport,
    tree,
    urlutils,
    workingtree,
    )
from bzrlib.decorators import (
    needs_read_lock,
    )


from bzrlib.plugins.git.inventory import (
    GitIndexInventory,
    )


IGNORE_FILENAME = ".gitignore"


class GitWorkingTree(workingtree.WorkingTree):
    """A Git working tree."""

    def __init__(self, bzrdir, repo, branch):
        self.basedir = bzrdir.root_transport.local_abspath('.')
        self.bzrdir = bzrdir
        self.repository = repo
        self.mapping = self.repository.get_mapping()
        self._branch = branch
        self._transport = bzrdir.transport

        self.controldir = urlutils.join(self.repository._git._controldir, 'bzr')

        try:
            os.makedirs(self.controldir)
            os.makedirs(os.path.join(self.controldir, 'lock'))
        except OSError:
            pass

        self._control_files = lockable_files.LockableFiles(
            transport.get_transport(self.controldir), 'lock', lockdir.LockDir)
        self._format = GitWorkingTreeFormat()
        self.index = self.repository._git.open_index()
        self.views = self._make_views()
        self._detect_case_handling()

    def unlock(self):
        # non-implementation specific cleanup
        self._cleanup()

        # reverse order of locking.
        try:
            return self._control_files.unlock()
        finally:
            self.branch.unlock()

    def is_control_filename(self, path):
        return os.path.basename(path) == ".git"

    def _rewrite_index(self):
        self.index.clear()
        for path, entry in self._inventory.iter_entries():
            if entry.kind == "directory":
                # Git indexes don't contain directories
                continue
            if entry.kind == "file":
                blob = Blob()
                try:
                    file, stat_val = self.get_file_with_stat(entry.file_id, path)
                except (errors.NoSuchFile, IOError):
                    # TODO: Rather than come up with something here, use the old index
                    file = StringIO()
                    stat_val = (0, 0, 0, 0, stat.S_IFREG | 0644, 0, 0, 0, 0, 0)
                blob.set_raw_string(file.read())
            elif entry.kind == "symlink":
                blob = Blob()
                try:
                    stat_val = os.lstat(self.abspath(path))
                except (errors.NoSuchFile, OSError):
                    # TODO: Rather than come up with something here, use the 
                    # old index
                    stat_val = (0, 0, 0, 0, stat.S_IFLNK, 0, 0, 0, 0, 0)
                blob.set_raw_string(entry.symlink_target)
            # Add object to the repository if it didn't exist yet
            if not blob.id in self.repository._git.object_store:
                self.repository._git.object_store.add_object(blob)
            # Add an entry to the index or update the existing entry
            flags = 0 # FIXME
            self.index[path.encode("utf-8")] = (stat_val.st_ctime, stat_val.st_mtime, stat_val.st_dev, stat_val.st_ino, stat_val.st_mode, stat_val.st_uid, stat_val.st_gid, stat_val.st_size, blob.id, flags)

    def flush(self):
        # TODO: Maybe this should only write on dirty ?
        if self._control_files._lock_mode != 'w':
            raise errors.NotWriteLocked(self)
        self._rewrite_index()           
        self.index.write()
        self._inventory_is_modified = False

    def get_ignore_list(self):
        ignoreset = getattr(self, '_ignoreset', None)
        if ignoreset is not None:
            return ignoreset

        ignore_globs = set()
        ignore_globs.update(ignores.get_runtime_ignores())
        ignore_globs.update(ignores.get_user_ignores())
        if self.has_filename(IGNORE_FILENAME):
            f = self.get_file_byname(IGNORE_FILENAME)
            try:
                ignore_globs.update(ignores.parse_ignore_file(f))
            finally:
                f.close()
        self._ignoreset = ignore_globs
        return ignore_globs

    def set_last_revision(self, revid):
        self._change_last_revision(revid)

    def _reset_data(self):
        self._inventory_is_modified = False
        basis_inv = self.repository.get_inventory(self.mapping.revision_id_foreign_to_bzr(self.repository._git.head()))
        result = GitIndexInventory(basis_inv, self.mapping, self.index,
            self.repository._git.object_store)
        self._set_inventory(result, dirty=False)

    @needs_read_lock
    def get_file_sha1(self, file_id, path=None, stat_value=None):
        if not path:
            path = self._inventory.id2path(file_id)
        return osutils.sha_file_by_name(self.abspath(path).encode(osutils._fs_enc))

    def iter_changes(self, from_tree, include_unchanged=False,
                     specific_files=None, pb=None, extra_trees=None,
                     require_versioned=True, want_unversioned=False):

        intertree = tree.InterTree.get(from_tree, self)
        return intertree.iter_changes(include_unchanged, specific_files, pb,
            extra_trees, require_versioned, want_unversioned=want_unversioned)


class GitWorkingTreeFormat(workingtree.WorkingTreeFormat):

    def get_format_description(self):
        return "Git Working Tree"
