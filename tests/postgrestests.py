# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for what --upgrade-postgres can actually deliver."""
import unittest
from unittest import mock

from pleskdistup.common import postgres

from cloudlinux8to9.actions.postgres import AssertPostgresDatabaseIsUpgradable


class TestAssertPostgresDatabaseIsUpgradable(unittest.TestCase):
    """--upgrade-postgres reaches exactly one major version back.

    `postgresql-setup --upgrade` on CloudLinux 9 drives the binaries in
    postgresql-upgrade, and that package ships only
    /usr/lib64/pgsql/postgresql-12/bin. So a version 12 datadir upgrades to 13
    and nothing older does.

    Without this check the tool accepts --upgrade-postgres, converts the host,
    and only then finds out, on the far side of the point of no return:

        ERROR: Cannot upgrade because the database in /var/lib/pgsql/data is of
               version 10 but it should be 12

    leaving PostgreSQL unusable - and 10 is the DEFAULT stream of el8's
    postgresql module, so this is the common case rather than an unlucky one.
    """

    def _check(self, installed=True, initialized=True, data_version=10):
        act = AssertPostgresDatabaseIsUpgradable()
        with mock.patch.object(postgres, "is_postgres_installed", return_value=installed), \
                mock.patch.object(postgres, "is_database_initialized", return_value=initialized), \
                mock.patch.object(postgres, "is_database_major_version_lower",
                                  side_effect=lambda v: data_version < v):
            return act._do_check()

    def test_rejects_a_version_10_database(self):
        # The case seen on a real conversion.
        self.assertFalse(self._check(data_version=10))

    def test_rejects_a_version_11_database(self):
        self.assertFalse(self._check(data_version=11))

    def test_accepts_a_version_12_database(self):
        # Exactly what postgresql-upgrade carries the binaries for.
        self.assertTrue(self._check(data_version=12))

    def test_accepts_a_database_already_at_the_target_version(self):
        # Nothing to upgrade: PostgresDatabasesUpdate skips itself.
        self.assertTrue(self._check(data_version=13))

    def test_accepts_a_newer_database(self):
        self.assertTrue(self._check(data_version=16))

    def test_nothing_to_say_when_postgres_is_not_installed(self):
        self.assertTrue(self._check(installed=False))

    def test_nothing_to_say_when_the_database_was_never_initialized(self):
        self.assertTrue(self._check(initialized=False))

    def test_the_description_names_the_versions_involved(self):
        # The administrator has to know what to upgrade to before converting,
        # and this is their only chance to act on it.
        act = AssertPostgresDatabaseIsUpgradable()
        self.assertIn("12", act.description)
        self.assertIn("13", act.description)


if __name__ == "__main__":
    unittest.main()


class TestPostgresUpgradeIsIdempotent(unittest.TestCase):
    """A resumed finish stage must not re-run an upgrade that already happened.

    `_is_required()` is evaluated when the action flow is built - on the source
    system, where PostgreSQL is still 12 - and the answer is stored in
    actions.json. On a resume the stored plan still says "required", so
    `_post_action` runs again against a data directory that is now 13, and
    `postgresql-setup --upgrade` exits non-zero:

        ERROR - Failed: updating PostgreSQL databases. The reason:
        Command '['postgresql-setup', '--upgrade']' returned non-zero exit status 1.

    Observed on a real conversion whose upgrade had in fact SUCCEEDED
    (PG_VERSION 13, the upgrade log ending in "Upgrade Complete"). The finish
    stage is resumable by design - it runs from a systemd unit after a reboot,
    and the tool tells the administrator to re-run it after fixing anything - so
    an action that cannot be re-run turns a recoverable interruption into a
    manual one.
    """

    def _run_upgrade(self, current_version_is_lower):
        # Patch the module's own attributes, not a dotted import path: the
        # action reaches these through `postgres.` and `util.` bound in its
        # module namespace.
        # importlib, not `from cloudlinux8to9.actions import postgres`: the
        # package's star-import rebinds the name `postgres` to pleskdistup's
        # module, shadowing the submodule of the same name.
        import importlib
        pg_action = importlib.import_module("cloudlinux8to9.actions.postgres")
        act = pg_action.PostgresDatabasesUpdate()
        with mock.patch.object(pg_action.postgres, "is_database_major_version_lower",
                               return_value=current_version_is_lower), \
                mock.patch.object(pg_action.postgres, "get_saved_data_path",
                                  return_value="/nonexistent"), \
                mock.patch.object(pg_action.postgres, "get_data_path",
                                  return_value="/nonexistent"), \
                mock.patch.object(pg_action.util, "logged_check_call") as call:
            act._upgrade_database()
        return [" ".join(c[0][0]) for c in call.call_args_list]

    def test_upgrades_when_the_datadir_is_still_older(self):
        cmds = self._run_upgrade(current_version_is_lower=True)
        self.assertTrue(
            any("postgresql-setup" in c for c in cmds),
            "the upgrade did not run on a datadir that still needs it",
        )

    def test_does_not_re_run_when_the_datadir_is_already_current(self):
        cmds = self._run_upgrade(current_version_is_lower=False)
        self.assertFalse(
            any("postgresql-setup" in c for c in cmds),
            "postgresql-setup --upgrade was re-run against an already-upgraded "
            "datadir, which exits non-zero and fails the finish stage",
        )
