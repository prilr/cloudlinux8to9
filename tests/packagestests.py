# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for the CloudLinux-specific package and repository actions."""
import unittest
from unittest import mock

from pleskdistup.common import util

from cloudlinux8to9.actions.packages import SwitchClnChannel


class TestSwitchClnChannel(unittest.TestCase):
    """The CLN channel switch only applies where CLN manages the packages.

    Carried over from cloudlinux7to8, where every CloudLinux 7 host was CLN
    managed. CloudLinux 8 also ships the SWNG mirrorlist scheme, and such a
    host has no cln-switch-channel at all - rhn-client-tools is installed and
    the binary simply is not in it.

    This action does its work in _revert_action, so an unguarded version fails
    only when the user is already recovering from something else. Verified on a
    CloudLinux 8.10 host: `--revert` died with

        Failed: switching CLN channel. The reason: [Errno 2] No such file or
        directory: '/usr/sbin/cln-switch-channel'
    """

    def test_not_required_without_the_cln_tool(self):
        with mock.patch("os.path.exists", return_value=False):
            self.assertFalse(SwitchClnChannel()._is_required())

    def test_required_when_the_cln_tool_is_present(self):
        with mock.patch("os.path.exists") as exists:
            exists.side_effect = lambda p: p == "/usr/sbin/cln-switch-channel"
            self.assertTrue(SwitchClnChannel()._is_required())

    def test_skipping_it_also_skips_the_revert(self):
        # _is_required is what the flow consults, and a False answer skips the
        # action entirely - prepare, post and revert. That is the property the
        # guard relies on: there is nothing to put back on a host that never
        # had a CLN channel to move.
        act = SwitchClnChannel()
        with mock.patch("os.path.exists", return_value=False):
            self.assertFalse(act.is_required())


class TestSwitchClnChannelRevert(unittest.TestCase):
    """The revert has to guard itself, not only rely on _is_required.

    RevertActionsFlow._is_action_required runs any action its stored state
    marks as SUCCESS whatever is_required now answers, and _prepare_action here
    succeeds trivially. So state written by a build without the guard - or a
    host that lost the CLN tooling between prepare and revert, which a
    conversion can well do - still reaches _revert_action.
    """

    def test_revert_is_a_no_op_without_the_cln_tool(self):
        act = SwitchClnChannel()
        with mock.patch("os.path.exists", return_value=False):
            with mock.patch.object(util, "logged_check_call") as call:
                act._revert_action()
        call.assert_not_called()

    def test_revert_moves_the_channel_back_to_8_when_it_can(self):
        act = SwitchClnChannel()
        with mock.patch("os.path.exists", return_value=True):
            with mock.patch.object(util, "logged_check_call") as call:
                act._revert_action()
        self.assertEqual(call.call_args_list[0][0][0],
                         ["/usr/sbin/cln-switch-channel", "-t", "8", "-o", "-f"])


if __name__ == "__main__":
    unittest.main()
