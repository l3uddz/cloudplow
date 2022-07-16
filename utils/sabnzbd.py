import urllib, json

class Sabnzbd(object):

    def __init__(self, url, apikey=''):
        self.url = url
        self.apikey = apikey

    def request(self, mode, output=True, **kwargs):
        kwargs['apikey'] = self.apikey
        kwargs['mode'] = mode

        if output:
            kwargs['output'] = 'json'
        url = '%s/api?%s' % (
            self.url,
            urllib.parse.urlencode(kwargs)
        )

        try:
           result = urllib.request.urlopen(url)
           if output:
              print("Result is ", result.reason)
           if mode == "pause":
              self.paused = True
           if mode == "resume":   
              self.resumed = True
        except urllib.error.HTTPError as error:
           print("Failed to " + mode +" with error code " + str(error.code)) # 404, 500, etc
           return None

    def pause_queue(self):
        self.paused = False
        self.request('pause')
        return self.paused

    def resume_queue(self):
        self.resumed = False
        self.request('resume')
        return self.resumed

# Can we use this in the furture ??
#    def shutdown(self):
#        self.request('shutdown')

#    def status(self, advanced=False):
#        if advanced:
#            return self.request('status', True)
#        else:
#            return self.request('qstatus', True)

#    def limit(self):
#        try:
#            return self.status(advanced=True)['limit']
#        except:
#            return

#    def setLimit(self, value=0):
#        self.request('config', name='speedlimit', value=value)