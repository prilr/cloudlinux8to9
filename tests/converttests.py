# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for how the conversion invokes leapp."""
import unittest
from unittest import mock

from pleskdistup.common import util

from cloudlinux8to9.actions.convert import DoCloudLinux8to9Convert


class TestLeappInvocation(unittest.TestCase):
    """`leapp upgrade` has to be told not to ask.

    The CloudLinux leapp gates `upgrade` behind an interactive confirmation:

        Do you confirm that you've successfully taken and tested a full backup
        of your server?
        Y/N>

    guarded by `if not args.resume and not args.nowarn` in
    leapp/cli/commands/upgrade/__init__.py. The conversion runs leapp with no
    terminal, so on a real CloudLinux 8.10 host that prompt ended the upgrade
    with `EOFError: EOF when reading a line` - after preupgrade had passed and
    the target userspace had been built.

    `preupgrade` has no such gate, which is why it ran fine and only the
    upgrade died.
    """

    def _run_and_capture_argv(self):
        act = DoCloudLinux8to9Convert()
        calls = []
        with mock.patch.object(util, "log_outputs_check_call",
                               side_effect=lambda cmd, **kw: calls.append(cmd)):
            act._prepare_action()
        return calls

    def test_upgrade_is_invoked_with_nowarn(self):
        calls = self._run_and_capture_argv()
        upgrade = [c for c in calls if "upgrade" in c]
        self.assertTrue(upgrade, "leapp upgrade was never invoked")
        self.assertIn("--nowarn", upgrade[0])

    def test_preupgrade_runs_first_and_is_left_alone(self):
        # preupgrade has no confirmation gate, so it needs no flag - and it has
        # to run first, since it is what produces the inhibitor report the
        # conversion reports on.
        calls = self._run_and_capture_argv()
        self.assertEqual(calls[0], ["/usr/bin/leapp", "preupgrade"])

    def test_the_overlay_size_is_passed_through_the_environment(self):
        act = DoCloudLinux8to9Convert(leapp_ovl_size=8192)
        envs = []
        with mock.patch.object(util, "log_outputs_check_call",
                               side_effect=lambda cmd, **kw: envs.append(kw.get("env"))):
            act._prepare_action()
        self.assertEqual(envs[0]["LEAPP_OVL_SIZE"], "8192")


if __name__ == "__main__":
    unittest.main()
