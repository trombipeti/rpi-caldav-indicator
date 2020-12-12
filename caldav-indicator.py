import caldav
import time
from timeit import default_timer as timer
import threading
from datetime import date, datetime, timedelta
try:
    from RPLCD.gpio import CharLCD
    has_lcd = True
except ImportError:
    has_lcd = False
import requests
from requests.auth import HTTPBasicAuth
import json

class CalendarDisplayEvent(object):
    def __init__(self, name, start_time, end_time, participants):
        super(CalendarDisplayEvent, self).__init__()
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.participants = participants

    def __eq__(self, other):
        return other and self.name == other.name and self.start_time == other.start_time and self.end_time == other.end_time


class LCDIndicator(object):

    DISPLAY_UPDATE_FREQ = 5 # Hz

    def __init__(self):
        super(LCDIndicator, self).__init__()
        self.current_event = None
        self.is_lcd_on = False
        self.manual_lcd_status = None
        self._first_line_position = 0
        self._first_line = ""
        self._second_line_position = 0
        self._second_line = ""

        self._display_thread = threading.Thread(target = self._update_display_loop, args = ())
        self._display_thread_lock = threading.Lock()
        self._stop_display_thread = False
        self._event_lock = threading.Lock()

    def force_off_lcd(self):
        self.manual_lcd_status = False
        self._turn_off_lcd()


    def force_on_lcd(self):
        self.manual_lcd_status = True
        self._turn_on_lcd

    def clear_force_lcd(self):
        self.manual_lcd_status = None

    def _turn_off_lcd(self):
        if self.manual_lcd_status != True:
            self.is_lcd_on = False
            if has_lcd:
                pass

    def _turn_on_lcd(self):
        if self.manual_lcd_status != False:
            self.is_lcd_on = True
            if has_lcd:
                pass

    def _scroll_line(self, line, current_start):
        if len(line) <= 16:
            return (line, current_start)
        else:
            double_line = line + " "*6 + line
            line_part = double_line[current_start : current_start + 16]
            if current_start == len(line) + 5:
                current_start = 0
            else:
                current_start += 1
            return (line_part, current_start)

    def _display_first_line(self):
        if has_lcd:
            pass
        elif self.is_lcd_on:
            scroll_data = self._scroll_line(self._first_line, self._first_line_position)
            line = scroll_data[0]
            self._first_line_position = scroll_data[1]
            print("F:", line)

    def _display_second_line(self):
        if has_lcd:
            pass
        elif self.is_lcd_on:
            scroll_data = self._scroll_line(self._second_line, self._second_line_position)
            line = scroll_data[0]
            self._second_line_position = scroll_data[1]
            print("S:", line)

    def _on_new_event(self):
        self._first_line_position = 0
        self._first_line = '{0} {1}-{2}'.format(self.current_event.name, self.current_event.start_time, self.current_event.end_time)
        self._second_line_position = 0
        self._second_line = ', '.join(self.current_event.participants)

    def set_current_event(self, event):
        with self._event_lock:
            new_event = False
            if self.current_event is not None and event is None:
                print(self.current_event.name, "ended")
            elif self.current_event != event:
                new_event = True
            self.current_event = event
            if new_event:
                self._on_new_event()

    def get_current_event(self):
        with self._event_lock:
            return self.current_event

    def start_display_thread(self):
        self._display_thread.start()

    def stop_display_thread(self):
        with self._display_thread_lock:
            self._stop_display_thread = True
        self._display_thread.join()

    def _should_stop_display_thread(self):
        with self._display_thread_lock:
            return self._stop_display_thread

    def _update_display_loop(self):
        while not self._should_stop_display_thread():
            self._update_display()
            time.sleep(1.0 / self.DISPLAY_UPDATE_FREQ)

    def _update_display(self):
        current_event = self.get_current_event()
        if current_event is not None:
            if not self.is_lcd_on:
                self._turn_on_lcd()
            self._display_first_line()
            self._display_second_line()
            pass
        elif self.is_lcd_on:
            self._turn_off_lcd()


