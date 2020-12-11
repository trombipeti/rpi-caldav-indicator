import caldav
import time
from datetime import date, datetime, timedelta
try:
    from RPLCD.gpio import CharLCD
    has_lcd = True
except ImportError:
    has_lcd = False
import requests
from requests.auth import HTTPBasicAuth
import json

class LCDIndicator(object):
    def __init__(self):
        super(LCDIndicator, self).__init__()

class CalDAVIndicator(object):

    POLL_TIMEOUT = 10 # 10 seconds

    def __init__(self):
        super(CalDAVIndicator, self).__init__()
        self.url = self.username = self.password = self.togglApiKey = None
        self._parse_secret_file()
        self.client = caldav.DAVClient(url = self.url, username =  self.username, password = self.password)
        self.calendar = caldav.Calendar(client = self.client, url = self.url)
        self.current_event = None

    def _parse_secret_file(self):
        try:
            with open('secret.txt', 'r') as sf:
                secret_lines = sf.readlines()

            for sl in secret_lines:
                data = sl.split('=')
                key = data[0].strip()
                value = data[1].strip()
                if key == 'url':
                    self.url = value
                elif key == 'username':
                    self.username = value
                elif key == 'password':
                    self.password = value
                elif key == 'togglApiKey':
                    self.togglApiKey = value
            if self.url is None or self.username is None or self.password is None or self.togglApiKey is None:
                raise ValueError("secret.txt malformed")
        except FileNotFoundError:
            print("Secret file not found, creating")
            while self.url is None or len(self.url) == 0:
                self.url = input("Input CalDAV calendar URL: ")
            while self.username is None or len(self.username) == 0:
                self.username = input("Input CalDAV calendar username: ")
            while self.password is None or len(self.password) == 0:
                self.password = input("Input CalDAV calendar password: ")
            while self.password is None or len(self.password) == 0:
                self.password = input("Input toggl API Key: ")
            with open('secret.txt', 'w') as sf:
                sf.write(
                    'url=' + self.url + '\n' +
                    'username=' + self.username + '\n' +
                    'password=' + self.password + '\n' +
                    'togglApiKey=' + self.togglApiKey
                )

    def is_working_toggl(self):
        auth = HTTPBasicAuth(self.togglApiKey, 'api_token')
        r = requests.get("https://api.track.toggl.com/api/v8/time_entries/current", auth = auth)
        rd = json.loads(r.text)
        return rd['data'] is not None

    def main_loop(self):
        first_run = True
        while True:
            if self.is_working_toggl():
                current_events = self.calendar.date_search(
                    start = datetime.now(), end = datetime.now(), expand = False
                )
                if len(current_events) > 0:
                    current_event = current_events[0]
                    if str(self.current_event) != str(current_event):
                        self.current_event = current_event
                        event_name = current_event.vobject_instance.vevent.summary.value
                        event_start = current_event.vobject_instance.vevent.dtstart.value
                        event_end = current_event.vobject_instance.vevent.dtend.value
                        participants = current_event.vobject_instance.vevent.contents.get('attendee')
                        if participants is not None:
                            participant_names = []
                            for p in participants:
                                name = p.params.get('CN')[0]
                                status = p.params.get('PARTSTAT')[0]
                                if status == "ACCEPTED" and not "Konferenzraum" in name:
                                    participant_names.append(name)
                            print(event_name, event_start.strftime("%H:%M") + " - " + event_end.strftime("%H:%M"))
                            print(participant_names)
                        else:
                            print(event_name, "- without participants")
                else:
                    if self.current_event:
                        print("Ended")
                    if first_run:
                        print("No current event")
                    self.current_event = None
            else:
                print("Not working")
            time.sleep(self.POLL_TIMEOUT)
            first_run = False

if __name__ == '__main__':
    CalDAVIndicator().main_loop()
