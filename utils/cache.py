import json
import logging

from sqlitedict import SqliteDict

log = logging.getLogger('cache')


class Cache:
    def __init__(self, cache_file_path):
        self.cache_file_path = cache_file_path
        self.caches = {
            'uploader_bans': SqliteDict(self.cache_file_path, tablename='uploader_bans', encode=json.dumps,
                                        decode=json.loads, autocommit=True),
            'syncer_bans': SqliteDict(self.cache_file_path, tablename='syncer_bans', encode=json.dumps,
                                      decode=json.loads, autocommit=True),
            'sa_bans': SqliteDict(self.cache_file_path,tablename='sa_bans',encode=json.dumps,decode=json.loads,autocommit=True)
        }

    def get_cache(self, cache_name):
        return None if cache_name not in self.caches else self.caches[cache_name]
