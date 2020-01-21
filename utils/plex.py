import logging
import platform
from urllib.parse import urljoin
from uuid import getnode

import requests

log = logging.getLogger('plex')


class Plex:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.headers = {
            'X-Plex-Token': self.token,
            'Accept': 'application/json',
            'X-Plex-Provides': 'controller',
            'X-Plex-Platform': platform.uname()[0],
            'X-Plex-Platform-Version': platform.uname()[2],
            'X-Plex-Product': 'cloudplow',
            'X-Plex-Version': '0.9.5',
            'X-Plex-Device': platform.platform(),
            'X-Plex-Client-Identifier': str(hex(getnode()))
        }

    def validate(self):
        try:
            request_url = urljoin(self.url, 'status/sessions')
            r = requests.get(request_url, headers=self.headers, timeout=15, verify=False)
            if r.status_code == 200 and r.headers['Content-Type'] == 'application/json':
                log.debug("Server responded with status_code=%r, content: %r", r.status_code, r.json())
                return True
            else:
                log.error("Server responded with status_code=%r, content: %r", r.status_code, r.content)
                return False
        except Exception:
            log.exception("Exception validating server token=%r, url=%r: ", self.token, self.url)
            return False

    def get_streams(self):
        request_url = urljoin(self.url, 'status/sessions')
        try:
            r = requests.get(request_url, headers=self.headers, timeout=15, verify=False)
            if r.status_code == 200 and r.headers['Content-Type'] == 'application/json':
                result = r.json()
                log.debug("Server responded with status_code=%r, content: %r", r.status_code, r.content)

                if 'MediaContainer' not in result:
                    log.error("Failed to retrieve streams from server at %r", self.url)
                    return None
                elif 'Video' not in result['MediaContainer'] and 'Metadata' not in result['MediaContainer']:
                    log.debug("There were no streams to check for server at %r", self.url)
                    return []

                streams = []
                for stream in result['MediaContainer']['Video' if 'Video' in result['MediaContainer'] else 'Metadata']:
                    streams.append(PlexStream(stream))
                return streams

            else:
                log.error(
                    "Server url or token was invalid, token=%r, request_url=%r, status_code=%r, content: %r",
                    self.token, request_url, r.status_code, r.content)
                return None
        except Exception:
            log.exception("Exception retrieving streams from request_url=%r, token=%r: ", request_url, self.token)
            return None


# helper classes (parsing responses etc...)
class PlexStream:
    def __init__(self, stream):
        if 'User' in stream:
            self.user = stream['User']['title']
        else:
            self.user = 'Unknown'

        if 'Player' in stream:
            self.player = stream['Player']['product']
            self.ip = stream['Player']['remotePublicAddress']
            self.state = stream['Player']['state']
            self.local = stream['Player']['local']
        else:
            self.player = 'Unknown'
            self.ip = 'Unknown'
            self.state = 'Unknown'
            self.local = None

        if 'Session' in stream:
            self.session_id = stream['Session']['id']
        else:
            self.session_id = 'Unknown'

        if 'Media' in stream:
            self.type = self.get_decision(stream['Media'])
        else:
            self.type = 'Unknown'

        if self.type == 'transcode':
            if 'TranscodeSession' in stream:
                self.video_decision = stream['TranscodeSession']['videoDecision']
                self.audio_decision = stream['TranscodeSession']['audioDecision']
            else:
                self.video_decision = 'Unknown'
                self.audio_decision = 'Unknown'
        else:
            self.video_decision = 'directplay'
            self.audio_decision = 'directplay'

        if 'title' not in stream or 'type' not in stream:
            self.title = 'Unknown'
        else:
            if stream['type'] == 'episode':
                self.title = u"{} {}x{}".format(stream['grandparentTitle'], stream['parentIndex'], stream['index'])
            else:
                self.title = stream['title']

    @staticmethod
    def get_decision(medias):
        for media in medias:
            if 'Part' not in media:
                continue
            for part in media['Part']:
                if 'decision' in part:
                    return part['decision']
        return 'Unknown'

    def __str__(self):
        if self.type == 'transcode':
            transcode_type = "("
            if self.video_decision == 'transcode':
                transcode_type += "video"
            if self.audio_decision == 'transcode':
                if 'video' in transcode_type:
                    transcode_type += " & "
                transcode_type += "audio"
            transcode_type += ")"
            stream_type = "transcode {}".format(transcode_type)
        else:
            stream_type = self.type

        return u"{user} is playing {media} using {player}. " \
               "Stream state: {state}, local: {local}, type: {type}.".format(user=self.user,
                                                                             media=self.title,
                                                                             player=self.player,
                                                                             state=self.state,
                                                                             local=self.local,
                                                                             type=stream_type)

    def __repr__(self):
        return str(self)
