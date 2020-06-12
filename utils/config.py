import argparse
import json
import logging
import os
import sys
from copy import copy

log = logging.getLogger('config')


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)

        return cls._instances[cls]


class Config(object):
    __metaclass__ = Singleton

    base_config = {
        # core settings
        'core': {
            'dry_run': False,
            'rclone_binary_path': '/usr/bin/rclone',
            'rclone_config_path': '/home/seed/.config/rclone/rclone.conf'
        },
        # hidden cleaner settings
        'hidden': {
        },
        # uploader settings
        'uploader': {
        },
        # rclone settings
        'remotes': {
        },
        # syncer settings
        'syncer': {
        },
        # notification settings
        'notifications': {
        },
        # plex settings
        'plex': {
            'enabled': False,
            'url': 'https://plex.domain.com',
            'token': '',
            'poll_interval': 60,
            'max_streams_before_throttle': 1,
            'ignore_local_streams': True,
            'notifications': False,
            'rclone': {
                'url': 'http://localhost:7949',
                'throttle_speeds': {
                    '1': '50M',
                    '2': '40M',
                    '3': '30M',
                    '4': '20M',
                    '5': '10M'
                }
            }
        },
        # nzbget settings
        'nzbget': {
            'enabled': False,
            'url': 'https://user:password@nzbget.domain.com'
        }
    }

    base_settings = {
        'config': {
            'argv': '--config',
            'env': 'CLOUDPLOW_CONFIG',
            'default': os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'config.json')
        },
        'logfile': {
            'argv': '--logfile',
            'env': 'CLOUDPLOW_LOGFILE',
            'default': os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'cloudplow.log')
        },
        'cachefile': {
            'argv': '--cachefile',
            'env': 'CLOUDPLOW_CACHEFILE',
            'default': os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'cache.db')
        },
        'loglevel': {
            'argv': '--loglevel',
            'env': 'CLOUDPLOW_LOGLEVEL',
            'default': 'INFO'
        }
    }

    def __init__(self):
        """Initializes config"""
        # Args and settings
        self.args = self.parse_args()
        self.settings = self.get_settings()
        # Configs
        self.configs = None

    @property
    def default_config(self):
        cfg = self.base_config.copy()

        # add example remote
        cfg['remotes'] = {
            'google': {
                'upload_folder': '/mnt/local/Media',
                'upload_remote': 'google:/Media',
                'hidden_remote': 'google:',
                'sync_remote': 'google:/Media',
                'rclone_command': 'move',
                'rclone_excludes': [
                    '**partial~',
                    '**_HIDDEN~',
                    '.unionfs/**',
                    '.unionfs-fuse/**',
                ],
                'rclone_extras': {
                    '--drive-chunk-size': '64M',
                    '--transfers': 8,
                    '--checkers': 16,
                    '--stats': '60s',
                    '--verbose': 1,
                    '--skip-links': None,
                    '--user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 '
                                    '(KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36'
                },
                'rclone_sleeps': {
                    'Failed to copy: googleapi: Error 403: User rate limit exceeded': {
                        'count': 5,
                        'timeout': 3600,
                        'sleep': 25
                    }
                },
                'remove_empty_dir_depth': 2
            }
        }

        # add example uploader
        cfg['uploader'] = {
            'google': {
                'can_be_throttled': True,
                'check_interval': 30,
                'max_size_gb': 200,
                'size_excludes': [
                    'downloads/*'
                ],
                'opened_excludes': [
                    '/downloads/'
                ],
                'exclude_open_files': True,
                'schedule': {
                    'enabled': False,
                    'allowed_from': '04:00',
                    'allowed_until': '08:00'
                }
            }
        }

        # add example hidden
        cfg['hidden'] = {
            '/mnt/local/.unionfs-fuse': {
                'hidden_remotes': ['google']
            }
        }

        return cfg

    def __inner_upgrade(self, settings1, settings2, key=None, overwrite=False):
        sub_upgraded = False
        merged = copy(settings2)

        if isinstance(settings1, dict):
            for k, v in settings1.items():
                # missing k
                if k not in settings2:
                    merged[k] = v
                    sub_upgraded = True
                    if not key:
                        log.info("Added %r config option: %s", str(k), str(v))
                    else:
                        log.info("Added %r to config option %r: %s", str(k), str(key), str(v))
                    continue

                # iterate children
                if isinstance(v, dict) or isinstance(v, list):
                    merged[k], did_upgrade = self.__inner_upgrade(settings1[k], settings2[k], key=k,
                                                                  overwrite=overwrite)
                    sub_upgraded = did_upgrade if did_upgrade else sub_upgraded
                elif settings1[k] != settings2[k] and overwrite:
                    merged = settings1
                    sub_upgraded = True
        elif isinstance(settings1, list) and key:
            for v in settings1:
                if v not in settings2:
                    merged.append(v)
                    sub_upgraded = True
                    log.info("Added to config option %r: %s", str(key), str(v))
                    continue

        return merged, sub_upgraded

    def upgrade_settings(self, currents):
        fields_env = {}

        # ENV gets priority: ENV > config.json
        for name, data in self.base_config.items():
            if name in os.environ:
                # Use JSON decoder to get same behaviour as config file
                fields_env[name] = json.JSONDecoder().decode(os.environ[name])
                log.info("Using ENV setting %s=%s", name, fields_env[name])

        # Update in-memory config with environment settings
        currents.update(fields_env)

        # Do inner upgrade
        upgraded_settings, upgraded = self.__inner_upgrade(self.base_config, currents)
        return upgraded_settings, upgraded

    def upgrade(self, cfg):
        fields = []
        fields_env = {}

        # ENV gets priority: ENV < config.json
        for name, data in self.base_config.items():
            if name not in cfg:
                cfg[name] = data
                fields.append(name)

            if name in os.environ:
                # Use JSON decoder to get same behaviour as config file
                fields_env[name] = json.JSONDecoder().decode(os.environ[name])
                log.info("Using ENV setting %s=%s", name, fields_env[name])

        # Only rewrite config file if new fields added
        if len(fields):
            log.info("Upgraded config. Added %d new field(s): %r", len(fields), fields)
            self.save(cfg)

        # Update in-memory config with environment settings
        cfg.update(fields_env)

        return cfg

    def load(self):
        if not os.path.exists(self.settings['config']):
            log.warning("No config file found, creating default config.")
            self.save(self.default_config)

        cfg = {}
        log.debug("Upgrading config...")
        with open(self.settings['config'], 'r') as fp:
            cfg, upgraded = self.upgrade_settings(json.load(fp))

            # Save config if upgraded
            if upgraded:
                self.save(cfg)
                exit(0)
            else:
                log.debug("Config was not upgraded as there were no changes to add.")

        self.configs = cfg

    def save(self, cfg):
        with open(self.settings['config'], 'w') as fp:
            json.dump(cfg, fp, indent=4, sort_keys=True)

            log.info(
                "Your config was upgraded. You may check the changes here: %r",
                self.settings['config']
            )

        exit(0)

    def get_settings(self):
        setts = {}
        for name, data in self.base_settings.items():
            # Argrument priority: cmd < environment < default
            try:
                value = None
                # Command line argument
                if self.args[name]:
                    value = self.args[name]
                    log.info("Using ARG setting %s=%s", name, value)

                # Envirnoment variable
                elif data['env'] in os.environ:
                    value = os.environ[data['env']]
                    log.debug("Using ENV setting %s=%s" % (
                        data['env'],
                        value
                    ))

                # Default
                else:
                    value = data['default']
                    log.debug("Using default setting %s=%s" % (
                        data['argv'],
                        value
                    ))

                setts[name] = value

            except Exception:
                log.exception("Exception retrieving setting value: %r" % name)

        return setts

    # Parse command line arguments
    def parse_args(self):
        parser = argparse.ArgumentParser(
            description=(
                'Script to assist cloud mount users. \n'
                'Can remove UnionFS hidden files from Rclone remotes, '
                'upload local content to Rclone remotes, and keep Rclone remotes in sync.'
            ),
            formatter_class=argparse.RawTextHelpFormatter
        )

        # Mode
        parser.add_argument('cmd',
                            choices=('clean', 'upload', 'sync', 'run', 'update_config'),
                            help=(
                                '"clean": perform clean of UnionFS HIDDEN files from Rclone remotes\n'
                                '"upload": perform clean of UnionFS HIDDEN files and upload local content to Rclone remotes\n'
                                '"sync": perform sync between Rclone remotes\n'
                                '"run": starts the application in automatic mode\n'
                                '"update_config": perform simple update of config'
                            )
                            )

        # Config file
        parser.add_argument(self.base_settings['config']['argv'],
                            nargs='?',
                            const=None,
                            help='Config file location (default: %s)' % self.base_settings['config']['default']
                            )

        # Log file
        parser.add_argument(self.base_settings['logfile']['argv'],
                            nargs='?',
                            const=None,
                            help='Log file location (default: %s)' % self.base_settings['logfile']['default']
                            )

        # Cache file
        parser.add_argument(self.base_settings['cachefile']['argv'],
                            nargs='?',
                            const=None,
                            help='Cache file location (default: %s)' % self.base_settings['cachefile']['default']
                            )

        # Logging level
        parser.add_argument(self.base_settings['loglevel']['argv'],
                            choices=('WARN', 'INFO', 'DEBUG'),
                            help='Log level (default: %s)' % self.base_settings['loglevel']['default']
                            )

        # Print help by default if no arguments
        if len(sys.argv) == 1:
            parser.print_help()

            sys.exit(0)

        else:
            return vars(parser.parse_args())
