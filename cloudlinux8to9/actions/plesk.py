# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.
import os
import re
import subprocess
import time
import typing

from pleskdistup import actions as common_actions
from pleskdistup.common import action, files, log, plesk, systemd


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


class SetFirewalldAllowZoneDriftingOff(action.ActiveAction):
    """Turn off firewalld's AllowZoneDrifting, which leapp inhibits on.

    AllowZoneDrifting=yes is the el8 default, and leapp's
    firewalld_check_allow_zone_drifting inhibits the upgrade on it whenever
    firewalld is enabled - deliberately, since it is a behaviour change the
    administrator should know about. A stock Plesk server runs firewalld with
    the Plesk Firewall extension unconfigured, so the conversion stops there
    with nothing else wrong with the host.

    Turning it off is what leapp's own remediation, leapp's CI and the
    elevate-qa harness all do. It is also forward-only in effect: RHEL 9 removed
    the option and behaves as if it were "no", so the source is being moved to
    the behaviour it is about to get anyway. Reverting the conversion puts the
    original file back.
    """

    conf_path: str
    # [ \t] rather than \s: \s matches the newline too, and with MULTILINE the
    # trailing \s*$ then swallows it, joining the next line onto the rewritten
    # setting.
    _setting_re = re.compile(r"^[ \t]*AllowZoneDrifting[ \t]*=[ \t]*yes[ \t]*$",
                             re.MULTILINE | re.IGNORECASE)

    def __init__(self, conf_path: str = "/etc/firewalld/firewalld.conf") -> None:
        self.name = "turn off firewalld AllowZoneDrifting"
        self.conf_path = conf_path

    @staticmethod
    def _is_zone_drifting_allowed(content: str) -> bool:
        return bool(SetFirewalldAllowZoneDriftingOff._setting_re.search(content))

    @staticmethod
    def _disable_zone_drifting(content: str) -> str:
        return SetFirewalldAllowZoneDriftingOff._setting_re.sub("AllowZoneDrifting=no", content)

    def _read_conf(self) -> typing.Optional[str]:
        if not os.path.exists(self.conf_path):
            return None
        with open(self.conf_path) as f:
            return f.read()

    @staticmethod
    def _is_firewalld_enabled() -> bool:
        # Matches how leapp decides: systemfacts reads `systemctl is-enabled`
        # and calls the service enabled only on exactly "enabled". The
        # framework has no equivalent helper - is_service_active is a different
        # question, and is_service_startable answers "could it start".
        res = subprocess.run(
            [systemd.SYSTEMCTL_BIN_PATH, "is-enabled", "firewalld.service"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
        )
        return res.stdout.strip() == "enabled"

    def _is_required(self) -> bool:
        # leapp's actor returns early when firewalld is not enabled, so match
        # it: such a host is never inhibited and its configuration should not
        # be touched.
        if not self._is_firewalld_enabled():
            return False
        content = self._read_conf()
        return content is not None and self._is_zone_drifting_allowed(content)

    def _prepare_action(self) -> action.ActionResult:
        content = self._read_conf()
        if content is None:
            return action.ActionResult()
        files.backup_file(self.conf_path)
        with open(self.conf_path, "w") as f:
            f.write(self._disable_zone_drifting(content))
        log.info(f"Set AllowZoneDrifting=no in {self.conf_path!r}")
        return action.ActionResult()

    def _post_action(self) -> action.ActionResult:
        # Keep the new value: the option does not exist on the target at all.
        files.remove_backup(self.conf_path, raise_exception=False)
        return action.ActionResult()

    def _revert_action(self) -> action.ActionResult:
        files.restore_file_from_backup(self.conf_path)
        return action.ActionResult()

    def estimate_prepare_time(self) -> int:
        return 1
