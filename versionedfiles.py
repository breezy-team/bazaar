# Copyright (C) 2009 Jelmer Vernooij <jelmer@samba.org>

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

from dulwich.object_store import (
    tree_lookup_path,
    )
from dulwich.objects import (
    Blob,
    Commit,
    Tree,
    )

from bzrlib.versionedfile import (
    AbsentContentFactory,
    FulltextContentFactory,
    VersionedFiles,
    )


class GitRevisions(VersionedFiles):

    def __init__(self, object_store):
        self.object_store = object_store

    def check(self, progressbar=None):
        return True

    def iterkeys(self):
        for sha in self.object_store:
            if type(sha) == Commit:
                yield (sha,)

    def keys(self):
        return list(self.iterkeys())

    def add_mpdiffs(self, records):
        raise NotImplementedError(self.add_mpdiffs)

    def get_record_stream(self, keys, ordering, include_delta_closure):
        for key in keys:
            (sha,) = key
            try:
                text = self.object_store.get_raw(sha)
            except KeyError:
                yield AbsentContentFactory(key)
            else:
                yield FulltextContentFactory(key, None, None, text)

    def get_parent_map(self, keys):
        ret = {}
        for (key,) in keys:
            try:
                ret[(key,)] = [(p,) for p in self.object_store[key].parents]
            except KeyError:
                ret[(key,)] = None
        return ret


class GitTexts(VersionedFiles):
    """A texts VersionedFiles instance that is backed onto a Git object store."""

    def __init__(self, repository):
        self.repository = repository
        self.object_store = self.repository._git.object_store

    def check(self, progressbar=None):
        return True

    def add_mpdiffs(self, records):
        raise NotImplementedError(self.add_mpdiffs)

    def get_record_stream(self, keys, ordering, include_delta_closure):
        for key in keys:
            (fileid, revid) = key
            (foreign_revid, mapping) = self.repository.lookup_git_revid(revid)
            root_tree = self.object_store[foreign_revid].tree
            path = mapping.parse_file_id(fileid)
            try:
                obj = tree_lookup_path(self.object_store.__getitem__, 
                                       root_tree, path)
            except KeyError:
                yield AbsentContentFactory(key)
            else:
                if isinstance(obj, Tree):
                    yield FulltextContentFactory(key, None, None, "")
                elif isinstance(obj, Blob):
                    yield FulltextContentFactory(key, None, None, obj._text)
                else:
                    yield AbsentContentFactory(key)

    def get_parent_map(self, keys):
        raise NotImplementedError(self.get_parent_map)

