# Copyright (C) 2005 by Canonical Ltd

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

import os
import sys

import bzrlib.errors
from bzrlib.selftest.testrevision import make_branches
from bzrlib.trace import mutter
from bzrlib.branch import Branch
from bzrlib.fetch import greedy_fetch

from bzrlib.selftest import TestCaseInTempDir
from bzrlib.selftest.HTTPTestUtil import TestCaseWithWebserver


def has_revision(branch, revision_id):
    try:
        branch.get_revision_xml_file(revision_id)
        return True
    except bzrlib.errors.NoSuchRevision:
        return False

def fetch_steps(self, br_a, br_b, writable_a):
    """A foreign test method for testing fetch locally and remotely."""
    def new_branch(name):
        os.mkdir(name)
        return Branch.initialize(name)
            
    assert not has_revision(br_b, br_a.revision_history()[3])
    assert has_revision(br_b, br_a.revision_history()[2])
    assert len(br_b.revision_history()) == 7
    assert greedy_fetch(br_b, br_a, br_a.revision_history()[2])[0] == 0

    # greedy_fetch is not supposed to alter the revision history
    assert len(br_b.revision_history()) == 7
    assert not has_revision(br_b, br_a.revision_history()[3])

    assert len(br_b.revision_history()) == 7
    assert greedy_fetch(br_b, br_a, br_a.revision_history()[3])[0] == 1
    assert has_revision(br_b, br_a.revision_history()[3])
    assert not has_revision(br_a, br_b.revision_history()[6])
    assert has_revision(br_a, br_b.revision_history()[5])

    # When a non-branch ancestor is missing, it should be unlisted...
    # as its not present in the ancestry weave.
    br_b4 = new_branch('br_4')
    count, failures = greedy_fetch(br_b4, br_b)
    self.assertEqual(count, 7)
    self.assertEqual(failures, [])

    self.assertEqual(greedy_fetch(writable_a, br_b)[0], 1)
    assert has_revision(br_a, br_b.revision_history()[3])
    assert has_revision(br_a, br_b.revision_history()[4])
        
    br_b2 = new_branch('br_b2')
    assert greedy_fetch(br_b2, br_b)[0] == 7
    assert has_revision(br_b2, br_b.revision_history()[4])
    assert has_revision(br_b2, br_a.revision_history()[2])
    assert not has_revision(br_b2, br_a.revision_history()[3])

    br_a2 = new_branch('br_a2')
    assert greedy_fetch(br_a2, br_a)[0] == 9
    assert has_revision(br_a2, br_b.revision_history()[4])
    assert has_revision(br_a2, br_a.revision_history()[3])
    assert has_revision(br_a2, br_a.revision_history()[2])

    br_a3 = new_branch('br_a3')
    assert greedy_fetch(br_a3, br_a2)[0] == 0
    for revno in range(4):
        assert not has_revision(br_a3, br_a.revision_history()[revno])
    self.assertEqual(greedy_fetch(br_a3, br_a2, br_a.revision_history()[2])[0], 3)
    fetched = greedy_fetch(br_a3, br_a2, br_a.revision_history()[3])[0]
    assert fetched == 3, "fetched %d instead of 3" % fetched
    # InstallFailed should be raised if the branch is missing the revision
    # that was requested.
    self.assertRaises(bzrlib.errors.InstallFailed, greedy_fetch, br_a3,
                      br_a2, 'pizza')
    # InstallFailed should be raised if the branch is missing a revision
    # from its own revision history
    br_a2.append_revision('a-b-c')
    self.assertRaises(bzrlib.errors.InstallFailed, greedy_fetch, br_a3,
                      br_a2)


class TestFetch(TestCaseInTempDir):

    def test_fetch(self):
        #highest indices a: 5, b: 7
        br_a, br_b = make_branches()
        fetch_steps(self, br_a, br_b, br_a)


class TestHttpFetch(TestCaseWithWebserver):

    def setUp(self):
        super(TestHttpFetch, self).setUp()
        self.weblogs = []

    def test_fetch(self):
        #highest indices a: 5, b: 7
        br_a, br_b = make_branches()
        br_rem_a = Branch.open(self.get_remote_url(br_a._transport.base))
        fetch_steps(self, br_rem_a, br_b, br_a)

    def log(self, *args):
        """Capture web server log messages for introspection."""
        super(TestHttpFetch, self).log(*args)
        if args[0].startswith("webserver"):
            self.weblogs.append(args[0])

    def test_weaves_are_retrieved_once(self):
        self.build_tree(("source/", "source/file", "target/"))
        branch = Branch.initialize("source")
        branch.add(["file"], ["id"])
        branch.commit("added file")
        print >>open("source/file", 'w'), "blah"
        branch.commit("changed file")
        target = Branch.initialize("target/")
        source = Branch.open(self.get_remote_url("source/"))
        source.weave_store.enable_cache = False
        self.assertEqual(greedy_fetch(target, source), (2, []))
        weave_suffix = 'weaves/id.weave HTTP/1.1" 200 -'
        self.assertEqual(1,
            len([log for log in self.weblogs if log.endswith(weave_suffix)]))
