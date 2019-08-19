from ...tests.script import TestCaseWithTransportAndScript
        # Some older versions of Dulwich (< 0.19.12) formatted diffs slightly
        # differently.
        from dulwich import __version__ as dulwich_version
        if dulwich_version < (0, 19, 12):
            self.assertEqual(output,
                             'diff --git /dev/null b/a\n'
                             'old mode 0\n'
                             'new mode 100644\n'
                             'index 0000000..c197bd8 100644\n'
                             '--- /dev/null\n'
                             '+++ b/a\n'
                             '@@ -0,0 +1 @@\n'
                             '+contents of a\n')
        else:
            self.assertEqual(output,
                             'diff --git a/a b/a\n'
                             'old file mode 0\n'
                             'new file mode 100644\n'
                             'index 0000000..c197bd8 100644\n'
                             '--- /dev/null\n'
                             '+++ b/a\n'
                             '@@ -0,0 +1 @@\n'
                             '+contents of a\n')
class SwitchScriptTests(TestCaseWithTransportAndScript):

    def test_switch_preserves(self):
        # See https://bugs.launchpad.net/brz/+bug/1820606
        self.run_script("""
$ brz init --git r
Created a standalone tree (format: git)
$ cd r
$ echo original > file.txt
$ brz add
adding file.txt
$ brz ci -q -m "Initial"
$ echo "entered on master branch" > file.txt
$ brz stat
modified:
  file.txt
$ brz switch -b other
2>Tree is up to date at revision 1.
2>Switched to branch other
$ cat file.txt
entered on master branch
""")

