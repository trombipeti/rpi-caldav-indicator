import caldav
from datetime import date, datetime, timedelta, tzinfo
import pytz

class CalDAVIndicator(object):

    POLL_TIMEOUT = 10 # 10 seconds

    def __init__(self):
        super(CalDAVIndicator, self).__init__()
        self.url = self.username = self.password = None
        self._parse_secret_file()
        self.client = caldav.DAVClient(url = self.url, username =  self.username, password = self.password)
        self.calendar = caldav.Calendar(client = self.client, url = self.url)

    def _parse_secret_file(self):
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

    def main_loop(self):
        todays_events = self.calendar.date_search(start = datetime.now(), end = datetime.now(), expand = False)
        for te in todays_events:
            event_name = te.vobject_instance.vevent.summary.value
            event_start = te.vobject_instance.vevent.dtstart.value
            event_end = te.vobject_instance.vevent.dtend.value
            participants = te.vobject_instance.vevent.contents.get('attendee')
            if participants is not None:
                print(event_name, event_start, event_end)

if __name__ == '__main__':
    CalDAVIndicator().main_loop()
