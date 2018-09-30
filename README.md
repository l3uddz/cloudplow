# Cloudplow

[![made-with-python](https://img.shields.io/badge/Made%20with-Python-blue.svg)](https://www.python.org/)
[![License: GPL 3](https://img.shields.io/badge/License-GPL%203-blue.svg)](https://github.com/l3uddz/cloudplow/blob/master/LICENSE.md)
[![Discord](https://img.shields.io/discord/381077432285003776.svg?colorB=177DC1&label=Discord)](https://discord.io/cloudbox)
[![Feature Requests](https://img.shields.io/badge/Requests-Feathub-blue.svg)](http://feathub.com/l3uddz/cloudplow)

---

<!-- TOC depthFrom:1 depthTo:2 withLinks:1 updateOnSave:1 orderedList:0 -->

- [Introduction](#introduction)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
	- [Sample config.json](#sample-configjson)
	- [Core](#core)
	- [Hidden](#hidden)
	- [Notifications](#notifications)
	- [Plex](#plex)
	- [Remotes](#remotes)
	- [Uploader](#uploader)
- [Usage](#usage)
	- [Automatic (Scheduled)](#automatic-scheduled)
	- [Manual (CLI)](#manual-cli)

<!-- /TOC -->

---



# Introduction

Cloudplow has 3 main functions:

1. Automatic uploader to Rclone remote : Files are moved off local storage. With support for multiple uploaders (i.e. remote/folder pairings).

2. UnionFS Cleaner functionality: Deletion of UnionFS-Fuse whiteout files (*_HIDDEN~) and their corresponding "whited-out" files on Rclone remotes. With support for multiple remotes (useful if you have multiple Rclone remotes mounted).

3. Automatic remote syncer: Sync between two different Rclone remotes using 3rd party VM instances. With support for multiple remote/folder pairings. With support for multiple syncers (i.e. remote/remote pairings).


# Requirements

1. Ubuntu/Debian

2. Python 3.5 or higher (`sudo apt install python3 python3-pip`).

3. requirements.txt modules (see below).

# Installation

1. `cd /opt`

1. `sudo git clone https://github.com/l3uddz/cloudplow`

1. `sudo chown -R user:group cloudplow` (run `id` to find your user / group)

1. `cd cloudplow`

1. `sudo python3 -m pip install -r requirements.txt`

1. `sudo ln -s /opt/cloudplow/cloudplow.py /usr/local/bin/cloudplow`

1. `cloudplow` - run once to generate a default config.json file.

1. `nano config.json` - edit preferences.


# Configuration


## Sample config.json

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
    "plex": {
        "enabled": true,
        "max_streams_before_throttle": 1,
        "poll_interval": 60,
        "verbose_notifications": false,
        "rclone": {
            "throttle_speeds": {
                "1": "50M",
                "2": "40M",
                "3": "30M",
                "4": "20M",
                "5": "10M"
            },
            "url": "http://localhost:7949"
        },
        "token": "",
        "url": "https://plex.cloudbox.media"
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
                "--no-traverse": null,
                "--stats": "60s",
                "--transfers": 8,
                "--verbose": 1
            },
            "rclone_sleeps": {
                "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 3600
                }
            },
            "remove_empty_dir_depth": 2,
            "sync_remote": "google:/Backups",
            "upload_folder": "/mnt/local/Media",
            "upload_remote": "google:/Media"
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
            "--checkers": 32,
            "--no-traverse": null,
            "--stats": "60s",
            "--transfers": 16,
            "--verbose": 1
          },
          "rclone_sleeps": {
            "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
              "count": 5,
              "sleep": 25,
              "timeout": 300
            }
          },
          "remove_empty_dir_depth": 2,
          "sync_remote": "box:/Backups",
          "upload_folder": "/mnt/local/Media",
          "upload_remote": "box:/Media"
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
            "check_interval": 30,
            "exclude_open_files": true,
            "max_size_gb": 400,
            "opened_excludes": [
                "/downloads/"
            ],
            "size_excludes": [
                "downloads/*"
            ]
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

`"dry_run": true` will prevent any files being uploaded or deleted - use this to test out your config.


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

This is where you specify the location of the unionfs _HIDDEN~ files (i.e. whiteout files) and the rclone remotes where the corresponding files will need to be deleted from. You may specify than one remote here.

The specific remote path, where those corresponding files are, will be specified in the `remotes` section.


## Plex

Cloudplow can throttle Rclone uploads during active, playing Plex streams (paused streams are ignored).


```
    "plex": {
        "enabled": true,
        "max_streams_before_throttle": 1,
        "poll_interval": 60,
        "verbose_notifications": false,
        "rclone": {
            "throttle_speeds": {
                "1": "50M",
                "2": "40M",
                "3": "30M",
                "4": "20M",
                "5": "10M"
            },
            "url": "http://localhost:7949"
        },
        "token": "",
        "url": "https://plex.cloudbox.media"
    },
```


`enabled` - `true` to enable.

`url` - Your Plex URL.

`token` - Your Plex Access Token.

`poll_interval` - How often (in seconds) Plex is checked for active streams.

`max_streams_before_throttle` - How many playing streams are allowed before enabling throttling.

`verbose_notifications` - Send notifications when rate limit is adjusted due to more/less streams.

`rclone`

- `url` - Leave as default.

- `throttle_speed` - Categorized option to configure upload speeds for various stream counts (where `5` represents 5 streams or more). `M` is MB/s.

  - Format: `"STREAM COUNT": "THROTTLED UPLOAD SPEED",`




## Notifications

Notification alerts during tasks.


Currently, only Pushover and Slack are supported. But more will be added later.

### Pushover

```
    "notifications": {
        "Pushover": {
            "app_token": "",
            "service": "pushover",
            "user_token": "",
            "priority": 0
        }
    },
```

Retrieve `app_token` and `user_token` from Pushover.net and fill it in.

You can specify a priority for the messages send via Pushover using the `priority` key. It can be any Pushover priority value (https://pushover.net/api#priority)

Note: The key name can be anything (e.g. `"Pushover":`), however, the `"service"` must be `"pushover"`.

### Slack

```
    "notifications": {
        "Slack": {
            "webhook_url": "",
	    "sender_name": "cloudplow",
	    "sender_icon": ":heavy_exclamation_mark:",
	    "channel": "",
            "service": "slack"
        }
    },
```

Retrieve the `webhook_url` when registering your webhook to Slack
(via https://my.slack.com/services/new/incoming-webhook/).

You can use `sender_name`, `sender_icon` and `channel` to specify settings
for your webhook. You can however leave these out and use the defaults.

Note: The key name can be anything (e.g. `"Slack":`), however, the `"service"` must be `"slack"`.


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


`"hidden_remote"`: is the remote path where the unionfs hidden cleaner will remove files from (if the remote is listed under the `hidden` section).

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
                "--checkers": 16,
                "--drive-chunk-size": "64M",
                "--no-traverse": null,
                "--stats": "60s",
                "--transfers": 8,
                "--verbose": 1
            },
```
These are rclone parameters that will be used when uploading to this remote. You may add other rclone parameters.

Note: a value of null will mean `--no-traverse` instead of `--no-traverse=null`.


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



`"rclone_sleeps"` are keywords or phrases that are monitored during rclone tasks that will cause this remote's upload task to abort and go into a sleep for a specified amount of time. When a remote is asleep, it will not do it's regularly scheduled uploads (as definted in `check_intervals`).

You may list multiple keywords or phrases here.

In the example above, the phrase `"Failed to copy: googleapi: Error 403: User rate limit exceeded"` is being monitored.

`"count"`: How many times this keyword/phrase has to occur within a specific time period (i.e. `timeout`), from the very first occurrence, to cause the remote to go to sleep.

`"timeout"`: The time period (in seconds) during which the the phrase is counted in after its first occurance.

  - On it's first occurrence, the time is logged and if `count` is reached within this `timeout` period, the upload task will abort and the remote will go into `sleep`.

  - If the `timeout` period expires without reaching the `count`, the `count` will reset back to `0`.

  - The `timeout` period will restart again after the first new occurance of the monitored phrase.

`"sleep"`: How many hours the remote goes to sleep for, when the monitored phrase is `count`-ed during the `timeout` period.

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

`"upload_remote"`: is the remote path that `uploader` task will  uploaded to.




## Uploader

Each entry to `uploader` references a remote inside `remotes`. The remote can only be referenced ONCE.

```
    "uploader": {
        "google": {
            "check_interval": 30,
            "exclude_open_files": true,
            "max_size_gb": 500,
            "opened_excludes": [
                "/downloads/"
            ],
            "size_excludes": [
                "downloads/*"
            ]
          }
    }
```

In the example above, the uploader references `"google"` from the `remotes` section.

`"check_interval"`: how often (in minutes) to check the size of this remotes `upload_folder`. Once it reaches the size threshold as specified in `max_size_gb`, the uploader will start.

`"exclude_open_files"`: when set to `true`, open files will be excluded from the rclone transfer (i.e. transfer will occur without them).

`"max_size_gb"`: maximum size (in gigabytes) before uploading can commence

`"opened_excludes"`: Paths the open file checker will check for when searching for open files. In the example above, any open files with `/downloads/` in it's path, would be ignored.

`"size_excludes"`: Paths that will not be counted in the total size calculation for `max_size_gb`.


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
Can remove hidden files from rclone remotes, upload local content to remotes as-well as keeping remotes
in sync with the assistance of Scaleway.

positional arguments:
  {clean,upload,sync,run}
                        "clean": clean HIDDEN files from configured unionfs mounts and rclone remotes
                        "upload": perform clean and upload local content to configured chosen unionfs rclone remotes
                        "sync": perform sync of configured remotes
                        "run": starts the application

optional arguments:
  -h, --help            show this help message and exit
  --config [CONFIG]     Config file location (default: /opt/cloudplow/config.json)
  --logfile [LOGFILE]   Log file location (default: /opt/cloudplow/cloudplow.log)
  --loglevel {WARN,INFO,DEBUG}
                        Log level (default: INFO)
```
