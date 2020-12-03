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
            if self.url is None or self.username is None or self.password is None:
                raise ValueError("secret.txt malformed")
        except FileNotFoundError:
            print("Secret file not found, creating")
            self.url = input("Input CalDAV calendar URL: ")
            self.username = input("Input CalDAV calendar username: ")
            self.password = input("Input CalDAV calendar password: ")
            with open('secret.txt', 'w') as sf:
                sf.write(
                    f'url={self.url}\n'
                    f'username={self.username}\n'
                    f'password={self.password}'
                )

    def main_loop(self):
        first_run = True
        while True:
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
                if first_run:
                    print("No current event")
                self.current_event = None
            time.sleep(self.POLL_TIMEOUT)
            first_run = False

if __name__ == '__main__':
    CalDAVIndicator().main_loop()
