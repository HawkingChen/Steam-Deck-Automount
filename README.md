# Steam Deck Auto Mount

**Keep automatic mounting configured across normal SteamOS updates — no need to set it up again.**

Automatically mount USB storage, SD cards, and selected internal data partitions in Gaming Mode and Desktop Mode. The installer adds a SteamOS update keep-list for its configuration. See the validation limits below.

Based on [scawp/Steam-Deck.Mount-External-Drive](https://github.com/scawp/Steam-Deck.Mount-External-Drive), by scawp. This is a modified version, distributed under the original [DBAD Public License 1.2](LICENSE.md). Upstream attribution and source comments are retained.

## What changed from the original?

The original project provides the mounting script and the udev/systemd approach used here. This version adds setup and management features around that foundation:

| Area | Original project | This version |
| --- | --- | --- |
| SteamOS updates | Original installer does not add a custom update keep-list | Keeps the mounting setup across normal SteamOS updates through an update keep-list |
| Installation | Installer downloads files from GitHub | One-command setup or an extracted download |
| Management | Installation script and manual removal commands | One menu with Install and Uninstall |
| Status | No installation-status menu | Shows installation status and configured partitions before setup |
| Internal partitions | Matches device names in udev rules | User selects data partitions; selection is saved by filesystem UUID |
| Local user | Mounting script uses the Steam Deck user and UID | Installer detects the local user, UID and group |
| Repeated mounting | Original mounting logic | Skips already mounted filesystems |
| Steam notifications | Notification errors can fail the service | Notification failure does not invalidate a successful mount |

The supported filesystems and core mounting approach come from the original project. This version does not claim faster storage, support for every Linux distribution, or guaranteed compatibility with future SteamOS updates.

## Install

Open Konsole in Desktop Mode and run:

```sh
curl -fsSL https://raw.githubusercontent.com/HawkingChen/Steam-Deck-Automount/main/setup.sh | bash
```

This opens the menu and lets you select internal data partitions. Run it without `sudo`; setup requests your administrator password when needed. The downloaded program is kept in `~/.local/share/steamdeck-auto-mount` (or `$XDG_DATA_HOME/steamdeck-auto-mount`).

To open the menu later, including to uninstall:

```sh
bash "${XDG_DATA_HOME:-$HOME/.local/share}/steamdeck-auto-mount/install.sh"
```

### Manual download

Download the ZIP from Releases, extract it, and open a terminal in the extracted folder:

```sh
bash install.sh
```

Run as your regular desktop user. The installer requests administrator privileges when applying changes.

The English menu shows the installation status and enabled partitions, then offers:

- **Install**: configure automatic mounting for USB storage and SD cards. Select internal data partitions by number, separated by spaces; leave the selection empty to skip internal partitions.
- **Uninstall**: remove this tool's installed worker, service, rules and update keep-list. Keep the extracted program folder if you want to reinstall later.

Supported filesystems: NTFS, exFAT, ext4 and Btrfs. Mounted filesystems normally appear under `/run/media/<user>/<label-or-UUID>`.

Select internal partitions carefully. Recognized system labels and system mountpoints are excluded, but an unlabeled partition can still be a recovery volume. Only select partitions you recognize as data storage. Reformatted partitions need to be selected again because their UUID changes.

Uninstall does not unmount data filesystems currently in use. SteamOS built-in SD-card mounting may continue after removal.

## SteamOS update persistence

The installer creates `/etc/atomic-update.conf.d/external-drive-automount.conf`. It lists the installed worker, configuration, systemd service and udev rules for preservation by the current SteamOS atomic-update mechanism.

This covers normal updates using that mechanism. It does not cover OS reinstalls, factory resets, or future incompatible changes. An actual SteamOS update with this version installed has not yet been tested.

## Compatibility and configuration

- Requires SteamOS with systemd, UDisks2, Python 3, sudo, util-linux tools, jq and hexdump.
- Installed worker and settings: `/etc/steamdeck-automount/`.
- KDE automatic mounting is disabled during installation to prevent duplicate requests. Its previous configuration is backed up in the user's configuration directory. Uninstall does not automatically re-enable it.
- This version replaces the upstream service and rule names. Use it as an alternative to the original installation, not alongside it.
- Like the original project, it overrides SteamOS's udev rule of the same name. Other tools that modify this rule may conflict.

## Test status

Preview version. Automated checks cover device selection, repeated installation/removal with mocked system commands, generated keep-list entries, and shell syntax. The generated udev rules have also passed validation on the development machine.

Reboot, hotplug, other hardware configurations and OS-update preservation still require real-device testing. Passing automated checks does not establish compatibility with every Steam Deck setup.
