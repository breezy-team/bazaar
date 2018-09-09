# Copyright (C) 2018 Jelmer Vernooij <jelmer@jelmer.uk>
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

"""Propose command implementations."""

from ... import (
    branch as _mod_branch,
    controldir,
    errors,
    msgeditor,
    urlutils,
    )
from ...i18n import gettext
from ...commands import Command
from ...option import (
    ListOption,
    Option,
    RegistryOption,
    )
from ...sixish import text_type
from ...trace import note
from ...transport import get_transport
from . import (
    propose as _mod_propose,
    )


def branch_name(branch):
    if branch.name:
        return branch.name
    return urlutils.basename(branch.user_url)


class cmd_publish(Command):
    __doc__ = """Publish a branch.

    Try to create a public copy of a local branch.
    How this is done depends on the submit branch and where it is
    hosted.

    Reasonable defaults are picked for owner name, branch name and project
    name, but they can also be overridden from the command-line.
    """

    takes_options = [
            'directory',
            Option('owner', help='Owner of the new remote branch.', type=str),
            Option('project', help='Project name for the new remote branch.', type=str),
            Option('name', help='Name of the new remote branch.', type=str),
            ]
    takes_args = ['submit_branch?']

    def run(self, submit_branch=None, owner=None, name=None, project=None,
            directory='.'):
        local_branch = _mod_branch.Branch.open_containing(directory)[0]
        self.add_cleanup(local_branch.lock_write().unlock)
        if submit_branch is None:
            submit_branch = local_branch.get_submit_branch()
            note(gettext('Using submit branch %s') % submit_branch)
        submit_branch = _mod_branch.Branch.open(submit_branch)
        if name is None:
            name = branch_name(local_branch)
        hoster = _mod_propose.get_hoster(submit_branch)
        remote_branch, public_url = hoster.publish(
                local_branch, submit_branch, name=name, project=project,
                owner=owner)
        local_branch.set_push_location(remote_branch.user_url)
        local_branch.set_public_branch(public_url)
        note(gettext("Pushed to %s") % public_url)


class cmd_propose_merge(Command):
    __doc__ = """Propose a branch for merging.

    This command creates a merge proposal for the local
    branch to the target branch. The format of the merge
    proposal depends on the submit branch.
    """

    takes_options = ['directory',
            RegistryOption(
                'hoster',
                help='Use the hoster.',
                lazy_registry=('breezy.plugins.propose.propose', 'hosters')),
            ListOption('reviewers', short_name='R', type=text_type,
                help='Requested reviewers.'),
            Option('name', help='Name of the new remote branch.', type=str),
            Option('description', help='Description of the change.', type=str),
            ]
    takes_args = ['submit_branch?']

    aliases = ['propose']

    def run(self, submit_branch=None, directory='.', hoster=None, reviewers=None, name=None,
            description=None):
        tree, branch, relpath = controldir.ControlDir.open_containing_tree_or_branch(
            directory)
        if submit_branch is None:
            submit_branch = branch.get_submit_branch()
        if submit_branch is None:
            submit_branch = branch.get_parent()
        if submit_branch is None:
            raise errors.BzrCommandError(gettext("No target location specified or remembered"))
        else:
            target = _mod_branch.Branch.open(submit_branch)
        if hoster is None:
            hoster = _mod_propose.get_hoster(target)
        else:
            hoster = hoster.probe(target)
        if name is None:
            name = branch_name(branch)
        remote_branch, public_branch_url = hoster.publish(branch, target, name=name)
        note(gettext('Published branch to %s') % public_branch_url)
        proposal_builder = hoster.get_proposer(remote_branch, target)
        if description is None:
            body = proposal_builder.get_initial_body()
            info = proposal_builder.get_infotext()
            description = msgeditor.edit_commit_message(info, start_message=body)
        try:
            proposal = proposal_builder.create_proposal(
                description=description, reviewers=reviewers)
        except _mod_propose.MergeProposalExists as e:
            raise errors.BzrCommandError(gettext(
                'There is already a branch merge proposal: %s') % e.url)
        note(gettext('Merge proposal created: %s') % proposal.url)


class cmd_autopropose(Command):
    __doc__ = """Propose a change based on a script."""

    takes_args = ['branch', 'script']
    takes_options = [
        Option('name', help='Name of the new remote branch.', type=str),
        Option('overwrite', help='Whether to overwrite changes'),
        ]

    def run(self, branch, script, name=None, overwrite=False):
        from ... import osutils
        from ...commit import PointlessCommit
        import os
        import subprocess
        import shutil
        import tempfile
        main_branch = _mod_branch.Branch.open(branch)
        td = tempfile.mkdtemp()
        self.add_cleanup(shutil.rmtree, td)
        # preserve whatever source format we have.
        to_dir = main_branch.controldir.sprout(
                get_transport(td).base, None, create_tree_if_local=True,
                source_branch=main_branch)
        local_tree = to_dir.open_workingtree()
        local_branch = to_dir.open_branch()
        p = subprocess.Popen(script, cwd=td, stdout=subprocess.PIPE)
        (description, err) = p.communicate("")
        if p.returncode != 0:
            raise errors.BzrCommandError(
                gettext("Script %s failed with error code %d") % (
                    script, p.returncode))
        try:
            local_tree.commit(description, allow_pointless=False)
        except PointlessCommit:
            raise errors.BzrCommandError(gettext(
                "Script didn't make any changes"))
        hoster = _mod_propose.get_hoster(main_branch)
        if name is None:
            name = os.path.splitext(osutils.basename(script.split(' ')[0]))[0]
        remote_branch, public_branch_url = hoster.publish(local_branch, main_branch, name=name, overwrite=overwrite)
        note(gettext('Published branch to %s') % public_branch_url)
        proposal_builder = hoster.get_proposer(remote_branch, main_branch)
        proposal = proposal_builder.create_proposal(description=description)
        note(gettext('Merge proposal created: %s') % proposal.url)
