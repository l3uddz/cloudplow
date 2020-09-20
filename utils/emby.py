# import requests
# jellyfin_url="https://snickerpop.com/jellyfin/"
# jellyfin_apikey="70a0a4802cde402395c75bcf78982cb7"
# def jellyfin_active_stream():
#     response=requests.get(jellyfin_url+"Sessions?api_key="+jellyfin_apikey)
#     if response.status_code!=200:
#         return "invalid url"
#     data = response.json()
#     for i in range(0,len(data)):
#         playing=data[i].get("NowPlayingItem")
#         if playing!=None:
#             return True
#         if i==len(data)-1:
#             return False
#
# test=jellyfin_active_stream()
# print(test)
from urllib.parse import urljoin
import requests
import logging
log = logging.getLogger('emby')
class Emby():
    def __init__(self, url, api):
        self.url = url+'Sessions/?api_key='
        self.api = api
    def validate(self):
        try:
            request_url = self.url+self.api
            r = requests.get(request_url, timeout=15, verify=False)
            if r.status_code == 200:
                log.debug("Server responded with status_code=%r, content: %r", r.status_code, r.json())
                return True
            else:
                log.error("Server responded with status_code=%r, content: %r", r.status_code, r.content)
                return False
        except Exception:
            log.exception("Exception validating server api=%r, url=%r: ", self.api, self.url)
            return False
    def get_streams(self):
        try:
            request_url = self.url+self.api
            r = requests.get(request_url, timeout=15, verify=False)
            if r.status_code == 200:
                result = r.json()
                streams=[]
                length=len(result)
                for i in range(0,length):
                    if(result[i].get("NowPlayingItem")!=None):
                        streams.append(result[i].get("NowPlayingItem").get("Name"))
                return streams
            else:
                log.error("Error with URL Server responded with status_code=%r, content: %r", r.status_code, r.content)
                return False
        except Exception:
            log.exception("Exception validating server api=%r, url=%r: ", self.api, self.url)
            return False






