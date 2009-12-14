# Copyright (C) 2005, 2006, 2008, 2009 Canonical Ltd
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


"""Progress indicators.

The usual way to use this is via bzrlib.ui.ui_factory.nested_progress_bar which
will manage a conceptual stack of nested activities.
"""


import sys
import time
import os


from bzrlib import (
    errors,
    )
from bzrlib.trace import mutter
from bzrlib.symbol_versioning import (
    deprecated_function,
    deprecated_in,
    deprecated_method,
    )


def _supports_progress(f):
    """Detect if we can use pretty progress bars on file F.

    If this returns true we expect that a human may be looking at that
    output, and that we can repaint a line to update it.

    This doesn't check the policy for whether we *should* use them.
    """
    isatty = getattr(f, 'isatty', None)
    if isatty is None:
        return False
    if not isatty():
        return False
    # The following case also handles Win32 - on that platform $TERM is
    # typically never set, so the case None is treated as a smart terminal,
    # not dumb.  <https://bugs.launchpad.net/bugs/334808>  win32 files do have
    # isatty methods that return true.
    if os.environ.get('TERM') == 'dumb':
        # e.g. emacs compile window
        return False
    return True


class ProgressTask(object):
    """Model component of a progress indicator.

    Most code that needs to indicate progress should update one of these,
    and it will in turn update the display, if one is present.

    Code updating the task may also set fields as hints about how to display
    it: show_pct, show_spinner, show_eta, show_count, show_bar.  UIs
    will not necessarily respect all these fields.
    
    :ivar update_latency: The interval (in seconds) at which the PB should be
        updated.  Setting this to zero suggests every update should be shown
        synchronously.

    :ivar show_transport_activity: If true (default), transport activity
        will be shown when this task is drawn.  Disable it if you're sure 
        that only irrelevant or uninteresting transport activity can occur
        during this task.
    """

    def __init__(self, parent_task=None, ui_factory=None, progress_view=None):
        """Construct a new progress task.

        :param parent_task: Enclosing ProgressTask or None.

        :param progress_view: ProgressView to display this ProgressTask.

        :param ui_factory: The UI factory that will display updates; 
            deprecated in favor of passing progress_view directly.

        Normally you should not call this directly but rather through
        `ui_factory.nested_progress_bar`.
        """
        self._parent_task = parent_task
        self._last_update = 0
        self.total_cnt = None
        self.current_cnt = None
        self.msg = ''
        # TODO: deprecate passing ui_factory
        self.ui_factory = ui_factory
        self.progress_view = progress_view
        self.show_pct = False
        self.show_spinner = True
        self.show_eta = False,
        self.show_count = True
        self.show_bar = True
        self.update_latency = 0.1
        self.show_transport_activity = True

    def __repr__(self):
        return '%s(%r/%r, msg=%r)' % (
            self.__class__.__name__,
            self.current_cnt,
            self.total_cnt,
            self.msg)

    def update(self, msg, current_cnt=None, total_cnt=None):
        self.msg = msg
        self.current_cnt = current_cnt
        if total_cnt:
            self.total_cnt = total_cnt
        if self.progress_view:
            self.progress_view.show_progress(self)
        else:
            self.ui_factory._progress_updated(self)

    def tick(self):
        self.update(self.msg)

    def finished(self):
        if self.progress_view:
            self.progress_view.task_finished(self)
        else:
            self.ui_factory._progress_finished(self)

    def make_sub_task(self):
        return ProgressTask(self, ui_factory=self.ui_factory,
            progress_view=self.progress_view)

    def _overall_completion_fraction(self, child_fraction=0.0):
        """Return fractional completion of this task and its parents

        Returns None if no completion can be computed."""
        if self.current_cnt is not None and self.total_cnt:
            own_fraction = (float(self.current_cnt) + child_fraction) / self.total_cnt
        else:
            # if this task has no estimation, it just passes on directly
            # whatever the child has measured...
            own_fraction = child_fraction
        if self._parent_task is None:
            return own_fraction
        else:
            if own_fraction is None:
                own_fraction = 0.0
            return self._parent_task._overall_completion_fraction(own_fraction)

    @deprecated_method(deprecated_in((2, 1, 0)))
    def note(self, fmt_string, *args):
        """Record a note without disrupting the progress bar.
        
        Deprecated: use ui_factory.note() instead or bzrlib.trace.  Note that
        ui_factory.note takes just one string as the argument, not a format
        string and arguments.
        """
        if args:
            self.ui_factory.note(fmt_string % args)
        else:
            self.ui_factory.note(fmt_string)

    def clear(self):
        # TODO: deprecate this method; the model object shouldn't be concerned
        # with whether it's shown or not.  Most callers use this because they
        # want to write some different non-progress output to the screen, but
        # they should probably instead use a stream that's synchronized with
        # the progress output.  It may be there is a model-level use for
        # saying "this task's not active at the moment" but I don't see it. --
        # mbp 20090623
        if self.progress_view:
            self.progress_view.clear()
        else:
            self.ui_factory.clear_term()


