import caldav
import time
from datetime import date, datetime, timedelta

class CalDAVIndicator(object):

    POLL_TIMEOUT = 10 # 10 seconds

    def __init__(self):
        super(CalDAVIndicator, self).__init__()
        self.url = self.username = self.password = None
        self._parse_secret_file()
        self.client = caldav.DAVClient(url = self.url, username =  self.username, password = self.password)
        self.calendar = caldav.Calendar(client = self.client, url = self.url)
        self.current_event = None

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
        while True:
            current_events = self.calendar.date_search(
                start = datetime.now(), end = datetime.now() + timedelta(minutes = 5), expand = False
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
                        print(event_name, event_start, event_end)
                        participant_names = []
                        for p in participants:
                            name = p.params.get('CN')[0]
                            status = p.params.get('PARTSTAT')[0]
                            if status == "ACCEPTED" and not "Konferenzraum" in name:
                                participant_names.append(name)
                        print(participant_names)
            else:
                if self.current_event:
                    print("Ended")
                self.current_event = None
            time.sleep(self.POLL_TIMEOUT)

if __name__ == '__main__':
    CalDAVIndicator().main_loop()
