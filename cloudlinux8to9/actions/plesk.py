# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import os
import time

from pleskdistup import actions as common_actions
from pleskdistup.common import action, log, plesk


class RemovePleskComponentsWhenInstallerIsIdle(common_actions.RemovePleskComponents):
    """RemovePleskComponents that waits out a lingering Plesk installer lock.

    UpdatePlesk runs the Plesk installer earlier in the same conversion, and on
    a host whose Plesk was not already current that is a real update rather than
    a no-op. Its lock stays held for a while after the installer has reported
    success - 27 seconds on the CloudLinux 8.10 + Plesk 18.0.80 host this was
    found on - and _change_plesk_components has no BUSY handling of its own, so
    the next component change dies with

        BUSY: Update operation was locked by another update process.

    and takes the whole conversion with it. The conversion loses a race it
    created itself, and it does so more readily the further behind the host's
    Plesk was, which is not a rare shape for a server about to be converted.

    The framework already models this: list_installed_components() raises
    PleskInstallerBusy for exactly this stdout. Poll it until it stops, then do
    the removal.
    """

    idle_poll_interval: int = 15
    idle_timeout: int = 900

    @property
    def _removed_components_list_file(self) -> str:
        # Upstream derives this from the class name, so subclassing would
        # silently move it. Keep the base class's filename: the removal and the
        # reinstall that undoes it have to agree on where the list lives, even
        # across a resume by a build that used the stock action.
        return os.path.join(self.state_dir, "plesk-dist-upgrade-RemovePleskComponents.txt")

    def _wait_until_installer_is_idle(self) -> None:
        deadline = time.time() + self.idle_timeout
        while True:
            try:
                plesk.list_installed_components()
                return
            except plesk.PleskInstallerBusy as e:
                if time.time() >= deadline:
                    log.err(f"Plesk installer still busy after {self.idle_timeout}s: {e}")
                    raise
                log.info(f"Plesk installer is busy, waiting {self.idle_poll_interval}s: {e}")
                time.sleep(self.idle_poll_interval)

    def _prepare_action(self) -> action.ActionResult:
        self._wait_until_installer_is_idle()
        return super()._prepare_action()
