
# cloudplow
Automatic rclone remote uploader, with support for multiple remote/folder pairings.  UnionFS Cleaner functionality: Deletion of UnionFS whiteout files  and their corresponding files on rclone remotes. Automatic remote syncer: Sync between different remotes via a Scaleway server instance, that is created and destroyed at every sync.

# Config

```
{
    "core": {
        "dry_run": false
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
            "user_token": ""
        }
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
                "--checkers": 8,
                "--drive-chunk-size": "64M",
                "--no-traverse": null,
                "--stats": "60s",
                "--transfers": 4,
                "--verbose": 1
            },
            "rclone_sleeps": {
                "Failed to copy: googleapi: Error 403: User rate limit exceeded": {
                    "count": 5,
                    "sleep": 25,
                    "timeout": 300
                }
            },
            "remove_empty_dir_depth": 1,
            "upload_folder": "/mnt/local/Media/",
            "upload_remote": "google:/Media/"
        },
    },
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
}
```