@deprecated_function(deprecated_in((1, 16, 0)))
def ProgressBar(to_file=None, **kwargs):
    """Construct a progress bar.

    Deprecated; ask the ui_factory for a progress task instead.
    """
    if to_file is None:
        to_file = sys.stderr
    requested_bar_type = os.environ.get('BZR_PROGRESS_BAR')
    # An value of '' or not set reverts to standard processing
    if requested_bar_type in (None, ''):
        if _supports_progress(to_file):
            return TTYProgressBar(to_file=to_file, **kwargs)
        else:
            return DummyProgress(to_file=to_file, **kwargs)
    else:
        # Minor sanitation to prevent spurious errors
        requested_bar_type = requested_bar_type.lower().strip()
        # TODO: jam 20060710 Arguably we shouldn't raise an exception
        #       but should instead just disable progress bars if we
        #       don't recognize the type
        if requested_bar_type not in _progress_bar_types:
            raise errors.InvalidProgressBarType(requested_bar_type,
                                                _progress_bar_types.keys())
        return _progress_bar_types[requested_bar_type](to_file=to_file, **kwargs)


# NOTE: This is also deprecated; you should provide a ProgressView instead.
class _BaseProgressBar(object):

    def __init__(self,
                 to_file=None,
                 show_pct=False,
                 show_spinner=False,
                 show_eta=False,
                 show_bar=True,
                 show_count=True,
                 to_messages_file=None,
                 _stack=None):
        object.__init__(self)
        if to_file is None:
            to_file = sys.stderr
        if to_messages_file is None:
            to_messages_file = sys.stdout
        self.to_file = to_file
        self.to_messages_file = to_messages_file
        self.last_msg = None
        self.last_cnt = None
        self.last_total = None
        self.show_pct = show_pct
        self.show_spinner = show_spinner
        self.show_eta = show_eta
        self.show_bar = show_bar
        self.show_count = show_count
        self._stack = _stack
        # seed throttler
        self.MIN_PAUSE = 0.1 # seconds
        now = time.time()
        # starting now
        self.start_time = now
        # next update should not throttle
        self.last_update = now - self.MIN_PAUSE - 1

    def finished(self):
        """Return this bar to its progress stack."""
        self.clear()
        self._stack.return_pb(self)

    def note(self, fmt_string, *args, **kwargs):
        """Record a note without disrupting the progress bar."""
        self.clear()
        self.to_messages_file.write(fmt_string % args)
        self.to_messages_file.write('\n')

    @deprecated_function(deprecated_in((1, 16, 0)))
    def child_progress(self, **kwargs):
        return ChildProgress(**kwargs)


class DummyProgress(_BaseProgressBar):
    """Progress-bar standin that does nothing.

    This can be used as the default argument for methods that
    take an optional progress indicator."""

    def tick(self):
        pass

    def update(self, msg=None, current=None, total=None):
        pass

    def child_update(self, message, current, total):
        pass

    def clear(self):
        pass

    def note(self, fmt_string, *args, **kwargs):
        """See _BaseProgressBar.note()."""

    def child_progress(self, **kwargs):
        return DummyProgress(**kwargs)


class DotsProgressBar(_BaseProgressBar):

    @deprecated_function(deprecated_in((1, 16, 0)))
    def __init__(self, **kwargs):
        _BaseProgressBar.__init__(self, **kwargs)
        self.last_msg = None
        self.need_nl = False

    def tick(self):
        self.update()

    def update(self, msg=None, current_cnt=None, total_cnt=None):
        if msg and msg != self.last_msg:
            if self.need_nl:
                self.to_file.write('\n')
            self.to_file.write(msg + ': ')
            self.last_msg = msg
        self.need_nl = True
        self.to_file.write('.')

    def clear(self):
        if self.need_nl:
            self.to_file.write('\n')
        self.need_nl = False

    def child_update(self, message, current, total):
        self.tick()


