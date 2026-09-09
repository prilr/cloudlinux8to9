# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for deriving Plesk's main (panel) repository.

The conversion has no other source for Plesk's panel packages. If this
repository is not produced, leapp finds no el9 counterpart for plesk-core and
its 20 siblings, ERASES them instead of upgrading, and the erase runs Plesk's
uninstall scriptlets - which call systemctl and cannot work in the upgrade
initramfs. The transaction then fails and the host lands on CloudLinux 9 with
Plesk half-migrated.

Measured on a real conversion: 21 panel packages erased, 113 upgraded, 10
scriptlet errors, 31 redhat.8 packages stranded. The same tool on AlmaLinux
upgraded all 159 with 0 erased and 0 scriptlet errors - the single difference
being the `enabled` flag on the extras repository this is derived from.
"""
import os
import tempfile
import unittest

from cloudlinux8to9.actions.configure import PleskMainRepoTemporary


CL_PLESK_REPO = """[PLESK_18_0_80-extras]
name=PLESK_18_0_80 extras
baseurl=http://autoinstall.plesk.com/pool/PSA_18.0.80_19608/extras-rpm-CloudLinux-8-x86_64/
enabled=0
gpgcheck=1
"""

ALMA_PLESK_REPO = CL_PLESK_REPO.replace(
    "extras-rpm-CloudLinux-8-x86_64", "extras-rpm-RedHat-el8-x86_64"
).replace("enabled=0", "enabled=1")


class TestPleskMainRepoTemporary(unittest.TestCase):
    def _derive(self, repo_contents):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "plesk.repo")
            with open(src, "w") as f:
                f.write(repo_contents)
            out = os.path.join(d, "plesk-convert_tmp.repo")
            action = PleskMainRepoTemporary()
            returned = action._create_temporary_plesk_repo([src], out)
            with open(out) as f:
                written = f.read()
        return returned, written

    def test_derives_the_panel_repo_from_an_enabled_extras_repo(self):
        """The AlmaLinux case, which has always worked."""
        returned, written = self._derive(ALMA_PLESK_REPO)
        self.assertTrue(returned, "no repository id was returned")
        self.assertIn("PLESK_18_0_80", written)
        self.assertIn("dist-rpm-RedHat-el8-x86_64", written)

    def test_derives_it_from_a_DISABLED_extras_repo_too(self):
        """The CloudLinux case, which did not.

        CloudLinux + Plesk images ship the extras repository with enabled=0.
        Whether extras is enabled for everyday yum use says nothing about where
        Plesk's panel packages live - the URL is right there either way - so
        skipping a disabled repository throws away the only thing this action
        exists to find.
        """
        returned, written = self._derive(CL_PLESK_REPO)
        self.assertTrue(
            returned,
            "no panel repository was derived from a disabled extras repo - "
            "leapp will erase the Plesk panel packages",
        )
        self.assertIn("PLESK_18_0_80", written)
        self.assertIn("dist-rpm-CloudLinux-8-x86_64", written)

    def test_the_derived_repo_is_enabled_regardless_of_the_source(self):
        """It exists to be used by the very next transaction."""
        _, written = self._derive(CL_PLESK_REPO)
        self.assertIn("enabled=1", written)

    def test_extras_is_rewritten_to_dist(self):
        """dist is the panel repository; extras is the add-ons one."""
        _, written = self._derive(CL_PLESK_REPO)
        self.assertNotIn("extras-rpm", written)

    def test_a_repo_file_with_no_plesk_panel_repo_derives_nothing(self):
        returned, _ = self._derive(
            "[plesk-ext-ruby]\nname=ruby\nbaseurl=http://example/x\nenabled=1\n"
        )
        self.assertFalse(returned)


if __name__ == "__main__":
    unittest.main()


class TestPrepareActionReportsAnEmptyDerivation(unittest.TestCase):
    """The action used to report Success having written only a header comment.

    That silence is why the consequence surfaced an hour later, inside the leapp
    transaction, as scriptlet errors on packages being erased - rather than here,
    before the point of no return.
    """

    def test_the_warning_path_resolves_its_names(self):
        # log was not imported when this branch was added; the tests exercised
        # _create_temporary_plesk_repo directly and never reached it, so a
        # NameError would have waited for a real conversion to surface.
        import inspect
        from cloudlinux8to9.actions import configure
        src = inspect.getsource(configure.PleskMainRepoTemporary._prepare_action)
        self.assertIn("log.warn", src)
        self.assertTrue(hasattr(configure, "log"), "configure.py does not import log")
        self.assertTrue(callable(configure.log.warn))
