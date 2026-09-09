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

from cloudlinux8to9.actions.plesk import (
    RemovePleskComponentsWhenInstallerIsIdle,
    SetFirewalldAllowZoneDriftingOff,
)


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


class TestSetFirewalldAllowZoneDriftingOff(unittest.TestCase):
    """The one inhibitor a stock CloudLinux 8 + Plesk host hits.

    AllowZoneDrifting=yes is the el8 default and leapp inhibits on it whenever
    firewalld is enabled, so on a host with nothing else wrong the conversion
    stops here.
    """

    # Exactly as it appears in /etc/firewalld/firewalld.conf on
    # firewalld-0.9.11-12.el8_10, comment line included.
    REAL_CONF = (
        "# AllowZoneDrifting\n"
        "# Older versions of firewalld had undocumented behavior known as\n"
        "# \"zone drifting\".\n"
        "# Possible values; \"yes\", \"no\"\n"
        "# Default: yes\n"
        "AllowZoneDrifting=yes\n"
    )

    def setUp(self):
        self.act = SetFirewalldAllowZoneDriftingOff("/etc/firewalld/firewalld.conf")

    def test_detects_the_stock_el8_configuration(self):
        self.assertTrue(self.act._is_zone_drifting_allowed(self.REAL_CONF))

    def test_rewrites_only_the_setting(self):
        out = self.act._disable_zone_drifting(self.REAL_CONF)
        self.assertIn("AllowZoneDrifting=no\n", out)
        self.assertNotIn("AllowZoneDrifting=yes", out)
        # The commented lines describe the option and must survive - in
        # particular "# Default: yes", which a careless substitution eats.
        self.assertIn("# Default: yes", out)
        self.assertIn("# AllowZoneDrifting\n", out)

    def test_tolerates_spacing(self):
        self.assertTrue(self.act._is_zone_drifting_allowed("AllowZoneDrifting = yes\n"))
        self.assertEqual(
            self.act._disable_zone_drifting("  AllowZoneDrifting = yes  \n"),
            "AllowZoneDrifting=no\n")

    def test_already_off_is_not_a_match(self):
        self.assertFalse(self.act._is_zone_drifting_allowed("AllowZoneDrifting=no\n"))

    def test_a_commented_out_setting_is_not_a_match(self):
        # Only the live setting counts; leapp reads the parsed value.
        self.assertFalse(self.act._is_zone_drifting_allowed("# AllowZoneDrifting=yes\n"))

    def test_not_required_when_firewalld_is_disabled(self):
        # leapp's actor returns early for a disabled firewalld, so there is no
        # inhibitor and no reason to touch the file.
        with mock.patch.object(SetFirewalldAllowZoneDriftingOff, "_is_firewalld_enabled",
                               return_value=False):
            with mock.patch.object(SetFirewalldAllowZoneDriftingOff, "_read_conf",
                                   return_value=self.REAL_CONF):
                self.assertFalse(self.act._is_required())

    def test_required_when_firewalld_is_enabled_and_drifting_allowed(self):
        with mock.patch.object(SetFirewalldAllowZoneDriftingOff, "_is_firewalld_enabled",
                               return_value=True):
            with mock.patch.object(SetFirewalldAllowZoneDriftingOff, "_read_conf",
                                   return_value=self.REAL_CONF):
                self.assertTrue(self.act._is_required())

    def test_not_required_when_there_is_no_config_file(self):
        with mock.patch.object(SetFirewalldAllowZoneDriftingOff, "_is_firewalld_enabled",
                               return_value=True):
            with mock.patch.object(SetFirewalldAllowZoneDriftingOff, "_read_conf",
                                   return_value=None):
                self.assertFalse(self.act._is_required())


if __name__ == "__main__":
    unittest.main()