class TTYProgressBar(_BaseProgressBar):
    """Progress bar display object.

    Several options are available to control the display.  These can
    be passed as parameters to the constructor or assigned at any time:

    show_pct
        Show percentage complete.
    show_spinner
        Show rotating baton.  This ticks over on every update even
        if the values don't change.
    show_eta
        Show predicted time-to-completion.
    show_bar
        Show bar graph.
    show_count
        Show numerical counts.

    The output file should be in line-buffered or unbuffered mode.
    """
    SPIN_CHARS = r'/-\|'

    @deprecated_function(deprecated_in((1, 16, 0)))
    def __init__(self, **kwargs):
        from bzrlib.osutils import terminal_width
        _BaseProgressBar.__init__(self, **kwargs)
        self.spin_pos = 0
        self.width = terminal_width()
        self.last_updates = []
        self._max_last_updates = 10
        self.child_fraction = 0
        self._have_output = False

    def throttle(self, old_msg):
        """Return True if the bar was updated too recently"""
        # time.time consistently takes 40/4000 ms = 0.01 ms.
        # time.clock() is faster, but gives us CPU time, not wall-clock time
        now = time.time()
        if self.start_time is not None and (now - self.start_time) < 1:
            return True
        if old_msg != self.last_msg:
            return False
        interval = now - self.last_update
        # if interval > 0
        if interval < self.MIN_PAUSE:
            return True

        self.last_updates.append(now - self.last_update)
        # Don't let the queue grow without bound
        self.last_updates = self.last_updates[-self._max_last_updates:]
        self.last_update = now
        return False

    def tick(self):
        self.update(self.last_msg, self.last_cnt, self.last_total,
                    self.child_fraction)

    def child_update(self, message, current, total):
        if current is not None and total != 0:
            child_fraction = float(current) / total
            if self.last_cnt is None:
                pass
            elif self.last_cnt + child_fraction <= self.last_total:
                self.child_fraction = child_fraction
        if self.last_msg is None:
            self.last_msg = ''
        self.tick()

    def update(self, msg, current_cnt=None, total_cnt=None,
            child_fraction=0):
        """Update and redraw progress bar.
        """
        if msg is None:
            msg = self.last_msg

        if total_cnt is None:
            total_cnt = self.last_total

        if current_cnt < 0:
            current_cnt = 0

        if current_cnt > total_cnt:
            total_cnt = current_cnt

        ## # optional corner case optimisation
        ## # currently does not seem to fire so costs more than saved.
        ## # trivial optimal case:
        ## # NB if callers are doing a clear and restore with
        ## # the saved values, this will prevent that:
        ## # in that case add a restore method that calls
        ## # _do_update or some such
        ## if (self.last_msg == msg and
        ##     self.last_cnt == current_cnt and
        ##     self.last_total == total_cnt and
        ##     self.child_fraction == child_fraction):
        ##     return

        if msg is None:
            msg = ''

        old_msg = self.last_msg
        # save these for the tick() function
        self.last_msg = msg
        self.last_cnt = current_cnt
        self.last_total = total_cnt
        self.child_fraction = child_fraction

        # each function call takes 20ms/4000 = 0.005 ms,
        # but multiple that by 4000 calls -> starts to cost.
        # so anything to make this function call faster
        # will improve base 'diff' time by up to 0.1 seconds.
        if self.throttle(old_msg):
            return

        if self.show_eta and self.start_time and self.last_total:
            eta = get_eta(self.start_time, self.last_cnt + self.child_fraction,
                    self.last_total, last_updates = self.last_updates)
            eta_str = " " + str_tdelta(eta)
        else:
            eta_str = ""

        if self.show_spinner:
            spin_str = self.SPIN_CHARS[self.spin_pos % 4] + ' '
        else:
            spin_str = ''

        # always update this; it's also used for the bar
        self.spin_pos += 1

        if self.show_pct and self.last_total and self.last_cnt:
            pct = 100.0 * ((self.last_cnt + self.child_fraction) / self.last_total)
            pct_str = ' (%5.1f%%)' % pct
        else:
            pct_str = ''

        if not self.show_count:
            count_str = ''
        elif self.last_cnt is None:
            count_str = ''
        elif self.last_total is None:
            count_str = ' %i' % (self.last_cnt)
        else:
            # make both fields the same size
            t = '%i' % (self.last_total)
            c = '%*i' % (len(t), self.last_cnt)
            count_str = ' ' + c + '/' + t

        if self.show_bar:
            # progress bar, if present, soaks up all remaining space
            cols = self.width - 1 - len(self.last_msg) - len(spin_str) - len(pct_str) \
                   - len(eta_str) - len(count_str) - 3

            if self.last_total:
                # number of markers highlighted in bar
                markers = int(round(float(cols) *
                              (self.last_cnt + self.child_fraction) / self.last_total))
                bar_str = '[' + ('=' * markers).ljust(cols) + '] '
            elif False:
                # don't know total, so can't show completion.
                # so just show an expanded spinning thingy
                m = self.spin_pos % cols
                ms = (' ' * m + '*').ljust(cols)

                bar_str = '[' + ms + '] '
            else:
                bar_str = ''
        else:
            bar_str = ''

        m = spin_str + bar_str + self.last_msg + count_str \
            + pct_str + eta_str
        self.to_file.write('\r%-*.*s' % (self.width - 1, self.width - 1, m))
        self._have_output = True
        #self.to_file.flush()

    def clear(self):
        if self._have_output:
            self.to_file.write('\r%s\r' % (' ' * (self.width - 1)))
        self._have_output = False
        #self.to_file.flush()



