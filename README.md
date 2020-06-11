<img src="assets/logo.svg" width="600" alt="Cloudplow">


[![made-with-python](https://img.shields.io/badge/Made%20with-Python-blue.svg?style=flat-square)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPL%203-blue.svg?style=flat-square)](https://github.com/l3uddz/cloudplow/blob/master/LICENSE.md)
[![last commit (develop)](https://img.shields.io/github/last-commit/l3uddz/cloudplow/develop.svg?colorB=177DC1&label=Last%20Commit&style=flat-square)](https://github.com/l3uddz/cloudplow/commits/develop)
[![Discord](https://img.shields.io/discord/381077432285003776.svg?colorB=177DC1&label=Discord&style=flat-square)](https://discord.io/cloudbox)
[![Contributing](https://img.shields.io/badge/Contributing-gray.svg?style=flat-square)](CONTRIBUTING.md)
[![Donate](https://img.shields.io/badge/Donate-gray.svg?style=flat-square)](#donate)

---

<!-- TOC depthFrom:1 depthTo:2 withLinks:1 updateOnSave:1 orderedList:0 -->

- [Introduction](#introduction)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Sample](#sample)
  - [Core](#core)
  - [Hidden](#hidden)
  - [Notifications](#notifications)
  - [NZBGet](#nzbget)
  - [Plex](#plex)
  - [Remotes](#remotes)
  - [Uploader](#uploader)
  - [Syncer](#syncer)
- [Usage](#usage)
  - [Automatic (Scheduled)](#automatic-scheduled)
  - [Manual (CLI)](#manual-cli)
- [Donate](#donate)

<!-- /TOC -->

---



# Introduction

Cloudplow has 3 main functions:

1. Automatic uploader to Rclone remote : Files are moved off local storage. With support for multiple uploaders (i.e. remote/folder pairings).

2. UnionFS Cleaner functionality: Deletion of UnionFS-Fuse whiteout files (`*_HIDDEN~`) and their corresponding "whited-out" files on Rclone remotes. With support for multiple remotes (useful if you have multiple Rclone remotes mounted).

3. Automatic remote syncer: Sync between two different Rclone remotes using 3rd party VM instances. With support for multiple remote/folder pairings. With support for multiple syncers (i.e. remote/remote pairings).


# Requirements

1. Ubuntu/Debian OS (could work in other OSes with some tweaks).

2. Python 3.5 or higher (`sudo apt install python3 python3-pip`).

3. Required Python modules (see below).

# Installation

1. Clone the Cloudplow repo.

   ```
   sudo git clone https://github.com/l3uddz/cloudplow /opt/cloudplow
   ```

1. Fix permissions of the Cloudplow folder (replace `user`/`group` with your info; run `id` to check).

   ```
   sudo chown -R user:group /opt/cloudplow
   ```

1. Go into the Cloudplow folder.

   ```
   cd /opt/cloudplow
   ```

1. Install Python PIP.

   ```
   sudo apt-get install python3-pip
   ```

1. Install the required python modules.

   ```
   sudo python3 -m pip install -r requirements.txt
   ```

1. Create a shortcut for Cloudplow.

   ```
   sudo ln -s /opt/cloudplow/cloudplow.py /usr/local/bin/cloudplow
   ```

1. Generate a basic `config.json` file.

   ```
   cloudplow run
   ```

1. Configure the `config.json` file.

   ```
   nano config.json
   ```


# Configuration


## Sample

```json
{
    "core": {
        "dry_run": false,
        "rclone_binary_path": "/usr/bin/rclone",
        "rclone_config_path": "/home/seed/.config/rclone/rclone.conf"
    },
    "hidden": {
        "/mnt/local/.unionfs-fuse": {
            "hidden_remotes": [
                "google"
            ]
        }
    },
    "notifications": {
        "Pushover": {
            "app_token": "",
            "service": "pushover",
            "user_token": "",
            "priority": "0"
        },
        "Slack": {
            "webhook_url": "",
            "sender_name": "cloudplow",
            "sender_icon": ":heavy_exclamation_mark:",
            "channel": "",
            "service": "slack"
        }
    },
    "nzbget": {
        "enabled": false,
        "url": "https://user:pass@nzbget.domain.com"
    },
    "plex": {
        "enabled": true,
        "max_streams_before_throttle": 1,
        "ignore_local_streams": true,
        "poll_interval": 60,
        "notifications": false,
        "rclone": {
            "throttle_speeds": {
                "0": "100M",
                "1": "50M",
                "2": "40M",
                "3": "30M",
                "4": "20M",
                "5": "10M"
            },
            "url": "http://localhost:7949"
        },
        "token": "",
        "url": "https://plex.domain.com"
    },
    "remotes": {
        "google": {
            "hidden_remote": "google:",
            "rclone_excludes": [
                "**partial~",
                "**_HIDDEN~",
                ".unionfs/**",
                ".unionfs-fuse/**"
            ],
            "rclone_extras": {
                "--checkers": 16,
                "--drive-chunk-size": "64M",
                "--stats": "60s",
                "--transfers": 8,
                "--verbose": 1,
                "--skip-links": null,
                "--drive-stop-on-upload-limit": null,
                "--user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36"
            },
            "rclone_sleeps": {
                "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 3600
                },
                " 0/s,": {
                    "count": 15,
                    "sleep": 25,
                    "timeout": 140
                }
            },
            "rclone_command": "move",
            "remove_empty_dir_depth": 2,
            "sync_remote": "google:/Backups",
            "upload_folder": "/mnt/local/Media",
            "upload_remote": "google:/Media"
        },
        "google_downloads": {
            "hidden_remote": "",
            "rclone_excludes": [
              "**partial~",
              "**_HIDDEN~",
              ".unionfs/**",
              ".unionfs-fuse/**"
            ],
            "rclone_extras": {
              "--checkers": 32,
              "--stats": "60s",
              "--transfers": 16,
              "--verbose": 1,
              "--skip-links": null
            },
            "rclone_sleeps": {
            },
            "rclone_command": "copy",
            "remove_empty_dir_depth": 2,
            "sync_remote": "",
            "upload_folder": "/mnt/local/Downloads",
            "upload_remote": "google:/Downloads"
        },
        "box": {
            "hidden_remote": "box:",
            "rclone_excludes": [
              "**partial~",
              "**_HIDDEN~",
              ".unionfs/**",
              ".unionfs-fuse/**"
            ],
            "rclone_extras": {
              "--user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36",
              "--checkers": 32,
              "--stats": "60s",
              "--transfers": 16,
              "--verbose": 1,
              "--skip-links": null
            },
            "rclone_sleeps": {
              "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                "count": 5,
                "sleep": 25,
                "timeout": 300
              },
              " 0/s,": {
                  "count": 15,
                  "sleep": 25,
                  "timeout": 140
              }
            },
            "rclone_command": "move",
            "remove_empty_dir_depth": 2,
            "sync_remote": "box:/Backups",
            "upload_folder": "/mnt/local/Media",
            "upload_remote": "box:/Media"
          },
          "google_with_mover": {
              "hidden_remote": "google:",
              "rclone_excludes": [
                  "**partial~",
                  "**_HIDDEN~",
                  ".unionfs/**",
                  ".unionfs-fuse/**"
              ],
              "rclone_extras": {
                  "--checkers": 16,
                  "--drive-chunk-size": "64M",
                  "--stats": "60s",
                  "--transfers": 8,
                  "--verbose": 1,
                  "--skip-links": null
              },
              "rclone_sleeps": {
                  "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                      "count": 5,
                      "sleep": 25,
                      "timeout": 3600
                  },
                  " 0/s,": {
                      "count": 15,
                      "sleep": 25,
                      "timeout": 140
                  }
              },
              "rclone_command": "move",
              "remove_empty_dir_depth": 2,
              "sync_remote": "google:/Backups",
              "upload_folder": "/mnt/local/Media",
              "upload_remote": "google:/Media"
          }
    },
    "syncer": {
        "google2box": {
            "rclone_extras": {
                "--bwlimit": "80M",
                "--checkers": 32,
                "--drive-chunk-size": "64M",
                "--stats": "60s",
                "--transfers": 16,
                "--verbose": 1
            },
            "service": "scaleway",
            "sync_from": "google",
            "sync_interval": 24,
            "sync_to": "box",
            "tool_path": "/home/seed/go/bin/scw",
            "use_copy": true,
            "instance_destroy": false
          }
    },
    "uploader": {
        "google": {
            "can_be_throttled": true,
            "check_interval": 30,
            "exclude_open_files": true,
            "max_size_gb": 400,
            "opened_excludes": [
                "/downloads/"
            ],
            "schedule": {
                "allowed_from": "04:00",
                "allowed_until": "08:00",
                "enabled": false
            },
            "size_excludes": [
                "downloads/*"
            ],
            "service_account_path":"/home/user/.config/cloudplow/service_accounts/"
        },
        "google_downloads": {
            "check_interval": 30,
            "exclude_open_files": true,
            "max_size_gb": 400,
            "opened_excludes": [
            ],
            "schedule": {},
            "size_excludes": [
            ]
        },
        "google_with_mover": {
            "check_interval": 30,
            "exclude_open_files": true,
            "max_size_gb": 400,
            "opened_excludes": [
                "/downloads/"
            ],
            "schedule": {},
            "size_excludes": [
                "downloads/*"
            ],
            "service_account_path":"/home/user/.config/cloudplow/service_accounts/",
            "mover": {
                "enabled": false,
                "move_from_remote": "staging:Media",
                "move_to_remote": "gdrive:Media",
                "rclone_extras": {
                    "--delete-empty-src-dirs": null,
                    "--create-empty-src-dirs": null,
                    "--stats": "60s",
                    "--verbose": 1,
                    "--no-traverse": null,
                    "--drive-server-side-across-configs": null,
                    "--user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36"
                }
            }
        }
    }
}
```


## Core

```
"core": {
    "dry_run": false,
    "rclone_binary_path": "/usr/bin/rclone",
    "rclone_config_path": "/home/seed/.config/rclone/rclone.conf"
},
```

`"dry_run": true` - prevent any files being uploaded or deleted - use this to test out your config.

`rclone_binary_path` - full path to Rclone binary file.

`rclone_config_path` - full path to Rclone config file.

## Hidden

UnionFS Hidden File Cleaner: Deletion of UnionFS whiteout files and their corresponding files on rclone remotes.

```
"hidden": {
    "/mnt/local/.unionfs-fuse": {
        "hidden_remotes": [
            "google"
        ]
    }
},
```

This is where you specify the location of the UnionFS `_HIDDEN~` files (i.e. whiteout files) and the Rclone remotes where the corresponding files will need to be deleted from. You may specify more than one remote here.

The specific remote path, where those corresponding files are, will be specified in the `remotes` section.

Note: If you plan on using this with any other file system, eg MergerFS, you can leave this section blank (`"hidden": {}`).

## Notifications

```json
"notifications": {
  "apprise": {
    "service": "apprise",
    "url": "",
    "title": ""
  }
},
```

Notifications alerts for both scheduled and manual Cloudplow tasks.

Supported `services`:
 - `apprise`
 - `pushover`
 - `slack`

_Note: The key name can be anything, but the `service` key must be must be the exact service name (e.g. `pushover`). See below for example._

```json
"notifications": {
  "anyname": {
    "service": "pushover",
  }
},
```

### Apprise

```json
"notifications": {
  "Apprise": {
    "service": "apprise",
    "url": "",
    "title": ""
  }
},
```

`url` - Apprise service URL (see [here](https://github.com/caronc/apprise)).

 - Required.

`title` - Notification Title.

 - Optional.

 - Default is `Cloudplow`.

### Pushover

```json
"notifications": {
    "Pushover": {
        "app_token": "",
        "service": "pushover",
        "user_token": "",
        "priority": 0
    }
},
```

`app_token`  - App Token from [Pushover.net](https://pushover.net).

 - Required.

`user_token` - User Token from [Pushover.net](https://pushover.net).

 - Required.

`priority` - [Priority](https://pushover.net/api#priority) of the notifications.

 - Optional.

 - Choices are: `-2`, `-1`, `0`, `1`, `2`.

 - Values are not quoted.

 - Default is `0`.

### Slack

```json
"notifications": {
    "Slack": {
        "service": "slack",
        "webhook_url": "",
        "channel": "",
        "sender_name": "Cloudplow",
        "sender_icon": ":heavy_exclamation_mark:"
    }
},
```

`webhook_url` - [Webhook URL](https://my.slack.com/services/new/incoming-webhook/).

 - Required.

`channel` - Slack channel to send the notifications to.

 - Optional.

 - Default is blank.

`sender_name` - Sender's name for the notifications.

 - Optional.

 - Default is `Cloudplow`.

`sender_icon` - Icon to use for the notifications.

 - Optional.

 - Default is `:heavy_exclamation_mark:`


## NZBGet

Cloudplow can pause the NZBGet download queue when an upload starts; and then resume it upon the upload finishing.

```
"nzbget": {
    "enabled": false,
    "url": "https://user:pass@nzbget.domain.com"
},
```

`enabled` - `true` to enable.

`url` - Your NZBGet URL. Can be either `http://user:pass@localhost:6789` or `https://user:pass@nzbget.domain.com`.

## Plex

Cloudplow can throttle Rclone uploads during active, playing Plex streams (paused streams are ignored).


```
"plex": {
    "enabled": true,
    "max_streams_before_throttle": 1,
    "ignore_local_streams": true,
    "poll_interval": 60,
    "notifications": false,
    "rclone": {
        "throttle_speeds": {
            "0": "1000M",
            "1": "50M",
            "2": "40M",
            "3": "30M",
            "4": "20M",
            "5": "10M"
        },
        "url": "http://localhost:7949"
    },
    "token": "",
    "url": "https://plex.domain.com"
},
```


`enabled` - `true` to enable.

`url` - Your Plex URL. Can be either `http://localhost:32400` or `https://plex.domain.com`.

`token` - Your Plex Access Token.

- Run the Plex Token script by [Werner Beroux](https://github.com/wernight): `/opt/cloudplow/scripts/plex_token.sh`.

  or

- Visit https://support.plex.tv/hc/en-us/articles/204059436-Finding-an-authentication-token-X-Plex-Token

`poll_interval` - How often (in seconds) Plex is checked for active streams.

`max_streams_before_throttle` - How many playing streams are allowed before enabling throttling.

`ignore_local_streams` - Whether streaming local files should count for throttling.

`notifications` - Send notifications when throttling is set, adjusted, or unset, depending on stream count.

`rclone`

- `url` - Leave as default.

- `throttle_speed` - Categorized option to configure upload speeds for various stream counts (where `5` represents 5 streams or more). Stream count `0` represents speeds when no active stream is playing. `M` is MB/s.

  - Format: `"STREAM COUNT": "THROTTLED UPLOAD SPEED",`


## Remotes

This is the heart of the configuration, most of the config references this section one way or another (e.g. hidden path references).

You can specify more than one remote here.

#### Basic

```
    "remotes": {
        "google": {
```

Under `"remote"`, you have the name of the remote as the key (in the example above, it is `"google"`). The remote name can be anything (e.g. google1, google2, google3, dropbox1, etc).



#### Hidden Cleaner

```
    "remotes": {
        "google": {
            "hidden_remote": "google:",
```


`"hidden_remote"`: is the remote path where the UnionFS hidden cleaner will remove files from (if the remote is listed under the `hidden` section).

#### Rclone Excludes


```
            "rclone_excludes": [
                "**partial~",
                "**_HIDDEN~",
                ".unionfs/**",
                ".unionfs-fuse/**"
            ],
```

These are the excludes to be used when uploading to this remote.


#### Rclone Extras


```
            "rclone_extras": {
                "--user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36",
                "--checkers": 16,
                "--drive-chunk-size": "64M",
                "--stats": "60s",
                "--transfers": 8,
                "--verbose": 1
            },
```
These are Rclone parameters that will be used when uploading to this remote. You may use the given examples or add your own.

Note: An argument with no value (e.g. `--no-traverse`) will be be given the value `null` (e.g. `"no-traverse": null`).


#### Rclone Sleep (i.e. Ban Sleep)

Format:
```
            "rclone_sleeps": {
                "keyword or phrase to be monitored": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 300
                }
            },
```

Example:

```
            "rclone_sleeps": {
                "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 300
                }
            },
```

`"rclone_sleeps"` are keywords or phrases that are monitored during Rclone tasks that will cause this remote's upload task to abort and go into a sleep for a specified amount of time. When a remote is asleep, it will not do its regularly scheduled uploads (as defined in `check_intervals`).

You may list multiple keywords or phrases here.

In the example above, the phrase `"Failed to copy: googleapi: Error 403: User rate limit exceeded"` is being monitored.

`"count"`: How many times this keyword/phrase has to occur within a specific time period (i.e. `timeout`), from the very first occurrence, to cause the remote to go to sleep.

`"timeout"`: The time period (in seconds) during which the the phrase is counted in after its first occurrence.

  - On its first occurrence, the time is logged and if the `count` is reached within this `timeout` period, the upload task will abort and the remote will go into `sleep`.

  - If the `timeout` period expires without reaching the `count`, the `count` will reset back to `0`.

  - The `timeout` period will restart again after the first new occurrence of the monitored phrase.

`"sleep"`: How many hours the remote goes to sleep for, when the monitored phrase is `count`-ed during the `timeout` period.

#### Rclone Command
```
            "rclone_command": "move",
```
This is the desired command to be used when running any Rclone uploads. Options are `move` or `copy`. Default is `move`.

#### Remove Empty Directories

```
            "remove_empty_dir_depth": 2,
```
This is the depth to min-depth to delete empty folders from relative to `upload_folder`  (1 = `/Media/ ` ; 2 = `/Media/Movies/`; 3 = `/Media/Movies/Movies-Kids/`)


```
            "upload_folder": "/mnt/local/Media/",
            "upload_remote": "google:/Media/"
```

#### Local/Remote Paths


`"upload_folder"`: is the local path that is uploaded by the `uploader` task, once it reaches the size threshold as specified in `max_size_gb`.

`"upload_remote"`: is the remote path that the `uploader` task will uploaded to.

#### Sync From/To Paths

`"sync_remote"`: Used by the `syncer` task. This specifies the from/to destinations used to build the Rclone command. See the [syncer](#syncer) section for more on this.

## Uploader

Each entry to `uploader` references a remote inside `remotes` (i.e. the names have to match). The remote can only be referenced ONCE.

If another folder needs to be uploaded, even to the same remote, then another uploader/remote combo must be created. The example at the top of this page shows 2 uploader/remote configs.

If multiple uploader tasks are specified, the tasks will run sequentially (vs in parallel).

```
"uploader": {
    "google": {
        "can_be_throttled": true,
        "check_interval": 30,
        "exclude_open_files": true,
        "max_size_gb": 500,
        "opened_excludes": [
            "/downloads/"
        ],
        "schedule": {
            "allowed_from": "04:00",
            "allowed_until": "08:00",
            "enabled": false
        },
        "size_excludes": [
            "downloads/*"
        ],
        "service_account_path":"/home/user/config/cloudplow/service_accounts/"
      }
}
```

In the example above, the uploader references `"google"` from the `remotes` section.

`"can_be_throttled"`: When this attribute is missing or set to `true`, this uploader can be throttled if enabled in the Plex config section. When set to `false`, no throttling will be attempted on this uploader.

`"check_interval"`: How often (in minutes) to check the size of this remotes `upload_folder`. Once it reaches the size threshold as specified in `max_size_gb`, the uploader will start.

`"exclude_open_files"`: When set to `true`, open files will be excluded from the Rclone upload (i.e. upload will occur without them).

`"max_size_gb"`: Maximum size (in gigabytes) before uploading can commence

`"opened_excludes"`: Paths the open file checker will check for when searching for open files. In the example above, any open files with `/downloads/` in its path, would be ignored.

`"schedule"`: Allows you to specify a time period, in 24H (HH:MM) format, for when uploads are allowed to start. Uploads in progress will not stop when `allowed_until` is reached.

  - This setting will not affect manual uploads, only the automatic uploader in `run` mode.

`"size_excludes"`: Paths that will not be counted in the total size calculation for `max_size_gb`.

`"service_account_path"`: Path that will be scanned for Google Drive service account keys (\*.json) to be used when performing upload operations.

  - This is currently not supported with sync operations.


### Mover

Move operations occur at the end of an upload task (regardless if the task was successful or aborted).

Can be used to move uploads from one folder to another on the same remote (i.e. server side move) or moves between Google Team Drives and Google "My Drives" with the same ownership (for this we recommend Rclone 1.48+ with the `--drive-server-side-across-configs` argument).

```json
    "mover": {
        "enabled": true,
        "move_from_remote": "staging:Media",
        "move_to_remote": "gdrive:Media",
        "rclone_extras": {
            "--delete-empty-src-dirs": null,
            "--create-empty-src-dirs": null,
            "--stats": "60s",
            "--verbose": 1,
            "--no-traverse": null,
            "--drive-server-side-across-configs": null,
            "--user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36"
        }
    }
```

`"enabled"` - Enable or disable mover function.

`"move_from_remote"` - Where to move the file/folders from.

`"move_to_remote"` - Where to move the file/folders to.

`"rclone_extras"` - Optional Rclone parameters.


## Syncer

Each entry to the `syncer` corresponds to a single sync task.

New `remotes` entries should be created for a single `syncer` task.

Further documentation refers to the example configurations below.

```json
    "remotes": {
        "local_torrents": {
            "hidden_remote": "",
            "rclone_excludes": [],
            "rclone_extras": {},
            "rclone_sleeps": {
                "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 3600
                },
                " 0/s,": {
                    "count": 15,
                    "sleep": 25,
                    "timeout": 140
                }
            },
            "remove_empty_dir_depth": 2,
            "sync_remote": "/mnt/local/downloads/torrents",
            "upload_folder": "",
            "upload_remote": ""
        },
        "google_torrents": {
            "hidden_remote": "",
            "rclone_excludes": [],
            "rclone_extras": {},
            "rclone_sleeps": {},
            "remove_empty_dir_depth": 2,
            "sync_remote": "gdrive:/downloads/torrents",
            "upload_folder": "",
            "upload_remote": ""
        }
    },
    "syncer": {
        "torrents2google": {
            "rclone_extras": {
                "--checkers": 16,
                "--drive-chunk-size": "128M",
                "--stats": "60s",
                "--transfers": 8,
                "--verbose": 1,
                "--fast-list": null
            },
            "service": "local",
            "sync_from": "local_torrents",
            "sync_interval": 26,
            "sync_to": "google_torrents",
            "tool_path": "/usr/bin/rclone",
            "use_copy": false,
            "instance_destroy": false
          }
    },
```

### Remotes

```json
    "remotes": {
        "local_torrents": {
            "hidden_remote": "",
            "rclone_excludes": [],
            "rclone_extras": {},
            "rclone_sleeps": {
                "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 3600
                },
                " 0/s,": {
                    "count": 15,
                    "sleep": 25,
                    "timeout": 140
                }
            },
            "remove_empty_dir_depth": 2,
            "sync_remote": "/mnt/local/downloads/torrents",
            "upload_folder": "",
            "upload_remote": ""
        },
        "google_torrents": {
            "hidden_remote": "",
            "rclone_excludes": [],
            "rclone_extras": {},
            "rclone_sleeps": {},
            "remove_empty_dir_depth": 2,
            "sync_remote": "gdrive:/downloads/torrents",
            "upload_folder": "",
            "upload_remote": ""
        }
    },
```

`sync_remote`: In the example above, there are two remote entries, both of which have  `sync_remote` filled-in. This is used by the syncer task to specify the sync source and destination (i.e. `sync_remote` of `sync_from` remote is the source and `sync_remote` of `sync_to` remote is the destination).

`rclone_sleeps`: Entries from both remotes are collated by the `syncer`, so there is only need for one `rclone_sleeps` to be filled in.

`rclone_extras`: Are not used by the syncer.

### Syncer

```json
    "syncer": {
        "torrents2google": {
            "rclone_extras": {
                "--checkers": 16,
                "--drive-chunk-size": "128M",
                "--stats": "60s",
                "--transfers": 8,
                "--verbose": 1,
                "--fast-list": null
            },
            "service": "local",
            "sync_from": "local_torrents",
            "sync_interval": 26,
            "sync_to": "google_torrents",
            "tool_path": "/usr/bin/rclone",
            "use_copy": false,
            "instance_destroy": false
          }
    },
```

`"rclone_extras"`: These are extra Rclone parameters that will be passed to the Rclone sync command (the `rclone_extras` in the remote entries are not used by the syncer).

`"service"`: Which syncer agent to use for the syncer task. Choices are `local` and `scaleway`. Other service providers can be added in the future.

  - `local`: a remote-to-remote sync that runs locally (i.e. on the same system as the one running Cloudplow).

  - `scaleway`: a remote-to-remote sync that runs on a Scaleway instance. Further documentation will be needed to describe the setup process.

`"sync_from"`: Where the sync is coming FROM.

  - In the example above, this is a local torrents folder.

`"sync_to"`: Where the sync is going TO.

  - In the example above, this is the `gdrive:/downloads/torrents` path.

`"sync_interval"`: How often to execute the sync, in hours. Only applies when Cloudplow is being ran as a service (see [here](#automatic-scheduled)).

`"tool_path"`: Which binary to use to execute the sync.

  - When using the `local` service, this will be the Rclone binary path.

  - When using `scaleway`, this will be the binary path of the `scw` tool.

`"use_copy"`: This tells the syncer to use the `rclone copy` command (vs the default `rclone sync` one). Default is `false`.

`"instance_destroy"`:

  - When this is `true`, the instance that is created for the sync task is destroyed after the task finishes.  This only applies to non-local sync services (e.g. `scaleway`).  

  - When this is set to `false`, it will re-use the existing instance that was previously created/shutdown after the last sync ran.

    - Note: It is able todo this because the instances being created are named after the `syncer` task (e.g. `torrents2google` in the example above). It uses this name to determine if an instance already exists, to start/stop it, rather than destroy it.


# Usage

## Automatic (Scheduled)

To have Cloudplow run automatically, do the following:

1. `sudo cp /opt/cloudplow/systemd/cloudplow.service /etc/systemd/system/`

2. `sudo systemctl daemon-reload`

3. `sudo systemctl enable cloudplow.service`

4. `sudo systemctl start cloudplow.service`

## Manual (CLI)

Command:
```
cloudplow
```

```
usage: cloudplow [-h] [--config [CONFIG]] [--logfile [LOGFILE]]
                 [--loglevel {WARN,INFO,DEBUG}]
                 {clean,upload,sync,run}

Script to assist cloud mount users.
Can remove UnionFS hidden files from Rclone remotes, upload local content to Rclone remotes, and keep Rclone Remotes in sync.

positional arguments:
  {clean,upload,sync,run}
                        "clean": perform clean of UnionFS HIDDEN files from Rclone remotes
                        "upload": perform clean of UnionFS HIDDEN files and upload local content to Rclone remotes
                        "sync": perform sync between Rclone remotes
                        "run": starts the application in automatic mode

optional arguments:
  -h, --help            show this help message and exit
  --config [CONFIG]     Config file location (default: /opt/cloudplow/config.json)
  --logfile [LOGFILE]   Log file location (default: /opt/cloudplow/cloudplow.log)
  --loglevel {WARN,INFO,DEBUG}
                        Log level (default: INFO)
```

***

# Donate

If you find this project helpful, feel free to make a small donation to the developer:

  - [Monzo](https://monzo.me/today): Credit Cards, Apple Pay, Google Pay

  - [Beerpay](https://beerpay.io/l3uddz/cloudplow): Credit Cards

  - [Paypal: l3uddz@gmail.com](https://www.paypal.me/l3uddz)

  - BTC: 3CiHME1HZQsNNcDL6BArG7PbZLa8zUUgjL
