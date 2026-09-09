# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for the CloudLinux-specific package and repository actions."""
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
