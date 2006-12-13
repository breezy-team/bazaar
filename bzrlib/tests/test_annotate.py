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

"""Whitebox tests for annotate functionality."""

from cStringIO import StringIO

from bzrlib import (
    annotate,
    conflicts,
    errors,
    tests,
    trace,
    )


class TestAnnotate(tests.TestCaseWithTransport):

    def create_merged_trees(self):
        tree1 = self.make_branch_and_tree('tree1')
        self.build_tree_contents([('tree1/a', 'first\n')])
        tree1.add(['a'], ['a-id'])
        tree1.commit('a', rev_id='rev-1',
                     committer="joe@foo.com", timestamp=1166046000.00)

        tree2 = tree1.bzrdir.clone('tree2').open_workingtree()

        self.build_tree_contents([('tree1/a', 'first\nsecond\n')])
        tree1.commit('b', rev_id='rev-2',
                     committer='joe@foo.com', timestamp=1166046001.00)

        self.build_tree_contents([('tree2/a', 'first\nthird\n')])
        tree2.commit('c', rev_id='rev-1_1_1',
                     committer="barry@foo.com", timestamp=1166046002.00)

        num_conflicts = tree1.merge_from_branch(tree2.branch)
        self.assertEqual(1, num_conflicts)

        self.build_tree_contents([('tree1/a',
                                 'first\nsecond\nthird\n')])
        tree1.set_conflicts(conflicts.ConflictList())
        tree1.commit('merge 2', rev_id='rev-3',
                     committer='sal@foo.com', timestamp=1166046003.00)
        return tree1, tree2

    def create_deeply_merged_trees(self):
        tree1, tree2 = self.create_merged_trees()

        tree3 = tree2.bzrdir.clone('tree3').open_workingtree()

        tree2.commit('noop', rev_id='rev-1.1.2')
        self.assertEqual(0, tree1.merge_from_branch(tree2.branch))
        tree1.commit('noop merge', rev_id='rev-4')

        self.build_tree_contents([('tree3/a', 'first\nthird\nfourth\n')])
        tree3.commit('four', rev_id='rev-1.1.1.1.1',
                     committer='jerry@foo.com', timestamp=1166046003.00)

        tree4 = tree3.bzrdir.clone('tree4').open_workingtree()

        tree3.commit('noop', rev_id='rev-1.1.1.1.2',
                     committer='jerry@foo.com', timestamp=1166046004.00)
        self.assertEqual(0, tree1.merge_from_branch(tree3.branch))
        tree1.commit('merge four', rev_id='rev-5')

        self.build_tree_contents([('tree4/a', 'first\nthird\nfourth\nfifth\n')])
        tree4.commit('five', rev_id='rev-1.1.1.1.1.1.1',
                     committer='george@foo.com', timestamp=1166046005.00)
        self.assertEqual(0, tree1.merge_from_branch(tree4.branch))
        tree1.commit('merge five', rev_id='rev-6')
        return tree1

    def test_annotate_shows_dotted_revnos(self):
        tree1, tree2 = self.create_merged_trees()

        sio = StringIO()
        annotate.annotate_file(tree1.branch, 'rev-3', 'a-id',
                               to_file=sio)
        self.assertEqualDiff('1     joe@foo | first\n'
                             '2     joe@foo | second\n'
                             '1.1.1 barry@f | third\n',
                             sio.getvalue())

    def test_annotate_limits_dotted_revnos(self):
        """Annotate should limit dotted revnos to a depth of 12"""
        tree1 = self.create_deeply_merged_trees()

        sio = StringIO()
        annotate.annotate_file(tree1.branch, 'rev-6', 'a-id',
                               to_file=sio)
        self.assertEqualDiff('1            joe@foo | first\n'
                             '2            joe@foo | second\n'
                             '1.1.1        barry@f | third\n'
                             '1.1.1.1.1    jerry@f | fourth\n'
                             '1.1.1.1.1.1> george@ | fifth\n',
                             sio.getvalue())

        # verbose=True shows everything, the full revno, user id, and date
        sio = StringIO()
        annotate.annotate_file(tree1.branch, 'rev-6', 'a-id',
                               to_file=sio, verbose=True)
        self.assertEqualDiff('1             joe@foo.com    20061213 | first\n'
                             '2             joe@foo.com    20061213 | second\n'
                             '1.1.1         barry@foo.com  20061213 | third\n'
                             '1.1.1.1.1     jerry@foo.com  20061213 | fourth\n'
                             '1.1.1.1.1.1.1 george@foo.com 20061213 | fifth\n',
                             sio.getvalue())
