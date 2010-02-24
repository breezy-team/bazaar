# Copyright (C) 2010 Canonical Ltd
# Copyright (C) 2010 Parth Malwankar <parth.malwankar@gmail.com>
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
"""bzr grep"""


from bzrlib.lazy_import import lazy_import
lazy_import(globals(), """
import os
import re

from bzrlib import (
    osutils,
    errors,
    lazy_regex,
    )
""")

def compile_pattern(pattern, flags=0):
    patternc = None
    try:
        # use python's re.compile as we need to catch re.error in case of bad pattern
        lazy_regex.reset_compile()
        patternc = re.compile(pattern, flags)
    except re.error, e:
        raise errors.BzrError("Invalid pattern: '%s'" % pattern)
    return patternc


def file_grep(tree, id, relpath, path, patternc, eol_marker, outf, line_number=True):
    if relpath:
        path = osutils.normpath(osutils.pathjoin(relpath, path))
        path = path.replace('\\', '/')
        path = path.replace(relpath + '/', '', 1)
    fmt_with_n = path + ":%d:%s" + eol_marker
    fmt_without_n = path + ":%s" + eol_marker

    index = 1
    for line in tree.get_file_lines(id):
        res = patternc.search(line)
        if res:
            if line_number:
                outf.write(fmt_with_n % (index, line.strip()))
            else:
                outf.write(fmt_without_n % (line.strip(),))
        index += 1


