import argparse
import json
import logging
import os
import sys

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
        'dry_run': True,
        'upload_interval': 30,
        'sync_interval': 24,
        # hidden cleaner settings
        'unionfs': {
            '/mnt/local/.unionfs-fuse': {
                'upload_remote': 'google',
                'hidden_remotes': ['google', 'dropbox']
            }
        },
        # mount settings
        'remotes': {
            'google': {
                'upload_folder': '/mnt/local/Media',
                'upload_remote': 'google:/Media',
                'hidden_remote': 'google:',
                'rclone_excludes': [
                    '**partial~',
                    '**_HIDDEN~',
                    '.unionfs/**',
                    '.unionfs-fuse/**',
                ],
                'rclone_extras': {
                    '--drive-chunk-size': '64M',
                    '--transfers': 8,
                    '--checkers': 16
                },
                'rclone_sleep': {
                    '403: userRateLimit exceeded': {
                        'count': 5,
                        'timeout': 300,
                        'sleep': 6
                    }
                }
            },
            'dropbox': {
                'upload_folder': '/mnt/local/Media',
                'upload_remote': 'encdb:/Media',
                'hidden_remote': 'encdb:',
                'rclone_excludes': [
                    '**partial~',
                    '**_HIDDEN~',
                    '.unionfs/**',
                    '.unionfs-fuse/**',
                ],
                'rclone_extras': {
                    '--dropbox-chunk-size': '128M',
                    '--transfers': 8,
                    '--checkers': 16
                },
                'rclone_sleep': {
                    'insufficient space': {
                        'count': 5,
                        'timeout': 300,
                        'sleep': 6
                    }
                }
            }
        },
        # notification settings
        'notifications': {
            'Slackchat': {
                'type': 'slack',
                'webhook_url': 'http://webhook-url-goes-here',
                'sender_name': 'CloudPlow',
                'sender_icon': ':ghost:'
            },
            'Pushover': {
                'type': 'pushover',
                'app_secret': 'app secret goes here',
                'app_key': 'app key goes here'
            }
        }
    }

    base_settings = {
        'config': {
            'argv': '--config',
            'env': 'CLOUDPLOW_CONFIG',
            'default': os.path.join(os.path.dirname(sys.argv[0]), 'config.json')
        },
        'logfile': {
            'argv': '--logfile',
            'env': 'CLOUDPLOW_LOGFILE',
            'default': os.path.join(os.path.dirname(sys.argv[0]), 'cloudplow.log')
        },
        'queuefile': {
            'argv': '--queuefile',
            'env': 'CLOUDPLOW_QUEUEFILE',
            'default': os.path.join(os.path.dirname(sys.argv[0]), 'queue.db')
        },
        'loglevel': {
            'argv': '--loglevel',
            'env': 'CLOUDPLOW_LOGLEVEL',
            'default': 'DEBUG'
        }
    }

    def __init__(self):
        """Initializes config"""
        # Args and settings
        self.args = self.parse_args()
        self.settings = self.get_settings()
        # Configs
        self.configs = None

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
            log.warning("Upgraded config, added %d new field(s): %r", len(fields), fields)
            self.save(cfg)

        # Update in-memory config with environment settings
        cfg.update(fields_env)

        return cfg

    def load(self):
        if not os.path.exists(self.settings['config']):
            log.warning("No config file found, creating default config.")
            self.save(self.base_config)

        cfg = {}
        with open(self.settings['config'], 'r') as fp:
            cfg = self.upgrade(json.load(fp))

        self.configs = cfg

    def save(self, cfg):
        with open(self.settings['config'], 'w') as fp:
            json.dump(cfg, fp, indent=4, sort_keys=True)

            log.warning(
                "Please configure/review config before running again: %r",
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
                    log.info("Using ENV setting %s=%s" % (
                        data['env'],
                        value
                    ))

                # Default
                else:
                    value = data['default']
                    log.info("Using default setting %s=%s" % (
                        data['argv'],
                        value
                    ))

                setts[name] = value

            except:
                log.exception("Exception retrieving setting value: %r" % name)

        return setts

    # Parse command line arguments
    def parse_args(self):
        parser = argparse.ArgumentParser(
            description=(
                'Script to assist cloud mount users. \n'
                'Can remove hidden files from rclone remotes, '
                'upload local content to remotes as-well as keeping remotes \n'
                'in sync with the assistance of Scaleway.'
            ),
            formatter_class=argparse.RawTextHelpFormatter
        )

        # Mode
        parser.add_argument('cmd',
                            choices=('clean', 'upload', 'run'),
                            help=(
                                '"clean": clean HIDDEN files from configured unionfs mounts and rclone remotes\n'
                                '"upload": perform clean and upload local content to configured chosen unionfs rclone remotes\n'
                                '"run": starts the application'
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

        # Queue file
        parser.add_argument(self.base_settings['queuefile']['argv'],
                            nargs='?',
                            const=None,
                            help='Log file location (default: %s)' % self.base_settings['queuefile']['default']
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