class CalDAVIndicator(object):

    POLL_TIMEOUT = 60 # 10 seconds

    def __init__(self):
        super(CalDAVIndicator, self).__init__()
        self.url = self.username = self.password = self.togglApiKey = None
        self._parse_secret_file()
        self.client = caldav.DAVClient(url = self.url, username =  self.username, password = self.password)
        self.calendar = caldav.Calendar(client = self.client, url = self.url)
        self.lcd_indicator = LCDIndicator()

        self._poll_events_thread_lock = threading.Lock()
        self._poll_events_thread = threading.Thread(target = self._poll_events_loop, args = ())
        self._stop_poll_events_thread = False

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

    def _is_working_toggl(self):
        auth = HTTPBasicAuth(self.togglApiKey, 'api_token')
        r = requests.get("https://api.track.toggl.com/api/v8/time_entries/current", auth = auth)
        rd = json.loads(r.text)
        return rd['data'] is not None

    def stop_poll_events_thread(self):
        with self._poll_events_thread_lock:
            self._stop_poll_events_thread = True
        self._poll_events_thread.join()

    def _should_stop_poll_events_thread(self):
        with self._poll_events_thread_lock:
            return self._stop_poll_events_thread

    def _poll_events_loop(self):
        last_poll = None
        while not self._should_stop_poll_events_thread():
            if last_poll is None or timer() - last_poll >= self.POLL_TIMEOUT:
                self._poll_events()
                last_poll = timer()
            time.sleep(0.1)


    def _poll_events(self):
        if self._is_working_toggl() or True:
            current_events = self.calendar.date_search(
                start = datetime.now() - timedelta(days = 3), end = datetime.now(), expand = False
            )
            if len(current_events) > 0:
                current_event = current_events[0]
                event_name = current_event.vobject_instance.vevent.summary.value
                event_start = current_event.vobject_instance.vevent.dtstart.value.strftime("%-H:%M")
                event_end = current_event.vobject_instance.vevent.dtend.value.strftime("%-H:%M")
                participants = current_event.vobject_instance.vevent.contents.get('attendee')
                participant_names = []
                if participants is not None or self.DISPLAY_SINGLE_EVENTS:
                    for p in participants:
                        name = p.params.get('CN')[0]
                        status = p.params.get('PARTSTAT')[0]
                        if status == "ACCEPTED" and not "Konferenzraum" in name and not "Trombitas" in name:
                            if ',' in name:
                                parts = name.split(',')
                                name = parts[1].strip() + ' ' + parts[0].strip()
                            participant_names.append(name)
                    display_event = CalendarDisplayEvent(event_name, event_start, event_end, participant_names)
                    self.lcd_indicator.set_current_event(display_event)
            else:
                self.lcd_indicator.set_current_event(None)
        else:
            self.lcd_indicator.set_current_event(None)

    def _config_menu(self):
        print(
            'Configuration\n'
            ' p: poll timeout\n'
            ' d: display frequency'
        )
        choice = input('> ')
        if choice == 'p':
            try:
                self.POLL_TIMEOUT = float(input('Poll timeout ({0}): '.format(self.POLL_TIMEOUT)))
            except ValueError:
                pass
        elif choice == 'd':
            try:
                prompt = 'Display update frequency ({0}): '.format(self.lcd_indicator.DISPLAY_UPDATE_FREQ)
                self.lcd_indicator.DISPLAY_UPDATE_FREQ = float(input(prompt))
            except ValueError:
                pass

    def _manual_input_menu(self):
        name = input("Event name: ")
        if len(name.strip()) > 0:
            start = datetime.now().strftime("%-H:%M")
            end = input("End: ")
            participants = []
            print("Participants:")
            while True:
                p = input("> ")
                if len(p.strip()) == 0:
                    break
                participants.append(p)
            self.lcd_indicator.set_current_event(CalendarDisplayEvent(name, start, end, participants))

    def _display_menu(self):
        print(
            'Display\n'
            ' on\n'
            ' off\n'
            ' clear'
        )
        choice = input('> ')
        if choice == 'on':
            self.lcd_indicator.force_on_lcd()
        elif choice == 'off':
            self.lcd_indicator.force_off_lcd()
        elif choice == 'clear':
            self.lcd_indicator.clear_force_lcd()

    def _handle_user_input(self):
        print(
            'RPi CalDAV Indicator\n'
            ' c: configure\n'
            ' m: manual event input\n'
            ' d: display menu\n'
            ' q: quit'
        )
        choice = input('> ')
        app_running = True
        if choice == 'c':
            self._config_menu()
        elif choice == 'm':
            self._manual_input_menu()
        elif choice == 'd':
            self._display_menu()
        elif choice == 'q':
            app_running = False
        return app_running

    def main_loop(self):
        self.lcd_indicator.start_display_thread()
        self._poll_events_thread.start()

        while self._handle_user_input():
            pass

        self.lcd_indicator.stop_display_thread()
        self.stop_poll_events_thread()


if __name__ == '__main__':
    CalDAVIndicator().main_loop()
