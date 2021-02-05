#!/usr/bin/env python3

import caldav
import time
from timeit import default_timer as timer
import threading
from datetime import date, datetime, timedelta
try:
    from RPLCD.gpio import CharLCD
    from RPi import GPIO
    has_lcd = True
except ImportError:
    has_lcd = False
import requests
from requests.auth import HTTPBasicAuth
import json
import flask
app = flask.Flask(__name__)

class CalendarDisplayEvent(object):
    def __init__(self, name, start_time, end_time, participants):
        super(CalendarDisplayEvent, self).__init__()
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.participants = participants

    def get_end_datetime(self):
        hm = self.end_time.split(':')
        result = datetime.now()
        try:
            result = result.replace(hour = int(hm[0]), minute = int(hm[1]), second = 59)
        except ValueError:
            pass
        return result

    def __eq__(self, other):
        return other and self.name == other.name and self.start_time == other.start_time and self.end_time == other.end_time


class LCDIndicator(object):

    DISPLAY_UPDATE_FREQ = 1 # Hz
    LCD_E = 8
    LCD_RS = 10
    LCD_RW = 12
    LCD_BL = 13
    LCD_DB4 = 15
    LCD_DB5 = 16
    LCD_DB6 = 19
    LCD_DB7 = 11

    def __init__(self):
        super(LCDIndicator, self).__init__()
        self.current_event = None
        self.is_lcd_on = False
        self.manual_lcd_status = None
        self._first_line = ""
        self._second_line = ""

        self.lcd = None
        if has_lcd:
            self.lcd = CharLCD(
                pin_rs = self.LCD_RS,
                pin_rw = self.LCD_RW,
                pin_e = self.LCD_E,
                pin_backlight = self.LCD_BL,
                backlight_enabled = False,
                backlight_mode = 'active_high',
                numbering_mode = GPIO.BOARD,
                pins_data = [self.LCD_DB4, self.LCD_DB5, self.LCD_DB6, self.LCD_DB7]
            )
            self.lcd.cursor_mode = 'hide'

        self._display_thread = threading.Thread(target = self._update_display_loop, args = ())
        self._display_thread_lock = threading.Lock()
        self._stop_display_thread = False
        self._event_lock = threading.Lock()

    def force_off_lcd(self):
        self.manual_lcd_status = False
        self._turn_off_lcd()


    def force_on_lcd(self):
        self.manual_lcd_status = True
        self._turn_on_lcd()

    def reset_force_lcd(self):
        self.manual_lcd_status = None

    def _turn_off_lcd(self):
        if self.manual_lcd_status != True:
            self.is_lcd_on = False
            if has_lcd:
                self.lcd.backlight_enabled = False

    def _turn_on_lcd(self):
        if self.manual_lcd_status != False:
            self.is_lcd_on = True
            if has_lcd:
                self.lcd.backlight_enabled = True

    def _display_first_line(self):
        if has_lcd:
            self.lcd.cursor_pos = (0, 0)
            self.lcd.write_string(self._first_line)
        elif self.is_lcd_on:
            print('F:', self._first_line)

    def _display_second_line(self):
        if has_lcd:
            self.lcd.cursor_pos = (1, 0)
            self.lcd.write_string(self._second_line)
        elif self.is_lcd_on:
            print('S:', self._second_line)

    def _on_new_event(self):
        if has_lcd:
            self.lcd.clear()
            self.lcd.cursor_pos = (0, 0)
            self.lcd.cursor_mode = 'hide'
            time.sleep(1)
        self._first_line = 'Meeting' if len(self.current_event.name) > 16 else self.current_event.name
        self._second_line = '{0}-{1}'.format(self.current_event.start_time, self.current_event.end_time)

    def set_current_event(self, event):
        with self._event_lock:
            print("Set current event:", event.name if event is not None else event)
            new_event = False
            if self.current_event is not None and event is None:
                print(self.current_event.name, "ended", self.current_event.end_time)
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

        if has_lcd:
            self.lcd.clear()
            self.force_off_lcd()
            GPIO.cleanup()

    def _update_display(self):
        current_event = self.get_current_event()
        if current_event is not None:
            if not self.is_lcd_on:
                self._turn_on_lcd()
            self._display_first_line()
            self._display_second_line()
            pass
        elif self.is_lcd_on:
            self.lcd.clear()
            self._turn_off_lcd()


class CalDAVIndicator(object):

    POLL_TIMEOUT = 20 # seconds
    DISPLAY_SINGLE_EVENTS = True

    def __init__(self):
        super(CalDAVIndicator, self).__init__()
        self.url = self.username = self.password = self.togglApiKey = None
        self._parse_secret_file()
        self.client = caldav.DAVClient(url = self.url, username =  self.username, password = self.password)
        self.calendar = caldav.Calendar(client = self.client, url = self.url)
        self.lcd_indicator = LCDIndicator()

        self._last_event_was_manual = False

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
        print('Toggl response:', r.text)
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

    def _on_poll_no_events(self):
        if not self._last_event_was_manual:
            self.lcd_indicator.set_current_event(None)
        else:
            if self.lcd_indicator.get_current_event().get_end_datetime() < (datetime.now() + timedelta(minutes = 5)):
                self.lcd_indicator.set_current_event(None)

    def _poll_events(self):
        print(datetime.now(), "POLL")
        if self._is_working_toggl():
            current_events = self.calendar.date_search(
                start = datetime.now() - timedelta(minutes = 5), end = datetime.now() + timedelta(minutes = 5), expand = False
            )
            if len(current_events) > 0:
                current_event = current_events[0]
                event_name = current_event.vobject_instance.vevent.summary.value
                event_start = current_event.vobject_instance.vevent.dtstart.value.strftime("%-H:%M")
                event_end = current_event.vobject_instance.vevent.dtend.value.strftime("%-H:%M")
                participants = current_event.vobject_instance.vevent.contents.get('attendee')
                participant_names = []
                if participants is not None or self.DISPLAY_SINGLE_EVENTS:
                    participants = [] if participants is None else participants
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
                    self._last_event_was_manual = False
            else:
                print('No events')
                self._on_poll_no_events()
        else:
            print('Not working')
            self._on_poll_no_events()

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
        name = input("Event name (empty to clear): ")
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
            self._last_event_was_manual = True
        else:
            self.lcd_indicator.set_current_event(None)

    def _display_menu(self):
        print(
            'Display\n'
            ' on\n'
            ' off\n'
            ' reset'
        )
        choice = input('> ')
        if choice == 'on':
            self.lcd_indicator.force_on_lcd()
        elif choice == 'off':
            self.lcd_indicator.force_off_lcd()
        elif choice == 'reset':
            self.lcd_indicator.reset_force_lcd()

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

indicator = None

@app.route('/')
def show_homepage():
    return flask.render_template('index.html')

@app.route('/update-event', methods=['POST'])
def update_event():
    name = flask.request.form["event-name"]
    start = flask.request.form["event-start"]
    end = flask.request.form["event-end"]
    new_event = CalendarDisplayEvent(name, start, end, [])
    indicator.lcd_indicator.set_current_event(new_event)
    return flask.redirect('/')

if __name__ == '__main__':
    indicator = CalDAVIndicator()
    indicator_thread = threading.Thread(target = indicator.main_loop, args = ())
    indicator_thread.start()
    app.run(host = '192.168.0.70', port = '5000')
