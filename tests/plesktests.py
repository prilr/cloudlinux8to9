# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for the Plesk installer lock handling.

The conversion runs the Plesk installer twice: UpdatePlesk, then a component
removal a few actions later. On a host whose Plesk was not already current the
first is a real update, and its lock is still held when the second starts. The
framework's component change has no BUSY handling, so the conversion aborts on
a race of its own making - observed on a CloudLinux 8.10 + Plesk 18.0.80 host
with a 27 second gap between the two.
"""
import unittest
from unittest import mock

from pleskdistup.actions import RemovePleskComponents
from pleskdistup.common import plesk

from cloudlinux8to9.actions.plesk import RemovePleskComponentsWhenInstallerIsIdle


class TestWaitUntilInstallerIsIdle(unittest.TestCase):
    def setUp(self):
        self.act = RemovePleskComponentsWhenInstallerIsIdle(["webalizer"], "/tmp/state")
        self.act.idle_poll_interval = 0

    def test_returns_at_once_when_the_installer_is_free(self):
        with mock.patch.object(plesk, "list_installed_components", return_value={}) as probe:
            with mock.patch("time.sleep") as slept:
                self.act._wait_until_installer_is_idle()
        self.assertEqual(probe.call_count, 1)
        slept.assert_not_called()

    def test_waits_out_a_lingering_lock(self):
        probe = mock.Mock(side_effect=[
            plesk.PleskInstallerBusy("Update operation was locked by another update process."),
            plesk.PleskInstallerBusy("Update operation was locked by another update process."),
            {},
        ])
        with mock.patch.object(plesk, "list_installed_components", probe):
            with mock.patch("time.sleep") as slept:
                self.act._wait_until_installer_is_idle()
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(slept.call_count, 2)

    def test_gives_up_rather_than_waiting_forever(self):
        # A lock that never clears is a different problem from one that lingers,
        # and hanging on it would be worse than failing: the conversion has
        # already stopped Plesk services by this point.
        self.act.idle_timeout = 0
        probe = mock.Mock(side_effect=plesk.PleskInstallerBusy("still locked"))
        with mock.patch.object(plesk, "list_installed_components", probe):
            with mock.patch("time.sleep"):
                with self.assertRaises(plesk.PleskInstallerBusy):
                    self.act._wait_until_installer_is_idle()

    def test_a_non_busy_failure_is_not_swallowed(self):
        probe = mock.Mock(side_effect=RuntimeError("installer is broken"))
        with mock.patch.object(plesk, "list_installed_components", probe):
            with mock.patch("time.sleep"):
                with self.assertRaises(RuntimeError):
                    self.act._wait_until_installer_is_idle()


class TestPrepareActionOrder(unittest.TestCase):
    def test_the_removal_waits_before_it_runs(self):
        act = RemovePleskComponentsWhenInstallerIsIdle(["webalizer"], "/tmp/state")
        calls = []
        with mock.patch.object(RemovePleskComponentsWhenInstallerIsIdle,
                               "_wait_until_installer_is_idle",
                               side_effect=lambda: calls.append("wait")):
            with mock.patch.object(RemovePleskComponents, "_prepare_action",
                                   side_effect=lambda: calls.append("remove")):
                act._prepare_action()
        self.assertEqual(calls, ["wait", "remove"])


class TestRemovedComponentsListFile(unittest.TestCase):
    def test_keeps_the_base_class_filename(self):
        # The base class derives it from the class name, so subclassing moves
        # it silently. The removal and the reinstall that undoes it have to
        # agree on where the list lives.
        act = RemovePleskComponentsWhenInstallerIsIdle(["webalizer"], "/tmp/state")
        self.assertEqual(act._removed_components_list_file,
                         "/tmp/state/plesk-dist-upgrade-RemovePleskComponents.txt")


if __name__ == "__main__":
    unittest.main()
