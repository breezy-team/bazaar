# Copyright (C) 2005-2010 Canonical Ltd
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

from __future__ import absolute_import

from cStringIO import StringIO

from bzrlib.lazy_import import lazy_import
lazy_import(globals(), """
from bzrlib import (
    errors,
    transport as _mod_transport,
    urlutils,
    )
from bzrlib.bundle import serializer as _serializer
from bzrlib.merge_directive import MergeDirective
from bzrlib.i18n import gettext
""")
from bzrlib.trace import note


def read_mergeable_from_url(url, _do_directive=True, possible_transports=None):
    """Read mergable object from a given URL.

    :return: An object supporting get_target_revision.  Raises NotABundle if
        the target is not a mergeable type.
    """
    child_transport = _mod_transport.get_transport(url,
        possible_transports=possible_transports)
    transport = child_transport.clone('..')
    filename = transport.relpath(child_transport.base)
    mergeable, transport = read_mergeable_from_transport(transport, filename,
                                                         _do_directive)
    return mergeable


def read_mergeable_from_transport(transport, filename, _do_directive=True):
    def get_bundle(transport):
        return StringIO(transport.get_bytes(filename)), transport

    def redirected_transport(transport, exception, redirection_notice):
        note(redirection_notice)
        url, filename = urlutils.split(exception.target,
                                       exclude_trailing_slash=False)
        if not filename:
            raise errors.NotABundle(gettext('A directory cannot be a bundle'))
        return _mod_transport.get_transport_from_url(url)

    try:
        bytef, transport = _mod_transport.do_catching_redirections(
            get_bundle, transport, redirected_transport)
    except errors.TooManyRedirections:
        raise errors.NotABundle(transport.clone(filename).base)
    except (errors.ConnectionReset, errors.ConnectionError), e:
        raise
    except (errors.TransportError, errors.PathError), e:
        raise errors.NotABundle(str(e))
    except (IOError,), e:
        # jam 20060707
        # Abstraction leakage, SFTPTransport.get('directory')
        # doesn't always fail at get() time. Sometimes it fails
        # during read. And that raises a generic IOError with
        # just the string 'Failure'
        # StubSFTPServer does fail during get() (because of prefetch)
        # so it has an opportunity to translate the error.
        raise errors.NotABundle(str(e))

    if _do_directive:
        try:
            return MergeDirective.from_lines(bytef), transport
        except errors.NotAMergeDirective:
            bytef.seek(0)

    return _serializer.read_bundle(bytef), transport
