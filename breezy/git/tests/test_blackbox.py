from ...tests.features import PluginLoadedFeature
        self.assertEqual(
            output,
            'Standalone tree (format: git)\n'
            'Location:\n'
            '            light checkout root: .\n'
            '  checkout of co-located branch: master\n')

    def test_ignore(self):
        self.simple_commit()
        output, error = self.run_bzr(['ignore', 'foo'])
        self.assertEqual(error, '')
        self.assertEqual(output, '')
        self.assertFileEqual("foo\n", ".gitignore")

    def test_cat_revision(self):
        self.simple_commit()
        output, error = self.run_bzr(['cat-revision', '-r-1'], retcode=3)
        self.assertContainsRe(
            error,
            'brz: ERROR: Repository .* does not support access to raw '
            'revision texts')
        self.assertEqual(output, '')
            author=b"Somebody <user@example.com>",


class ReconcileTests(ExternalBase):

    def test_simple_reconcile(self):
        tree = self.make_branch_and_tree('.', format='git')
        self.build_tree_contents([('a', 'text for a\n')])
        tree.add(['a'])
        output, error = self.run_bzr('reconcile')
        self.assertContainsRe(
            output,
            'Reconciling branch file://.*\n'
            'Reconciling repository file://.*\n'
            'Reconciliation complete.\n')
        self.assertEqual(error, '')


class StatusTests(ExternalBase):

    def test_empty_dir(self):
        tree = self.make_branch_and_tree('.', format='git')
        self.build_tree(['a/', 'a/foo'])
        self.build_tree_contents([('.gitignore', 'foo\n')])
        tree.add(['.gitignore'])
        tree.commit('add ignore')
        output, error = self.run_bzr('st')
        self.assertEqual(output, '')
        self.assertEqual(error, '')


class StatsTests(ExternalBase):

    def test_simple_stats(self):
        self.requireFeature(PluginLoadedFeature('stats'))
        tree = self.make_branch_and_tree('.', format='git')
        self.build_tree_contents([('a', 'text for a\n')])
        tree.add(['a'])
        tree.commit('a commit', committer='Somebody <somebody@example.com>')
        output, error = self.run_bzr('stats')
        self.assertEqual(output, '   1 Somebody <somebody@example.com>\n')


class GitObjectsTests(ExternalBase):

    def run_simple(self, format):
        tree = self.make_branch_and_tree('.', format=format)
        self.build_tree(['a/', 'a/foo'])
        tree.add(['a'])
        tree.commit('add a')
        output, error = self.run_bzr('git-objects')
        shas = list(output.splitlines())
        self.assertEqual([40, 40], [len(s) for s in shas])
        self.assertEqual(error, '')

        output, error = self.run_bzr('git-object %s' % shas[0])
        self.assertEqual('', error)

    def test_in_native(self):
        self.run_simple(format='git')

    def test_in_bzr(self):
        self.run_simple(format='2a')


class GitApplyTests(ExternalBase):

    def test_apply(self):
        b = self.make_branch_and_tree('.')

        with open('foo.patch', 'w') as f:
            f.write("""\
From bdefb25fab801e6af0a70e965f60cb48f2b759fa Mon Sep 17 00:00:00 2001
From: Dmitry Bogatov <KAction@debian.org>
Date: Fri, 8 Feb 2019 23:28:30 +0000
Subject: [PATCH] Add fixed for out-of-date-standards-version

---
 message           | 3 +++
 1 files changed, 14 insertions(+)
 create mode 100644 message

diff --git a/message b/message
new file mode 100644
index 0000000..05ec0b1
--- /dev/null
+++ b/message
@@ -0,0 +1,3 @@
+Update standards version, no changes needed.
+Certainty: certain
+Fixed-Lintian-Tags: out-of-date-standards-version
""")
        output, error = self.run_bzr('git-apply foo.patch')
        self.assertContainsRe(
            error,
            'Committing to: .*\n'
            'Committed revision 1.\n')