# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
"""Tests for the CloudLinux-specific package and repository actions."""
import subprocess
import unittest
from unittest import mock

from pleskdistup.common import motd, util

from cloudlinux8to9.actions.packages import AdoptRepositories, SwitchClnChannel


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


class TestAdoptRepositoriesPostAction(unittest.TestCase):
    """A repository that does not survive the version bump must not abort the
    finish stage.

    _post_action ends with `dnf -y update`, and dnf fails the whole command when
    ANY enabled repository cannot be reached. A Plesk server carries plenty of
    third-party repositories the conversion does not know how to remap, so one
    of them 404ing after the release version changes is an ordinary outcome -
    and this runs on the CloudLinux 9 side, where the framework's own contract
    for _post_action is "failures at this point are best-effort recovery - log
    clearly and prefer to keep going where safe".

    Aborting here strands the host: the actions that restore Plesk have not run
    yet. Seen on a real conversion, where a leftover el8-pinned repository
    returned 404 for .../9.8/cloudlinux-x86_64-server-8/... and took the whole
    finish stage with it.
    """

    def _post_action_with_dnf(self, dnf_side_effect):
        act = AdoptRepositories()
        with mock.patch.object(act, "_use_rpmnew_repositories"), \
                mock.patch.object(act, "_adopt_plesk_repositories") as adopt_plesk, \
                mock.patch.object(act, "_adopt_base_repository") as adopt_base, \
                mock.patch.object(util, "logged_check_call", side_effect=dnf_side_effect), \
                mock.patch.object(motd, "add_finish_ssh_login_message") as motd_msg:
            result = act._post_action()
        return result, adopt_plesk, adopt_base, motd_msg

    def test_a_failing_dnf_update_does_not_abort_the_finish_stage(self):
        boom = subprocess.CalledProcessError(1, ["/usr/bin/dnf", "-y", "update"])
        result, adopt_plesk, adopt_base, motd_msg = self._post_action_with_dnf(boom)
        # No exception, and the adoption that precedes the update still happened.
        self.assertIsNotNone(result)
        adopt_plesk.assert_called_once()
        adopt_base.assert_called_once()

    def test_the_failure_is_surfaced_to_the_administrator(self):
        # Swallowing it silently would be worse than aborting: the host would
        # look converted and clean while carrying an unusable repository.
        boom = subprocess.CalledProcessError(1, ["/usr/bin/dnf", "-y", "update"])
        _, _, _, motd_msg = self._post_action_with_dnf(boom)
        motd_msg.assert_called_once()
        self.assertIn("dnf", motd_msg.call_args[0][0].lower())

    def test_a_successful_update_says_nothing(self):
        result, _, _, motd_msg = self._post_action_with_dnf(None)
        self.assertIsNotNone(result)
        motd_msg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