# DEPRECATED
class ChildProgress(_BaseProgressBar):
    """A progress indicator that pushes its data to the parent"""

    @deprecated_function(deprecated_in((1, 16, 0)))
    def __init__(self, _stack, **kwargs):
        _BaseProgressBar.__init__(self, _stack=_stack, **kwargs)
        self.parent = _stack.top()
        self.current = None
        self.total = None
        self.child_fraction = 0
        self.message = None

    def update(self, msg, current_cnt=None, total_cnt=None):
        self.current = current_cnt
        if total_cnt is not None:
            self.total = total_cnt
        self.message = msg
        self.child_fraction = 0
        self.tick()

    def child_update(self, message, current, total):
        if current is None or total == 0:
            self.child_fraction = 0
        else:
            self.child_fraction = float(current) / total
        self.tick()

    def tick(self):
        if self.current is None:
            count = None
        else:
            count = self.current+self.child_fraction
            if count > self.total:
                if __debug__:
                    mutter('clamping count of %d to %d' % (count, self.total))
                count = self.total
        self.parent.child_update(self.message, count, self.total)

    def clear(self):
        pass

    def note(self, *args, **kwargs):
        self.parent.note(*args, **kwargs)


def str_tdelta(delt):
    if delt is None:
        return "-:--:--"
    delt = int(round(delt))
    return '%d:%02d:%02d' % (delt/3600,
                             (delt/60) % 60,
                             delt % 60)


def get_eta(start_time, current, total, enough_samples=3, last_updates=None, n_recent=10):
    if start_time is None:
        return None

    if not total:
        return None

    if current < enough_samples:
        return None

    if current > total:
        return None                     # wtf?

    elapsed = time.time() - start_time

    if elapsed < 2.0:                   # not enough time to estimate
        return None

    total_duration = float(elapsed) * float(total) / float(current)

    if last_updates and len(last_updates) >= n_recent:
        avg = sum(last_updates) / float(len(last_updates))
        time_left = avg * (total - current)

        old_time_left = total_duration - elapsed

        # We could return the average, or some other value here
        return (time_left + old_time_left) / 2

    return total_duration - elapsed


class ProgressPhase(object):
    """Update progress object with the current phase"""
    def __init__(self, message, total, pb):
        object.__init__(self)
        self.pb = pb
        self.message = message
        self.total = total
        self.cur_phase = None

    def next_phase(self):
        if self.cur_phase is None:
            self.cur_phase = 0
        else:
            self.cur_phase += 1
        self.pb.update(self.message, self.cur_phase, self.total)


_progress_bar_types = {}
_progress_bar_types['dummy'] = DummyProgress
_progress_bar_types['none'] = DummyProgress
_progress_bar_types['tty'] = TTYProgressBar
_progress_bar_types['dots'] = DotsProgressBar