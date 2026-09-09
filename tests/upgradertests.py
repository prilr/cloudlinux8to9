# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for the CloudLinux 8 -> 9 upgrader's distribution handling.

The conversion runs in two stages on two different systems: 'start' on
CloudLinux 8 and 'finish' on CloudLinux 9, after leapp has replaced the OS.
Nothing in the start stage exercises the CloudLinux 9 side, so a mistake there
only shows up on a converted machine, hours in and past the point of no return.
These tests pin that side down.
"""
import sys
import unittest
from unittest import mock

from pleskdistup.common import dist, rpm

import cloudlinux8to9.upgrader
from cloudlinux8to9.actions.common import get_adapted_repository
from cloudlinux8to9.actions.common_checks import AssertDistroIsCloudLinux9


def _detected_os(name: str, version: str):
    """Patch whichever OS detection branch get_distro() takes on this interpreter."""
    if sys.version_info < (3, 8):
        return mock.patch.object(dist.platform, "linux_distribution",
                                 return_value=(name, version, ""))
    return mock.patch.object(dist, "_parse_os_relase", return_value=(name, version))


class TestCloudLinux9IsKnown(unittest.TestCase):
    """CloudLinux 9 has to be a known distribution, not an UnknownDistro.

    pleskdistup.main aborts outright on an UnknownDistro, and the deb/rpm
    dispatch in pleskdistup.common.packages keys off rhel_based, which
    UnknownDistro reports as False. Importing the upgrader registers it.
    """

    def setUp(self):
        dist.get_distro.cache_clear()

    def tearDown(self):
        dist.get_distro.cache_clear()

    def test_cloudlinux9_is_not_unknown(self):
        with _detected_os("CloudLinux", "9.7"):
            detected = dist.get_distro()
        self.assertNotIsInstance(detected, dist.UnknownDistro)
        self.assertEqual(detected, dist.CloudLinux("9"))

    def test_cloudlinux9_is_rhel_based(self):
        with _detected_os("CloudLinux", "9.7"):
            self.assertTrue(dist.get_distro().rhel_based)
            self.assertFalse(dist.get_distro().deb_based)

    def test_cloudlinux8_is_still_known(self):
        with _detected_os("CloudLinux", "8.10"):
            self.assertEqual(dist.get_distro(), dist.CloudLinux("8"))


class TestUpgraderSupports(unittest.TestCase):
    def test_supports_cloudlinux_8_to_9(self):
        self.assertTrue(cloudlinux8to9.upgrader.CloudLinux8to9Upgrader.supports(
            dist.CloudLinux("8"), dist.CloudLinux("9")))

    def test_does_not_support_almalinux(self):
        self.assertFalse(cloudlinux8to9.upgrader.CloudLinux8to9Upgrader.supports(
            dist.AlmaLinux("8"), dist.AlmaLinux("9")))

    def test_does_not_support_cloudlinux_7_to_8(self):
        self.assertFalse(cloudlinux8to9.upgrader.CloudLinux8to9Upgrader.supports(
            dist.CloudLinux("7"), dist.CloudLinux("8")))


class TestAssertDistroIsCloudLinux9(unittest.TestCase):
    def setUp(self):
        dist.get_distro.cache_clear()

    def tearDown(self):
        dist.get_distro.cache_clear()

    def test_passes_on_cloudlinux9(self):
        with _detected_os("CloudLinux", "9.7"):
            self.assertTrue(AssertDistroIsCloudLinux9()._do_check())

    def test_fails_on_cloudlinux8(self):
        with _detected_os("CloudLinux", "8.10"):
            self.assertFalse(AssertDistroIsCloudLinux9()._do_check())

    def test_fails_on_almalinux9(self):
        with _detected_os("AlmaLinux", "9.6"):
            self.assertFalse(AssertDistroIsCloudLinux9()._do_check())


class TestCloudLinuxRepositoryAdaptation(unittest.TestCase):
    """The repository rewrite rules have to move CloudLinux 8 repos to 9."""

    def _adapt(self, id: str, name: str, url: str) -> rpm.Repository:
        return get_adapted_repository(rpm.Repository(
            id, name=name, url=url, metalink=None, mirrorlist=None,
            enabled="1\n", gpgcheck="1\n",
        ))

    def test_cloudlinux_path_is_bumped(self):
        adapted = self._adapt(
            "cloudlinux-base", "CloudLinux 8 - BaseOS",
            "https://repo.cloudlinux.com/cloudlinux/8/BaseOS/x86_64/os/")
        self.assertEqual(
            adapted.url, "https://repo.cloudlinux.com/cloudlinux/9/BaseOS/x86_64/os/")

    def test_plesk_extras_repo_moves_to_the_cloudlinux_9_pool(self):
        # The real shape on a CloudLinux 8 + Plesk 18.0.80 host. Plesk publishes
        # extras-rpm-CloudLinux-9-x86_64 alongside the 8 one, so getting this
        # wrong points the target at el8 Plesk packages rather than failing loudly.
        adapted = self._adapt(
            "PLESK_18_0_80-extras", "PLESK_18_0_80 extras",
            "http://autoinstall.plesk.com/pool/PSA_18.0.80_19608/extras-rpm-CloudLinux-8-x86_64/")
        self.assertEqual(
            adapted.url,
            "http://autoinstall.plesk.com/pool/PSA_18.0.80_19608/extras-rpm-CloudLinux-9-x86_64/")

    def test_plesk_php_repo_moves_to_el9(self):
        adapted = self._adapt(
            "PLESK_17_PHP84", "PHP 8.4",
            "http://autoinstall.plesk.com/PHP84_17/dist-rpm-RedHat-el8-x86_64/")
        self.assertEqual(
            adapted.url,
            "http://autoinstall.plesk.com/PHP84_17/dist-rpm-RedHat-el9-x86_64/")

    def test_cloudlinux_dashed_spelling_is_bumped(self):
        adapted = self._adapt(
            "cl-extras", "CloudLinux extras",
            "https://repo.cloudlinux.com/CloudLinux-8/extras/x86_64/")
        self.assertEqual(
            adapted.url, "https://repo.cloudlinux.com/CloudLinux-9/extras/x86_64/")

    def test_cloudlinux_underscored_spelling_is_bumped(self):
        adapted = self._adapt(
            "cl-thing", "CloudLinux thing",
            "https://example.com/CloudLinux_8/x86_64/")
        self.assertEqual(adapted.url, "https://example.com/CloudLinux_9/x86_64/")

    def test_releasever_is_pinned_to_the_target(self):
        adapted = self._adapt(
            "some-repo", "Some repo",
            "https://example.com/el/$releasever/x86_64/")
        self.assertEqual(adapted.url, "https://example.com/el/9/x86_64/")

    def test_plesk_test_mirror_is_bumped_to_the_cloudlinux_9_layout(self):
        adapted = self._adapt(
            "base", "CloudLinux base",
            "http://mirror.pp.plesk.tech/cloudlinux/8/os/x86_64/")
        self.assertEqual(
            adapted.url,
            "http://mirror.pp.plesk.tech/cloudlinux/9/cloudlinux-x86_64-server-9/x86_64/")

    def test_adapted_id_is_stable_across_a_second_pass(self):
        # adopt_repositories runs over already-adapted repo files on the finish
        # stage, so adapting twice must not stack prefixes.
        once = self._adapt("epel", "Extra Packages",
                           "https://example.com/epel/8/Everything/x86_64/")
        twice = get_adapted_repository(once)
        self.assertEqual(once.id, twice.id)


if __name__ == "__main__":
    unittest.main()
