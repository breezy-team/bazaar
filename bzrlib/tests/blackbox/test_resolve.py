# Copyright (C) 2010 Canonical Ltd
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from bzrlib import (
    conflicts,
    tests,
    )
from bzrlib.tests import script
from bzrlib.tests.blackbox import test_conflicts


class TestResolve(script.TestCaseWithTransportAndScript):

    def setUp(self):
        super(TestResolve, self).setUp()
        test_conflicts.make_tree_with_conflicts(self, 'branch', 'other')

    def test_resolve_one_by_one(self):
        self.run_script("""\
$ cd branch
$ bzr conflicts
Text conflict in my_other_file
Path conflict: mydir3 / mydir2
Text conflict in myfile
$ bzr resolve myfile
2>1 conflict(s) resolved, 2 remaining
$ bzr resolve my_other_file
2>1 conflict(s) resolved, 1 remaining
$ bzr resolve mydir2
2>1 conflict(s) resolved, 0 remaining
""")

    def test_resolve_all(self):
        self.run_script("""\
$ cd branch
$ bzr resolve --all
2>3 conflict(s) resolved, 0 remaining
$ bzr conflicts
""")

    def test_resolve_from_subdir(self):
        self.run_script("""\
$ mkdir branch/subdir
$ cd branch/subdir
$ bzr resolve ../myfile
2>1 conflict(s) resolved, 2 remaining
""")

    def test_resolve_via_directory_option(self):
        self.run_script("""\
$ bzr resolve -d branch myfile
2>1 conflict(s) resolved, 2 remaining
""")

    def test_resolve_all_via_directory_option(self):
        self.run_script("""\
$ bzr resolve -d branch --all
2>3 conflict(s) resolved, 0 remaining
$ bzr conflicts -d branch
""")


class TestResolveAuto(tests.TestCaseWithTransport):

    def test_auto_resolve(self):
        """Text conflicts can be resolved automatically"""
        tree = self.make_branch_and_tree('tree')
        self.build_tree_contents([('tree/file',
            '<<<<<<<\na\n=======\n>>>>>>>\n')])
        tree.add('file', 'file_id')
        self.assertEqual(tree.kind('file_id'), 'file')
        file_conflict = conflicts.TextConflict('file', file_id='file_id')
        tree.set_conflicts(conflicts.ConflictList([file_conflict]))
        note = self.run_bzr('resolve', retcode=1, working_dir='tree')[1]
        self.assertContainsRe(note, '0 conflict\\(s\\) auto-resolved.')
        self.assertContainsRe(note,
            'Remaining conflicts:\nText conflict in file')
        self.build_tree_contents([('tree/file', 'a\n')])
        note = self.run_bzr('resolve', working_dir='tree')[1]
        self.assertContainsRe(note, 'All conflicts resolved.')
