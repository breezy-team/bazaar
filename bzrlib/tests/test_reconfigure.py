# Copyright (C) 2007, 2008, 2009, 2011, 2012 Canonical Ltd
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
    branch as _mod_branch,
    controldir,
    errors,
    reconfigure,
    repository,
    tests,
    vf_repository,
    workingtree,
    )


class TestReconfigure(tests.TestCaseWithTransport):

    def test_tree_to_branch(self):
        tree = self.make_branch_and_tree('tree')
        reconfiguration = reconfigure.Reconfigure.to_branch(tree.bzrdir)
        reconfiguration.apply()
        self.assertRaises(errors.NoWorkingTree, workingtree.WorkingTree.open,
                          'tree')

    def test_modified_tree_to_branch(self):
        tree = self.make_branch_and_tree('tree')
        self.build_tree(['tree/file'])
        tree.add('file')
        reconfiguration = reconfigure.Reconfigure.to_branch(tree.bzrdir)
        self.assertRaises(errors.UncommittedChanges, reconfiguration.apply)
        reconfiguration.apply(force=True)
        self.assertRaises(errors.NoWorkingTree, workingtree.WorkingTree.open,
                          'tree')

    def test_tree_with_pending_merge_to_branch(self):
        tree = self.make_branch_and_tree('tree')
        tree.commit('unchanged')
        other_tree = tree.bzrdir.sprout('other').open_workingtree()
        other_tree.commit('mergeable commit')
        tree.merge_from_branch(other_tree.branch)
        reconfiguration = reconfigure.Reconfigure.to_branch(tree.bzrdir)
        self.assertRaises(errors.UncommittedChanges, reconfiguration.apply)
        reconfiguration.apply(force=True)
        self.assertRaises(errors.NoWorkingTree, workingtree.WorkingTree.open,
                          'tree')

    def test_branch_to_branch(self):
        branch = self.make_branch('branch')
        self.assertRaises(errors.AlreadyBranch,
                          reconfigure.Reconfigure.to_branch, branch.bzrdir)

    def test_repo_to_branch(self):
        repo = self.make_repository('repo')
        reconfiguration = reconfigure.Reconfigure.to_branch(repo.bzrdir)
        reconfiguration.apply()

    def test_checkout_to_branch(self):
        branch = self.make_branch('branch')
        checkout = branch.create_checkout('checkout')
        reconfiguration = reconfigure.Reconfigure.to_branch(checkout.bzrdir)
        reconfiguration.apply()
        reconfigured = controldir.ControlDir.open('checkout').open_branch()
        self.assertIs(None, reconfigured.get_bound_location())

    def prepare_lightweight_checkout_to_branch(self):
        branch = self.make_branch('branch')
        checkout = branch.create_checkout('checkout', lightweight=True)
        checkout.commit('first commit', rev_id='rev1')
        reconfiguration = reconfigure.Reconfigure.to_branch(checkout.bzrdir)
        return reconfiguration, checkout

    def test_lightweight_checkout_to_branch(self):
        reconfiguration, checkout = \
            self.prepare_lightweight_checkout_to_branch()
        reconfiguration.apply()
        checkout_branch = checkout.bzrdir.open_branch()
        self.assertEqual(checkout_branch.bzrdir.root_transport.base,
                         checkout.bzrdir.root_transport.base)
        self.assertEqual('rev1', checkout_branch.last_revision())
        repo = checkout.bzrdir.open_repository()
        repo.get_revision('rev1')

    def test_lightweight_checkout_to_branch_tags(self):
        reconfiguration, checkout = \
            self.prepare_lightweight_checkout_to_branch()
        checkout.branch.tags.set_tag('foo', 'bar')
        reconfiguration.apply()
        checkout_branch = checkout.bzrdir.open_branch()
        self.assertEqual('bar', checkout_branch.tags.lookup_tag('foo'))

    def prepare_lightweight_checkout_to_checkout(self):
        branch = self.make_branch('branch')
        checkout = branch.create_checkout('checkout', lightweight=True)
        reconfiguration = reconfigure.Reconfigure.to_checkout(checkout.bzrdir)
        return reconfiguration, checkout

    def test_lightweight_checkout_to_checkout(self):
        reconfiguration, checkout = \
            self.prepare_lightweight_checkout_to_checkout()
        reconfiguration.apply()
        checkout_branch = checkout.bzrdir.open_branch()
        self.assertIsNot(checkout_branch.get_bound_location(), None)

    def test_lightweight_checkout_to_checkout_tags(self):
        reconfiguration, checkout = \
            self.prepare_lightweight_checkout_to_checkout()
        checkout.branch.tags.set_tag('foo', 'bar')
        reconfiguration.apply()
        checkout_branch = checkout.bzrdir.open_branch()
        self.assertEqual('bar', checkout_branch.tags.lookup_tag('foo'))

    def test_lightweight_conversion_uses_shared_repo(self):
        parent = self.make_branch('parent')
        shared_repo = self.make_repository('repo', shared=True)
        checkout = parent.create_checkout('repo/checkout', lightweight=True)
        reconfigure.Reconfigure.to_tree(checkout.bzrdir).apply()
        checkout_repo = checkout.bzrdir.open_branch().repository
        self.assertEqual(shared_repo.bzrdir.root_transport.base,
                         checkout_repo.bzrdir.root_transport.base)

    def test_branch_to_tree(self):
        branch = self.make_branch('branch')
        reconfiguration=reconfigure.Reconfigure.to_tree(branch.bzrdir)
        reconfiguration.apply()
        branch.bzrdir.open_workingtree()

    def test_tree_to_tree(self):
        tree = self.make_branch_and_tree('tree')
        self.assertRaises(errors.AlreadyTree, reconfigure.Reconfigure.to_tree,
                          tree.bzrdir)

    def test_select_bind_location(self):
        branch = self.make_branch('branch')
        reconfiguration = reconfigure.Reconfigure(branch.bzrdir)
        self.assertRaises(errors.NoBindLocation,
                          reconfiguration._select_bind_location)
        branch.set_parent('http://parent')
        reconfiguration = reconfigure.Reconfigure(branch.bzrdir)
        self.assertEqual('http://parent',
                         reconfiguration._select_bind_location())
        branch.set_push_location('sftp://push')
        reconfiguration = reconfigure.Reconfigure(branch.bzrdir)
        self.assertEqual('sftp://push',
                         reconfiguration._select_bind_location())
        branch.lock_write()
        try:
            branch.set_bound_location('bzr://foo/old-bound')
            branch.set_bound_location(None)
        finally:
            branch.unlock()
        reconfiguration = reconfigure.Reconfigure(branch.bzrdir)
        self.assertEqual('bzr://foo/old-bound',
                         reconfiguration._select_bind_location())
        branch.set_bound_location('bzr://foo/cur-bound')
        reconfiguration = reconfigure.Reconfigure(branch.bzrdir)
        self.assertEqual('bzr://foo/cur-bound',
                         reconfiguration._select_bind_location())
        reconfiguration.new_bound_location = 'ftp://user-specified'
        self.assertEqual('ftp://user-specified',
                         reconfiguration._select_bind_location())

    def test_select_reference_bind_location(self):
        branch = self.make_branch('branch')
        checkout = branch.create_checkout('checkout', lightweight=True)
        reconfiguration = reconfigure.Reconfigure(checkout.bzrdir)
        self.assertEqual(branch.base,
                         reconfiguration._select_bind_location())

    def test_tree_to_checkout(self):
        # A tree with no related branches and no supplied bind location cannot
        # become a checkout
        parent = self.make_branch('parent')

        tree = self.make_branch_and_tree('tree')
        reconfiguration = reconfigure.Reconfigure.to_checkout(tree.bzrdir)
        self.assertRaises(errors.NoBindLocation, reconfiguration.apply)
        # setting a parent allows it to become a checkout
        tree.branch.set_parent(parent.base)
        reconfiguration = reconfigure.Reconfigure.to_checkout(tree.bzrdir)
        reconfiguration.apply()
        # supplying a location allows it to become a checkout
        tree2 = self.make_branch_and_tree('tree2')
        reconfiguration = reconfigure.Reconfigure.to_checkout(tree2.bzrdir,
                                                              parent.base)
        reconfiguration.apply()

    def test_tree_to_lightweight_checkout(self):
        # A tree with no related branches and no supplied bind location cannot
        # become a checkout
        parent = self.make_branch('parent')

        tree = self.make_branch_and_tree('tree')
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            tree.bzrdir)
        self.assertRaises(errors.NoBindLocation, reconfiguration.apply)
        # setting a parent allows it to become a checkout
        tree.branch.set_parent(parent.base)
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            tree.bzrdir)
        reconfiguration.apply()
        # supplying a location allows it to become a checkout
        tree2 = self.make_branch_and_tree('tree2')
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            tree2.bzrdir, parent.base)
        reconfiguration.apply()

    def test_checkout_to_checkout(self):
        parent = self.make_branch('parent')
        checkout = parent.create_checkout('checkout')
        self.assertRaises(errors.AlreadyCheckout,
                          reconfigure.Reconfigure.to_checkout, checkout.bzrdir)

    def make_unsynced_checkout(self):
        parent = self.make_branch('parent')
        checkout = parent.create_checkout('checkout')
        checkout.commit('test', rev_id='new-commit', local=True)
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            checkout.bzrdir)
        return checkout, parent, reconfiguration

    def test_unsynced_checkout_to_lightweight(self):
        checkout, parent, reconfiguration = self.make_unsynced_checkout()
        self.assertRaises(errors.UnsyncedBranches, reconfiguration.apply)

    def test_synced_checkout_to_lightweight(self):
        checkout, parent, reconfiguration = self.make_unsynced_checkout()
        parent.pull(checkout.branch)
        reconfiguration.apply()
        wt = checkout.bzrdir.open_workingtree()
        self.assertTrue(parent.repository.has_same_location(
            wt.branch.repository))
        parent.repository.get_revision('new-commit')
        self.assertRaises(errors.NoRepositoryPresent,
                          checkout.bzrdir.open_repository)

    def prepare_branch_to_lightweight_checkout(self):
        parent = self.make_branch('parent')
        child = parent.bzrdir.sprout('child').open_workingtree()
        child.commit('test', rev_id='new-commit')
        parent.pull(child.branch)
        child.bzrdir.destroy_workingtree()
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            child.bzrdir)
        return parent, child, reconfiguration

    def test_branch_to_lightweight_checkout(self):
        parent, child, reconfiguration = \
            self.prepare_branch_to_lightweight_checkout()
        reconfiguration.apply()
        self.assertTrue(reconfiguration._destroy_branch)
        wt = child.bzrdir.open_workingtree()
        self.assertTrue(parent.repository.has_same_location(
            wt.branch.repository))
        parent.repository.get_revision('new-commit')
        self.assertRaises(errors.NoRepositoryPresent,
                          child.bzrdir.open_repository)

    def test_branch_to_lightweight_checkout_failure(self):
        parent, child, reconfiguration = \
            self.prepare_branch_to_lightweight_checkout()
        old_Repository_fetch = vf_repository.VersionedFileRepository.fetch
        vf_repository.VersionedFileRepository.fetch = None
        try:
            self.assertRaises(TypeError, reconfiguration.apply)
        finally:
            vf_repository.VersionedFileRepository.fetch = old_Repository_fetch
        child = _mod_branch.Branch.open('child')
        self.assertContainsRe(child.base, 'child/$')

    def test_branch_to_lightweight_checkout_fetch_tags(self):
        parent, child, reconfiguration = \
            self.prepare_branch_to_lightweight_checkout()
        child.branch.tags.set_tag('foo', 'bar')
        reconfiguration.apply()
        child = _mod_branch.Branch.open('child')
        self.assertEqual('bar', parent.tags.lookup_tag('foo'))

    def test_lightweight_checkout_to_lightweight_checkout(self):
        parent = self.make_branch('parent')
        checkout = parent.create_checkout('checkout', lightweight=True)
        self.assertRaises(errors.AlreadyLightweightCheckout,
                          reconfigure.Reconfigure.to_lightweight_checkout,
                          checkout.bzrdir)

    def test_repo_to_tree(self):
        repo = self.make_repository('repo')
        reconfiguration = reconfigure.Reconfigure.to_tree(repo.bzrdir)
        reconfiguration.apply()
        workingtree.WorkingTree.open('repo')

    def test_shared_repo_to_lightweight_checkout(self):
        repo = self.make_repository('repo', shared=True)
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            repo.bzrdir)
        self.assertRaises(errors.NoBindLocation, reconfiguration.apply)
        branch = self.make_branch('branch')
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            repo.bzrdir, 'branch')
        reconfiguration.apply()
        workingtree.WorkingTree.open('repo')
        repository.Repository.open('repo')

    def test_unshared_repo_to_lightweight_checkout(self):
        repo = self.make_repository('repo', shared=False)
        branch = self.make_branch('branch')
        reconfiguration = reconfigure.Reconfigure.to_lightweight_checkout(
            repo.bzrdir, 'branch')
        reconfiguration.apply()
        workingtree.WorkingTree.open('repo')
        self.assertRaises(errors.NoRepositoryPresent,
                          repository.Repository.open, 'repo')

    def test_standalone_to_use_shared(self):
        self.build_tree(['root/'])
        tree = self.make_branch_and_tree('root/tree')
        tree.commit('Hello', rev_id='hello-id')
        repo = self.make_repository('root', shared=True)
        reconfiguration = reconfigure.Reconfigure.to_use_shared(tree.bzrdir)
        reconfiguration.apply()
        tree = workingtree.WorkingTree.open('root/tree')
        self.assertTrue(repo.has_same_location(tree.branch.repository))
        self.assertEqual('Hello', repo.get_revision('hello-id').message)

    def add_dead_head(self, tree):
        revno, revision_id = tree.branch.last_revision_info()
        tree.commit('Dead head', rev_id='dead-head-id')
        tree.branch.set_last_revision_info(revno, revision_id)
        tree.set_last_revision(revision_id)

    def test_standalone_to_use_shared_preserves_dead_heads(self):
        self.build_tree(['root/'])
        tree = self.make_branch_and_tree('root/tree')
        self.add_dead_head(tree)
        tree.commit('Hello', rev_id='hello-id')
        repo = self.make_repository('root', shared=True)
        reconfiguration = reconfigure.Reconfigure.to_use_shared(tree.bzrdir)
        reconfiguration.apply()
        tree = workingtree.WorkingTree.open('root/tree')
        message = repo.get_revision('dead-head-id').message
        self.assertEqual('Dead head', message)

    def make_repository_tree(self):
        self.build_tree(['root/'])
        repo = self.make_repository('root', shared=True)
        tree = self.make_branch_and_tree('root/tree')
        reconfigure.Reconfigure.to_use_shared(tree.bzrdir).apply()
        return workingtree.WorkingTree.open('root/tree')

    def test_use_shared_to_use_shared(self):
        tree = self.make_repository_tree()
        self.assertRaises(errors.AlreadyUsingShared,
                          reconfigure.Reconfigure.to_use_shared, tree.bzrdir)

    def test_use_shared_to_standalone(self):
        tree = self.make_repository_tree()
        tree.commit('Hello', rev_id='hello-id')
        reconfigure.Reconfigure.to_standalone(tree.bzrdir).apply()
        tree = workingtree.WorkingTree.open('root/tree')
        repo = tree.branch.repository
        self.assertEqual(repo.bzrdir.root_transport.base,
                         tree.bzrdir.root_transport.base)
        self.assertEqual('Hello', repo.get_revision('hello-id').message)

    def test_use_shared_to_standalone_preserves_dead_heads(self):
        tree = self.make_repository_tree()
        self.add_dead_head(tree)
        tree.commit('Hello', rev_id='hello-id')
        reconfigure.Reconfigure.to_standalone(tree.bzrdir).apply()
        tree = workingtree.WorkingTree.open('root/tree')
        repo = tree.branch.repository
        self.assertRaises(errors.NoSuchRevision, repo.get_revision,
                          'dead-head-id')

    def test_standalone_to_standalone(self):
        tree = self.make_branch_and_tree('tree')
        self.assertRaises(errors.AlreadyStandalone,
                          reconfigure.Reconfigure.to_standalone, tree.bzrdir)

    def make_unsynced_branch_reconfiguration(self):
        parent = self.make_branch_and_tree('parent')
        parent.commit('commit 1')
        child = parent.bzrdir.sprout('child').open_workingtree()
        child.commit('commit 2')
        return reconfigure.Reconfigure.to_lightweight_checkout(child.bzrdir)

    def test_unsynced_branch_to_lightweight_checkout_unforced(self):
        reconfiguration = self.make_unsynced_branch_reconfiguration()
        self.assertRaises(errors.UnsyncedBranches, reconfiguration.apply)

    def test_unsynced_branch_to_lightweight_checkout_forced(self):
        reconfiguration = self.make_unsynced_branch_reconfiguration()
        reconfiguration.apply(force=True)

    def make_repository_with_without_trees(self, with_trees):
        repo = self.make_repository('repo', shared=True)
        repo.set_make_working_trees(with_trees)
        return repo

    def test_make_with_trees(self):
        repo = self.make_repository_with_without_trees(False)
        reconfiguration = reconfigure.Reconfigure.set_repository_trees(
            repo.bzrdir, True)
        reconfiguration.apply()
        self.assertIs(True, repo.make_working_trees())

    def test_make_without_trees(self):
        repo = self.make_repository_with_without_trees(True)
        reconfiguration = reconfigure.Reconfigure.set_repository_trees(
            repo.bzrdir, False)
        reconfiguration.apply()
        self.assertIs(False, repo.make_working_trees())

    def test_make_with_trees_already_with_trees(self):
        repo = self.make_repository_with_without_trees(True)
        e = self.assertRaises(errors.AlreadyWithTrees,
           reconfigure.Reconfigure.set_repository_trees, repo.bzrdir, True)
        self.assertContainsRe(str(e),
            r"Shared repository '.*' already creates working trees.")

    def test_make_without_trees_already_no_trees(self):
        repo = self.make_repository_with_without_trees(False)
        e = self.assertRaises(errors.AlreadyWithNoTrees,
            reconfigure.Reconfigure.set_repository_trees, repo.bzrdir, False)
        self.assertContainsRe(str(e),
            r"Shared repository '.*' already doesn't create working trees.")

    def test_repository_tree_reconfiguration_not_supported(self):
        tree = self.make_branch_and_tree('tree')
        e = self.assertRaises(errors.ReconfigurationNotSupported,
            reconfigure.Reconfigure.set_repository_trees, tree.bzrdir, None)
        self.assertContainsRe(str(e),
            r"Requested reconfiguration of '.*' is not supported.")

    def test_lightweight_checkout_to_tree_preserves_reference_locations(self):
        format = controldir.format_registry.make_bzrdir('1.9')
        format.set_branch_format(_mod_branch.BzrBranchFormat8())
        tree = self.make_branch_and_tree('tree', format=format)
        tree.branch.set_reference_info('file_id', 'path', '../location')
        checkout = tree.branch.create_checkout('checkout', lightweight=True)
        reconfiguration = reconfigure.Reconfigure.to_tree(checkout.bzrdir)
        reconfiguration.apply()
        checkout_branch = checkout.bzrdir.open_branch()
        self.assertEqual(('path', '../location'),
                         checkout_branch.get_reference_info('file_id'))
