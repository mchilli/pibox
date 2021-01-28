#!/usr/bin/python3
# -*- coding: utf8 -*-
#
# Author: MCHilli
#
# PiBox folder better be in your home directory
#
# required Python 3:
#   sudo apt-get install python3
#
# required VLC Player:
#   sudo apt-get install vlc
#
# for display support, add in /etc/modules:
#   i2c-bcm2708
#   i2c-dev
#
# for display support, required modules:
#   sudo apt-get install python3-smbus
#
# for detecting display adress, install:
#   sudo apt-get install i2c-tools
# reboot and run:
#   sudo i2cdetect -y 1
#
# for rotary encoder support, required modules:
#   sudo apt-get install python3-rpi.gpio
#
# to run on startup, use:
#   sudo systemctl enable ~/PiBox3/etc/pibox.service
#
# to reading the log, use:
#   sudo journalctl -u pibox.service | tail

__version__ = "3.4.9"

import os
import sys
import subprocess
import re
import threading
import time
import signal
import random
import queue
import json
import collections
import socket
import urllib.parse
import logging

print("| ### PiBox start ###", flush=True)

def signal_term_handler(signal, frame):
    """ system signal handler TERM
    """
    print("| terminated by system", flush=True)
    soft_exit()

def soft_exit():
    """ save exit the script with cleanup
    """
    global keep_running
    keep_running = False

def hard_exit():
    """ hard exit the script without cleanup
    """
    print("| ### PiBox exit ###", flush=True)
    sys.exit(1)

def cleanup():
    """ cleanup before exit
    """
    try:
        lcd.clear()
        lcd.lcd_backlight(0)
        rotenc.clean()
        wss.close_server()
        https.close_server()
        print("| cleaned up", flush=True)
    except Exception as e:
        print("| cleanup error: %s" % e, flush=True)

"""
PREPARATIONS
"""

""" load submodules """
try:
    print("| loading submodules...", flush=True)
    from lib import vlclib
    from lib import webserver
    from lib import websocket
    # from lib import i2clcd
    # from lib import rotenc
except Exception as e:
    print("| import error: %s" % e, flush=True)
    hard_exit()

""" load variables """
config_file_path = os.path.join(os.path.dirname(__file__), "etc/config.json")
try:
    with open(config_file_path, "r", encoding="utf-8-sig") as config_file:
        config = json.load(config_file)
except OSError as e:
    """ default values """
    config = {
        'pibox_name': "PiBox",                # Name for startscreen and site title (max 16 Chars)
        'language': "en",                     # Language
        'default_volume': 30,                 # Default Volume on startup (in %)
        'force_softvol': False,               # Force PiBox to use Software Volume
        'webserver_port': 8080,               # Webserver Port (ports below 1024 require root)
        'websocket_port': 22222,              # Websocket Port
        'theme_primary': "#000000",           # Standard PiBox Theme Primary Color
        'theme_secondary': "#FFFFFF",         # Standard PiBox Theme Secondary Color
        'theme_hover': "#808080",             # Standard PiBox Theme Hover Color
        'pibox_home_dir': "home",             # PiBox Home directory (relativ to pibox directory)
        'pibox_radio_dir': "Radio",           # PiBox Radio directory (relativ to home directory)
        'pibox_playlist_dir': "Playlist",     # PiBox Playlist directory (relativ to home directory)
        'file_extensions': [".mp3", ".MP3"],  # File extensions that insert in playlist
        'enable_lcd': False,                  # Enable LCD Display (True=enable, False=disable)
        'lcd_i2c_addr': "0x27",               # LCD I2C Address
        'lcd_row': 2,                         # LCD Rows
        'lcd_col': 16,                        # LCD Columns
        'display_timeout': 30,                # Timeout for Display Backlight (in s)
        'menu_timeout': 30,                   # Timeout for Menu (in s)
        'enable_re': False,                   # Enable Rotary Encoder (True=enable, False=disable)
        'switch_clk': 17,                     # Rotary Encoder GPIO Pin Clock
        'switch_dt': 27,                      # Rotary Encoder GPIO Pin Direction
        'switch_sw': 22,                      # Rotary Encoder GPIO Pin Switch
        'longpress_delay': 1.0                # Delay for Longpress event(in s)
    }
default = {}
default["pibox_dir"] = os.path.dirname(os.path.realpath(__file__))
default["pibox_home_dir"] = os.path.join(default["pibox_dir"], config["pibox_home_dir"])
default["pibox_radio_dir"] = os.path.join(default["pibox_home_dir"], config["pibox_radio_dir"])
default["pibox_playlist_dir"] = os.path.join(default["pibox_home_dir"], config["pibox_playlist_dir"])

""" check requirements """
if sys.version_info < (3,3):
    print("| Python 3.3 is required, try: sudo apt-get install python3")
    hard_exit()

if config["enable_lcd"]:
    try:
        from lib import i2clcd
    except Exception as e:
        print("| %s" % e)
        print("| Modules required, try: sudo apt-get install python3-smbus")
        print("| continued with disabled LCD!")
        config["enable_lcd"] = False

if config["enable_re"]:
    try:
        from lib import rotenc
    except Exception as e:
        print("| %s" % e)
        print("| Modules required, try: sudo apt-get install python3-rpi.gpio")
        print("| continued with disabled Rotary Encoder!")
        config["enable_re"] = False

if not subprocess.call(["which", "vlc"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL) == 0:
    print("| VLC-Player required, try: sudo apt-get install vlc")
    hard_exit()

default["libvlc_version"] = int(vlclib.bytes_to_str(vlclib.libvlc_get_version())[0])
if default["libvlc_version"] < 3:
    print("| You're libvlc version is %i" % default["libvlc_version"], flush=True)
    print("| VLC-Player performed better with version >= 3.0", flush=True)


"""
MAIN CLASSES
"""


class HTTPServer(threading.Thread):
    """ creates a webserver, serve server files and handle REST API
    """
    daemon = True

    def __init__(self, webserver_port):
        threading.Thread.__init__(self)
        self.port = webserver_port
        self.base_path = os.path.join(os.path.dirname(__file__), "www")
        self.server = webserver.HTTPWebserver(self.port, self.base_path)
        # self.start()

    def run(self):
        self.server.set_fn_do_get(self.do_get)
        self.server.set_fn_do_post(self.do_post)
        self.server.set_fn_log_message(self.log_message)
        self.server.serve_forever()

    def do_get(self, request):
        """ handle the received get request
        """
        if request.path == "/defaults": # return the default config
            return json.dumps({'own_ip': 'localhost' if request.client_address[0] == '127.0.0.1' else sy.get_ip(),
                               'language': config['language'],
                               'base_path': default['pibox_home_dir'],
                               'websocket_port': config['websocket_port'],
                               'vol_mixer': default['vol_mixer'],
                               'theme_primary': config['theme_primary'],
                               'theme_secondary': config['theme_secondary'],
                               'theme_hover': config['theme_hover'],
                               'version': __version__},
                               separators=(',',':'))
        elif request.path == "/manifest": # return the pwa manifest
            manifest = {'short_name': config['pibox_name'],
                        'name': "PiBox - %s" % config['pibox_name'],
                        'icons': [],
                        'start_url': "/",
                        'background_color': config['theme_primary'],
                        'display': "standalone",
                        'theme_color': config['theme_primary']}
            for res in (96, 192, 256, 512):
                icon = {'src': "/img/icon_%s.png" % res,
                        'type': "image/png",
                        'sizes': "%(res)sx%(res)s" % {'res': res}}
                manifest['icons'].append(icon)
            return json.dumps(manifest, separators=(',',':'))
        return None

    def do_post(self, request):
        """ handle the received post request
        """
        if request.path == "/api":
            if request.headers['Content-Type'] == "application/json":
                content_length = int(request.headers['Content-Length'])
                raw_payload = request.rfile.read(content_length).decode("UTF-8")
                try:
                    payload = json.loads(raw_payload)
                except ValueError:
                    print("| API: no valid JSON string")
                    return
                response = self.handle_api(payload)
                if response:
                    request.set_headers("application/json")
                    request.wfile.write(response.encode())

    def handle_api(self, payload):
        """ handle the received commands for API
        """
        if not "command" in payload.keys():
            return False
        cmd = payload['command']
        req = {'command': cmd,
               'response': "ok"}
        if "data" in payload.keys():
            data = payload['data']
        if cmd == "player_play":
            mp.play()
            req['response'] = mp.get_current("play")
        elif cmd == "player_pause":
            mp.pause()
            req['response'] = mp.get_current("pause")
        elif cmd == "player_toggle_pause":
            mp.toggle_pause()
            req['response'] = mp.get_current("toggle")
        elif cmd == "player_stop":
            mp.fake_stop()
            req['response'] = mp.get_current("stop")
        elif cmd == "player_next":
            mp.next()
            time.sleep(.1)
            req['response'] = mp.get_current("play")
        elif cmd == "player_previous":
            mp.previous()
            time.sleep(.1)
            req['response'] = mp.get_current("play")
        elif cmd == "player_playback_mode":
            mp.toggle_playback_mode()
            req['response'] = {'playbackmode': mp.get_playback_mode()}
        elif cmd == "player_get_current":
            req['response'] = mp.get_current()
        elif cmd == "player_set_position":
            req['response'] = {'percent': mp.set_position(float(data)),
                               'position': mp.get_time(),
                               'duration': mp.get_duration()}
        elif cmd == "player_volume_up":
            mp.volume_up()
            time.sleep(.1)
            req['response'] = {'volume': mp.get_volume(1)}
        elif cmd == "player_volume_down":
            mp.volume_down()
            req['response'] = {'volume': mp.get_volume(1)}
        elif cmd == "player_volume_mute":
            mp.volume_mute()
            req['response'] = {'volume': mp.get_volume(1)}
        elif cmd == "player_volume_get":
            req['response'] = {'volume': mp.get_volume(1)}
        elif cmd == "player_volume_set":
            if "data" in locals():
                try:
                    req['response'] = {'volume': mp.set_volume(int(data))}
                except ValueError:
                    req['response'] = "invalid"
        elif cmd == "tracklist_get":
            req['response'] = {'tracklist': mp.get_tracklist()}
        elif cmd == "tracklist_play_new":
            if "data" in locals():
                mp.new_tracklist(data)
                req['response'] = {'tracklist': mp.get_tracklist()}
        elif cmd == "tracklist_add":
            if "data" in locals():
                mp.parse_url(data)
                req['response'] = {'tracklist': mp.get_tracklist()}
        elif cmd == "tracklist_add_random":
            if "data" in locals() and len(data) == 3:
                mp.add_randomly(data[0], int(data[1]), bool(int(data[2])))
                req['response'] = {'tracklist': mp.get_tracklist()}
        elif cmd == "tracklist_play_index":
            if "data" in locals():
                mp.play_index(int(data))
                req['response'] = {'play index': data}
        elif cmd == "tracklist_remove_index":
            if "data" in locals():
                req['response'] = {'remove index': mp.remove_index(data)}
        elif cmd == "tracklist_remove_current":
            req['response'] = {'remove index': mp.remove_index()}
        elif cmd == "tracklist_clear":
            mp.clear_tracklist()
        else:
            req['command'] = "invalid"
            req['response'] = "error"
        return json.dumps(req)

    def log_message(self, address, timestamp, data):
        # print("[%s] : %s %s" % (timestamp, address, data))
        # print("[%s] %s" % (address, data))
        pass

    def close_server(self):
        """ close the webserver
        """
        self.server.server_close()


class WSServer(threading.Thread):
    """ creates a websocket and handle the incoming messages
    """
    daemon = True

    def __init__(self, websocket_port):
        threading.Thread.__init__(self)
        self.websocket_port = websocket_port
        self.server = websocket.WebsocketServer(self.websocket_port, host="")
        # self.start()

    def run(self):
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_message_received(self.on_message)
        self.server.set_fn_client_left(self.left_client)
        self.server.run_forever()

    def new_client(self, client, server):
        """ send nessecary data to new clients
        """
        print("| client connected:  %s[%s](%s)" % (
            client['address'][0], client['address'][1], client['id']),
            flush=True)
        self.send_message(client, {'cmd': "config",
                                   'data': config})
        self.send_message(client, {'cmd': "volume",
                                   'data': mp.get_volume()})
        self.send_message(client, {'cmd': "mode",
                                   'data': mp.get_playback_mode()})
        self.send_message(client, {'cmd': "current",
                                   'data': mp.get_current()})
        # if mp.mlp.is_playing():
        #     self.send_message(client, {'cmd': "current",
        #                                'data': mp.get_current("play")})
        # elif mp.is_paused():
        #     self.send_message(client, {'cmd': "current",
        #                                'data': mp.get_current("pause")})
        # else:
        #     self.send_message(client, {'cmd': "current",
        #                                'data': mp.get_current("stop")})
        self.send_message(client, {'cmd': "tracklist",
                                   'data': mp.get_tracklist()})

    def left_client(self, client, server):
        """ log if a client has left
        """
        if client is not None:
            print("| client disconnect: %s[%s](%s)" % (
                client['address'][0], client['address'][1], client['id']),
                flush=True)

    def on_message(self, client, server, message):
        """ handle the over websocket incomming messages
        """
        message = json.loads(message.encode("latin-1").decode("utf-8"))
        if not "cmd" in message.keys():
            return False
        cmd = message['cmd']
        req = {}
        if "data" in message.keys():
            data = message['data']
        if cmd == "websocket_conn_alive":
            pass
        elif cmd == "system_get_directory":
            req["cmd"] = "directory"
            req["data"] = sy.parse_dir(data)
        elif cmd == "system_change_config":
            sy.change_config(data)
        elif cmd == "system_save_m3u":
            if sy.create_m3u(data):
                req["cmd"] = "toast"
                req["data"] = ("toast.saveList", sy.beauty_path(default["pibox_playlist_dir"]), data)
            else:
                req["cmd"] = "toast"
                req["data"] = "toast.cantSaveList"
        elif cmd == "system_rename_m3u":
            if sy.rename_m3u(data[0], data[1]):
                req["cmd"] = "directory"
                req["data"] = sy.parse_dir(sy.current_dir)
            else:
                req["cmd"] = "toast"
                req["data"] = "toast.cantRenameList"
        elif cmd == "system_delete_m3u":
            if sy.delete_m3u(data):
                req["cmd"] = "directory"
                req["data"] = sy.parse_dir(sy.current_dir)
        elif cmd == "system_reload":
            lcd.lcd_backlight_active()
            sy.restart_script()
        elif cmd == "system_reboot":
            lcd.lcd_backlight_active()
            sy.system_reboot()
        elif cmd == "system_shutdown":
            lcd.lcd_backlight_active()
            sy.system_shutdown()
        elif cmd == "player_toggle_pause":
            lcd.lcd_backlight_active()
            mp.toggle_pause()
        elif cmd == "player_stop":
            lcd.lcd_backlight_active()
            mp.fake_stop()
        elif cmd == "player_next":
            lcd.lcd_backlight_active()
            mp.next()
        elif cmd == "player_previous":
            lcd.lcd_backlight_active()
            mp.previous()
        elif cmd == "player_set_position":
            lcd.lcd_backlight_active()
            mp.set_position(data)
        elif cmd == "player_get_current":
            req["cmd"] = "current"
            req["data"] = mp.get_current()
            # if mp.mp.is_playing():
            #     req["cmd"] = "current"
            #     req["data"] = mp.get_current("play")
        elif cmd == "player_playback_mode":
            lcd.lcd_backlight_active()
            mp.toggle_playback_mode()
        elif cmd == "player_volume_up":
            lcd.lcd_backlight_active()
            mp.volume_up()
        elif cmd == "player_volume_down":
            lcd.lcd_backlight_active()
            mp.volume_down()
        elif cmd == "player_volume_mute":
            lcd.lcd_backlight_active()
            mp.volume_mute()
        elif cmd == "tracklist_play_new":
            lcd.lcd_backlight_active()
            if mp.new_tracklist(data):
                req["cmd"] = "toast"
                if isinstance(data, list):
                    req["data"] = ("toast.playMore", sy.beauty_path(data[0]), len(data) - 1)
                else:
                    req["data"] = ("toast.play", sy.beauty_path(data))
            else:
                req["cmd"] = "toast"
                req["data"] = "toast.cantPlay"
        elif cmd == "tracklist_add":
            lcd.lcd_backlight_active()
            if mp.parse_url(data):
                req["cmd"] = "toast"
                if isinstance(data, list):
                    req["data"] = ("toast.addMore", sy.beauty_path(data[0]), len(data) - 1)
                else:
                    req["data"] = ("toast.add", sy.beauty_path(data))
            else:
                req["cmd"] = "toast"
                req["data"] = "toast.cantAdd"
        elif cmd == "tracklist_add_random":
            lcd.lcd_backlight_active()
            if mp.add_randomly(data[0], data[1], data[2]):
                req["cmd"] = "toast"
                req["data"] = ("toast.addRandom", data[1], sy.beauty_path(data[0]))
            else:
                req["cmd"] = "toast"
                req["data"] = "toast.cantAddRandom"
        elif cmd == "tracklist_play_index":
            lcd.lcd_backlight_active()
            mp.play_index(int(data))
        elif cmd == "tracklist_update":
            req["cmd"] = "tracklist"
            req["data"] = mp.get_tracklist()
        elif cmd == "tracklist_remove_index":
            mp.remove_index(data)
        elif cmd == "tracklist_clear":
            lcd.lcd_backlight_active()
            mp.clear_tracklist()
        else:
            print("| unkown message: %s[%s]" % (cmd, data), flush=True)
        if "cmd" in req.keys():
            if req["cmd"] == "toast":
                self.send_to_all({'cmd': req["cmd"],
                                  'data': req["data"]})
            else:
                self.send_message(client, {'cmd': req["cmd"],
                                           'data': req["data"]})

    def close_server(self):
        """ close the websocket server
        """
        self.server.server_close()

    def send_message(self, client, message):
        """ send a JSON encoded message to a specific client
        """
        data = json.dumps(message, separators=(',',':'))
        self.server.send_message(client, data)

    def send_to_all(self, message):
        """ send a JSON encoded message to all connected clients
        """
        data = json.dumps(message, separators=(',',':'))
        self.server.send_message_to_all(data)


class MediaPlayer():
    """ create, handle and control the media player
    """
    def __init__(self, default_volume):
        # self.vlc = vlclib.Instance(["-A", "alsa", "--no-video"])
        self.vlc = vlclib.Instance(["--no-video", "--quiet"])
        self.mp = self.vlc.media_player_new()
        self.ml = self.vlc.media_list_new()
        self.mlp = self.vlc.media_list_player_new()
        self.declare_volume_mixer()
        self.set_volume(default_volume)
        self.mp.event_manager().event_attach(
            vlclib.EventType.MediaPlayerEndReached, self.on_end_track)
        self.mp.event_manager().event_attach(
            vlclib.EventType.MediaPlayerPlaying, self.on_play)
        self.mp.event_manager().event_attach(
            vlclib.EventType.MediaPlayerPaused, self.on_pause)
        self.mp.event_manager().event_attach(
            vlclib.EventType.MediaPlayerStopped, self.on_stop)
        self.mp.event_manager().event_attach(
            vlclib.EventType.MediaPlayerAudioVolume, self.on_volume_change)
        self.mp.event_manager().event_attach(
            vlclib.EventType.MediaPlayerMediaChanged, self.on_track_change)
        self.mlp.set_media_player(self.mp)
        self.mlp.set_media_list(self.ml)
        self.paused = False
        self.stopped = False
        self.playback_mode = "normal"
        self.tracklist = []
        self.shuffle_list = []

    def on_end_track(self, event):
        """ event handler that handle the next playing file based on
            the playback mode
        """
        playback_mode = self.get_playback_mode()
        next_index = self.get_index() + 1
        if playback_mode == "shuffle":
            return self.do_shuffle("next")
        elif playback_mode == "loop":
            return
        elif next_index == self.ml.count():
            # end of tracklist reached
            lcd.lcd_display_string("%s" % chr(1), 1, 0, 7)
            wss.send_to_all({'cmd': "current",
                             'data': self.get_current("stop")})
            self.update_tracklist()
        else:
            # play next track in list workaround, because of a bug if you delete indecies before current index
            def next(next_index):
                self.mlp.play()
                for i in range(0, 1000):
                    if self.mp.will_play():
                        return self.play_index(next_index)
                    time.sleep(.01)
            threading.Thread(target=next, args=[next_index]).start()

    def on_play(self, event):
        """ event handler that show play icon and current track title on
            display and send play informations to all websocket clients
        """
        lcd.lcd_display_string("%s" % chr(0), 1, 0, 7)
        if not lcd.menu_shown():
            lcd.lcd_display_string("%s" % self.get_title(), 2, 1)
        wss.send_to_all({'cmd': "current",
                         'data': self.get_current("play")})
        self.update_tracklist()
        # self.paused = False


    def on_pause(self, event):
        """ event handler that show pause icon on display and send pause
            informations to all websocket clients
        """
        # lcd.lcd_backlight_active()
        # lcd.lcd_display_string("%s" % chr(2), 1, 0, 7)
        # wss.send_to_all({'cmd': "current",
        #                  'data': self.get_current("pause")})
        # self.update_tracklist()
        # self.paused = True
        pass

    def on_stop(self, event):
        """ event handler that show stop icon and send stop to all
            websocket clients
        """
        lcd.lcd_backlight_active()
        lcd.lcd_display_string("%s" % chr(1), 1, 0, 7)
        wss.send_to_all({'cmd': "current",
                         'data': self.get_current("stop")})
        self.update_tracklist()

    def on_track_change(self, event):
        """ event handler that update tracklist on display
        """
        # self.update_tracklist(ws_send=False)
        pass

    def play(self):
        """ send the play command in single thread to prevent hangs
            on loading
        """
        lcd.lcd_backlight_active()
        if self.stopped:
            self.play_index(self.get_index())
            self.stopped = False
        self.paused = False
        threading.Thread(target=self.mlp.play, daemon=True).start()

    def pause(self):
        """ pause the playback
        """
        if self.mp.is_playing():
            lcd.lcd_backlight_active()
            self.paused = True
            self.mp.set_pause(1)
            lcd.lcd_display_string("%s" % chr(2), 1, 0, 7)
            wss.send_to_all({'cmd': "current",
                             'data': self.get_current("pause")})
            self.update_tracklist()

    def is_paused(self):
        """ return: True if playback is paused
        """
        return self.paused

    def toggle_pause(self):
        """ toggle the playback between play and pause
        """
        if self.mp.is_playing():
            self.pause()
        else:
            if not self.tracklist_empty():
                if not self.paused:
                    wss.send_to_all({'cmd': "current",
                                     'data': self.get_current("load")})
                self.play()

    def fake_stop(self):
        """ fake stop function to prevent a dead end
        """
        lcd.lcd_backlight_active()
        self.mp.set_pause(1)
        self.mp.set_position(0.0)
        self.paused = False
        self.stopped = True
        lcd.lcd_display_string("%s" % chr(1), 1, 0, 7)
        wss.send_to_all({'cmd': "current",
                         'data': self.get_current("stop")})
        self.update_tracklist()

    def next(self):
        """ play the next track based on playback mode
        """
        next_index = self.get_index() + 1
        wss.send_to_all({'cmd': "current",
                         'data': self.get_current("load")})
        if self.get_playback_mode() == "shuffle":
            self.do_shuffle("next")
        else:
            if next_index < self.ml.count():
                self.play_index(next_index)
            else:
                self.play_index(0)
            # if self.mlp.next() == -1: #Bug if you delete indecies before current index
            #     self.play_index(0)

    def previous(self):
        """ play the previous track based on playback mode
        """
        prev_index = self.get_index() - 1
        wss.send_to_all({'cmd': "current",
                         'data': self.get_current("load")})
        if self.get_playback_mode() == "shuffle":
            self.do_shuffle("prev")
        else:
            if prev_index > -1:
                self.play_index(prev_index)
            else:
                self.play_index(self.ml.count() - 1)
            # if self.mlp.previous() == -1: #Bug if you delete indecies before current index
            #     self.play_index(self.ml.count() - 1)

    def get_index(self, media=False):
        """ return the title of track
            args:
                media(instance): return the index of the track
                                 else of the current playing track
        """
        if media:
            return self.ml.index_of_item(media)
        else:
            return self.ml.index_of_item(self.mp.get_media())

    def get_artist(self, index=-1):
        """ return the title of track
            args:
                index(int): return the title of the track at index
                            else of the current playing track
        """
        if index >= 0:
            return vlclib.bytes_to_str(self.ml.item_at_index(index).get_meta(vlclib.Meta.Artist))
        else:
            return vlclib.bytes_to_str(self.mp.get_media().get_meta(vlclib.Meta.Artist))

    def get_title(self, index=-1):
        """ return the title of track
            args:
                index(int): return the title of the track at index
                            else of the current playing track
        """
        if index >= 0:
            return vlclib.bytes_to_str(self.ml.item_at_index(index).get_meta(vlclib.Meta.Title))
        else:
            return vlclib.bytes_to_str(self.mp.get_media().get_meta(vlclib.Meta.Title))

    def get_time(self):
        """ return the time of track in ms
        """
        return self.mp.get_time()

    def get_duration(self, index=-1):
        """ return the duration of track in ms
            args:
                index(int): return the duration of the track at index
                            else of the current playing track
        """
        if index >= 0:
            return self.ml.item_at_index(index).get_duration()
        else:
            return self.mp.get_media().get_duration()

    def get_mrl(self, index=-1, utf8=True):
        """ return the mrl of track
            args:
                index(int): return the mrl of the track at index
                            else of the current playing track
                utf8(bool): if True return the mrl as utf8 encoded string
                            else as url encoded string
        """
        if index >= 0:
            mrl = self.ml.item_at_index(index).get_mrl()
        else:
            mrl = self.mp.get_media().get_mrl()
        mrl = mrl.replace("file://", "")
        return urllib.parse.unquote(mrl) if utf8 else mrl


    def get_state(self):
        """ return current player state
        """
        if self.mlp.is_playing():
            return "play"
        elif self.is_paused():
            return "pause"
        else:
            return "stop"

    def get_current(self, request=None):
        """ return current track informations
            args:
                state(str): ("play", "pause", "stop", "load", "toggle")
                            return direct information based on state
        """
        if request == "load":
            return {'state': "load"}
        elif self.tracklist_empty():
            return {'state': "stop",
                    'error': "empty tracklist"}
        # elif request == "stop":
        #     return {'state': "stop"}
        elif request in ["play", "pause", "stop", "toggle"]:
            state = request
            if request == "toggle":
                search = ['play', 'pause']
            else:
                search = [request]
            while not state in search:
                state = self.get_state()
                time.sleep(.1)
        else:
            state = self.get_state()
        return {'state': state,
                'index': self.get_index(),
                'mrl': self.get_mrl(),
                'artist': self.get_artist(),
                'title': self.get_title(),
                'position': self.get_time(),
                'duration': self.get_duration()}

    def get_position(self):
        """ get current track position as percentage between 0.0 and 1.0.
            return: track position, or -1. in case of error
        """
        return self.mp.get_position()

    def set_position(self, position):
        """ set track position as percentage between 0.0 and 1.0.
            args:
                position(float): the position as percentage between 0.0 and 1.0
            return: track position, or -1. in case of error
        """
        self.mp.set_position(position)
        wss.send_to_all({'cmd': "current",
                         'data': self.get_current()})
        return self.get_position()

    """
    volume control
    """
    def declare_volume_methods(self, mixer):
        """ declare the volume methods to soft or hardware mixer
        """
        functions = ["on_volume_change",
                     "get_volume",
                     "set_volume",
                     "volume_up",
                     "volume_down",
                     "volume_mute"]
        for function in functions:
            setattr(self, function, getattr(self, '%s_%s' % (mixer, function)))

    def declare_volume_mixer(self):
        """ check and set to hardware or software volume mixer
        """
        if config["force_softvol"]:
            mixer = False
        else:
            process = str(subprocess.check_output(['amixer', 'scontrols']))
            regex = "Simple\smixer\scontrol\s\'(?P<mixer>Master|PCM)\'\,\d"
            mixer = re.search(regex, process)
        if mixer:
            print("| use hardware mixer...", flush=True)
            default['vol_mixer'] = "Hardware"
            self.alsa_mixer = mixer.group('mixer')
            self.declare_volume_methods('hw')
            self.mp.audio_set_volume(100)
            threading.Thread(target=self.hw_volume_monitor, daemon=True).start()
        else:
            print("| use software mixer...", flush=True)
            default['vol_mixer'] = "Software"
            self.mute = False
            self.declare_volume_methods('sw')

    def hw_volume_monitor(self):
        """ volume monitor that show hardware volume on display and send volume to all
            websocket clients if volume changed
        """
        process = subprocess.Popen(['stdbuf', '-oL', 'alsactl', 'monitor'],
                                   stdout=subprocess.PIPE)
        for line in iter(process.stdout.readline, ''):
            volume = self.get_volume()
            if volume == 100:
                lcd.lcd_display_string("%s%s%%" % (chr(5), volume), 1, 0)
            else:
                lcd.lcd_display_string("%s%s%% " % (chr(5), volume), 1, 0)
            wss.send_to_all({'cmd': "volume",
                             'data': volume})

    def hw_on_volume_change(self, event):
        """ event handler that set vlc volume back to 100
        """
        if self.mp.audio_get_volume() != 100:
            self.mp.audio_set_volume(100)

    def hw_get_volume(self, advanced=0):
        """ get current hardware audio volume.
            args:
                advanced(bool): return list [volume, state]
            return: the hardware volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        process = str(subprocess.check_output(['amixer', '-M', 'get', self.alsa_mixer]))
        regex = '(Mono|Front Left).*\[(?P<volume>.*)%\].*\[(?P<state>on|off)\]'
        mixer_output = re.search(regex, process)
        volume = int(mixer_output.group('volume'))
        state = mixer_output.group('state')
        if state == 'off':
            volume = 0
        if advanced:
            return [volume, state]
        else:
            return volume

    def hw_set_volume(self, volume):
        """ set hardware audio volume.
            args:
                volume(int): the volume in percent
            return: the hardware volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        volume_old, state = self.get_volume(1)
        if 0 <= volume <= 100:
            if not volume % 5 == 0:
                volume = int(round(volume/10)*10)
            if state == "off":
                subprocess.Popen(['amixer', '-M', '-q', 'set', self.alsa_mixer, 'unmute'])
                subprocess.Popen(['amixer', '-M', '-q', 'set', self.alsa_mixer, '%s%%' % str(volume)])
            else:
                subprocess.Popen(['amixer', '-M', '-q', 'set', self.alsa_mixer, '%s%%' % str(volume)])
        return self.get_volume()

    def hw_volume_up(self, step=5):
        """ increase the hardware audio volume based on step (default=5)
            args:
                step(int): the number of steps the volume will increase
            return: the hardware volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        volume, state = self.get_volume(1)
        if volume < 100:
            if state == "off":
                set_cmd = 'unmute'
            else:
                if not volume % 5 == 0:
                    volume = int(round(volume/10)*10) + step
                else:
                    volume = volume + step
                if volume > 100:
                    volume = 100
                set_cmd = '%s%%' % str(volume)
            subprocess.Popen(['amixer', '-M', '-q', 'set', self.alsa_mixer, set_cmd])
        return self.get_volume()

    def hw_volume_down(self, step=5):
        """ decrease the hardware audio volume based on step (default=5)
            args:
                step(int): the number of steps the volume will decrease
            return: the hardware volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        volume, state = self.get_volume(1)
        if state == "on":
            if volume > 5:
                if not volume % 5 == 0:
                    volume = int(round(volume/10)*10) - step
                else:
                    volume = volume - step
                if volume < 0:
                    volume = 0
                set_cmd = '%s%%' % str(volume)
            else:
                set_cmd = 'mute'
                volume = 0
            subprocess.Popen(['amixer', '-M', '-q', 'set', self.alsa_mixer, set_cmd])
        return self.get_volume()

    def hw_volume_mute(self):
        """ mute the hardware audio volume
            return: the hardware volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        subprocess.Popen(['amixer', '-M', '-q', 'set', self.alsa_mixer, 'toggle'])
        return self.get_volume()

    def sw_on_volume_change(self, event):
        """ event handler that show software volume on display and send volume to all
            websocket clients
        """
        lcd.lcd_backlight_active()
        if self.get_volume() != -1:
            if self.get_volume() == 100:
                lcd.lcd_display_string("%s%s%%" % (chr(5), self.get_volume()), 1, 0)
            else:
                lcd.lcd_display_string("%s%s%% " % (chr(5), self.get_volume()), 1, 0)
            wss.send_to_all({'cmd': "volume",
                             'data': self.get_volume()})

    def sw_get_volume(self):
        """ get current software audio volume.
            return: the software volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        return self.mp.audio_get_volume()

    def sw_set_volume(self, volume):
        """ set software audio volume.
            args:
                volume(int): the volume in percent
            return: the software volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        if 0 <= volume <= 100:
            if not volume % 5 == 0:
                volume = int(round(volume/10)*10)
            self.mp.audio_set_volume(volume)
        return self.get_volume()

    def sw_volume_up(self, step=5):
        """ increase the software audio volume based on step (default=5)
            args:
                step(int): the number of steps the volume will increase
            return: the software volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        if self.get_volume() < 100:
            if self.mute:
                self.set_volume(self.mute)
                self.mute = False
            else:
                self.set_volume(self.get_volume() + step)
        return self.get_volume()

    def sw_volume_down(self, step=5):
        """ decrease the software audio volume based on step (default=5)
            args:
                step(int): the number of steps the volume will decrease
            return: the software volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        self.set_volume(self.get_volume() - step)
        return self.get_volume()

    def sw_volume_mute(self):
        """ mute the software audio volume
            return: the software volume in percents (0 = mute, 100 = nominal / 0dB).
        """
        if self.mute:
            self.set_volume(self.mute)
            self.mute = False
        else:
            self.mute = self.get_volume()
            self.set_volume(0)
        return self.get_volume()

    """
    tracklist handling
    """
    def get_tracklist(self):
        """ get the current tracklist.
            return: the tracklist as a list of dicts.
        """
        # tracklist = []
        # for i in range(0, self.ml.count()):
        #     tracklist.append({"index": i,
        #                       "artist": self.get_artist(i),
        #                       "title": self.get_title(i),
        #                       "mrl": self.get_mrl(i),
        #                       "duration": self.get_duration(i)})
        return self.tracklist

    def reindex_tracklist(self):
        """ reindex the current tracklist.
        """
        for index in range(0, self.ml.count() - 1):
            self.tracklist[index]["artist"] = self.get_artist(index)
            self.tracklist[index]["title"] = self.get_title(index)
            self.tracklist[index]["mrl"] = self.get_mrl(index)
            self.tracklist[index]["duration"] = self.get_duration(index)

    def tracklist_empty(self):
        """ check if tracklist is empty.
            return: True if the tracklist is empty, else False.
        """
        return False if self.ml.count() > 0 else True

    def add_to_tracklist(self, url):
        """ add file to tracklist.
                args:
                    url(str): the complete url of the file, to add.
        """
        self.ml.add_media(url)
        media = self.ml.item_at_index(self.ml.count() - 1)
        index = self.get_index(media)
        self.tracklist.append({"index": index,
                               "artist": self.get_artist(index),
                               "title": self.get_title(index),
                               "mrl": self.get_mrl(index),
                               "duration": self.get_duration(index)})
        if default["libvlc_version"] < 3:
            media.parse_async() # used from libvlc version < 3.0
        else:
            media.parse_with_options(vlclib.MediaParseFlag.do_interact, -1)
        media.event_manager().event_attach(
            vlclib.EventType.MediaParsedChanged, self._media_parsed, media)

    def _media_parsed(self, event, media):
        """ event handler that send the tracklist to all websocket clients,
            if all tracks are parsed
        """
        index = self.get_index(media)
        if index != -1:
            self.tracklist[index]["artist"] = self.get_artist(index)
            self.tracklist[index]["title"] = self.get_title(index)
            self.tracklist[index]["mrl"] = self.get_mrl(index)
            self.tracklist[index]["duration"] = self.get_duration(index)
        if index == self.ml.count() - 1:
            if default["libvlc_version"] < 3:
                if not media.is_parsed(): # used from libvlc version < 3.0
                    return
            else:
                if str(media.get_parsed_status()) != "MediaParsedStatus.done":
                    return
            self.reindex_tracklist()
            wss.send_to_all({"cmd": "tracklist",
                             "data": self.get_tracklist()})

    def new_tracklist(self, url):
        """ delete the current tracklist and start a new one.
                args:
                    url(str): the complete url to a file or directory, to add.
        """
        lcd.lcd_backlight_active()
        lcd.lcd_display_string("%s" % chr(4), 1, 0, 7)
        wss.send_to_all({"cmd": "current",
                         "data": self.get_current("load")})
        self._clean_tracklist()
        self.shuffle_list = []
        self.parse_url(url)
        self.play()
        return True

    def add_randomly(self, url, count=5, clean=True):
        """ adds a count of random files to tracklist.
                args:
                    url(str): the complete url to a directory, to shuffle.
                    count(int): the number of files to add.
                    clean(bool): clean the tracklist before add
        """
        filelist = []
        for root, directories, files in os.walk(url):
            for filename in files:
                if filename.endswith(tuple(config["file_extensions"])):
                    filelist.append(os.path.join(root, filename))
            # break # uncomment break, for not recursive randomly add
        if len(filelist) == 0:
            return False
        if clean:
            self.fake_stop()
            self._clean_tracklist()
        self.shuffle_list = []
        random.shuffle(filelist)
        if count > len(filelist):
            count = len(filelist)
        for i in range(0, count):
            self.add_to_tracklist(filelist[i])
        if self.get_index() + 1 == 0:
            self.mp.set_media(self.ml.item_at_index(0))
        self.update_tracklist()
        if not lcd.menu_shown():
            lcd.lcd_display_string("%s" % mp.get_title(), 2, 1)
        if clean: self.play()
        return True

    def remove_index(self, index=-1, update=True):
        """ remove the index from tracklist.
                args:
                    index(int): the specific index if set, or the current index.
                    index(list): a list of indecies, to remove.
                    update(bool): if true(default) reread the tracklist.
        """
        if self.ml.count() == 1:
            self.clear_tracklist()
            return "empty tracklist"
        if isinstance(index, list):
            for index in reversed(index):
                self.remove_index(index, False)
            self._reread_tracklist()
            self.update_tracklist()
        else:
            index = int(index)
            current = self.get_index()
            if index == -1:
                index = current
            if current == index:
                next = self.ml.item_at_index(current + 1)
                first = self.ml.item_at_index(0)
                if next:
                    if self.mp.is_playing():
                        self.play_index(current + 1)
                    else:
                        self.mp.set_media(next)
                elif first:
                    if self.mp.is_playing():
                        self.play_index(0)
                    else:
                        self.mp.set_media(first)
            self.ml.remove_index(int(index))
            if update:
                self._reread_tracklist()
                self.update_tracklist()
            return int(index)

    def play_index(self, index):
        """ play the index from tracklist.
                args:
                    index(int): the specific index if set, or the zero index.
        """
        self.mlp.play_item_at_index(index)

    def restart_tracklist(self):
        """ restart the tracklist by playing index zero.
        """
        self.play_index(0)

    def _clean_tracklist(self):
        """ remove all tracks from tracklist
        """
        count = self.ml.count()
        if default["libvlc_version"] >= 3:
            for i in range(count):
                media = self.ml.item_at_index(i)
                threading.Thread(target=media.parse_stop).start() # only available in libvlc version >= 3.0
        for i in range(count):
            self.ml.remove_index(0)
        self.tracklist = []

    def clear_tracklist(self):
        """ stop playing and clear the tracklist.
        """
        self.fake_stop()
        self.mp.set_media(self.mp.get_media().release())
        self._clean_tracklist()
        self.update_tracklist()
        if not lcd.menu_shown():
            lcd.lcd_clear_line(2)

    def _reread_tracklist(self):
        """ reread the entire tracklist
        """
        self.tracklist = []
        for i in range(0, self.ml.count()):
            self.tracklist.append({"index": i,
                                   "artist": self.get_artist(i),
                                   "title": self.get_title(i),
                                   "mrl": self.get_mrl(i),
                                   "duration": self.get_duration(i)})

    def update_tracklist(self):
        """ update the tracklist on all display devices
        """
        current = self.get_index() + 1
        total = self.ml.count()
        space = " " * (8 - (len(str(current)) + len(str(total))))
        if total > 0:
            lcd.lcd_display_string("%s%i/%i" % (space, current, total), 1, 0, 8)
        else:
            lcd.lcd_display_string(" " * 9, 1, 0, 8)
        wss.send_to_all({"cmd": "current",
                         "data": self.get_current()})
        wss.send_to_all({"cmd": "tracklist",
                         "data": self.get_tracklist()})

    def parse_url(self, url):
        """ parse the given url to add only playable files.
                args:
                    url(str): the complete url to a file or directory, to add.
                    url(list): a list of urls, to add.
        """
        if isinstance(url, list):
            for file in url:
                self.parse_url(file)
        elif isinstance(url, str):
            if url.startswith(("http://", "https://")):
                self.add_to_tracklist(url)
            elif os.path.isdir(url):
                for root, directories, files in os.walk(url):
                    for filename in sorted(files):
                        if filename.endswith(tuple(config["file_extensions"])):
                            self.add_to_tracklist(os.path.join(root, filename))
            elif os.path.isfile(url):
                if url.endswith(tuple(config["file_extensions"])):
                    self.add_to_tracklist(url)
                elif url.endswith(".m3u"):
                    for file in sy.parse_m3u(url):
                        self.add_to_tracklist(file["path"])
            else:
                print("| cannot open file", flush=True)
        if self.get_index() + 1 == 0:
            self.mp.set_media(self.ml.item_at_index(0))
        self.update_tracklist()
        return True

    """
    playback mode handling
    """
    def do_shuffle(self, direction="next"):
        """ handle the shuffle playback mode
            args:
                direction("next", "prev"): shuffle based on direction
        """
        def shuffle(direction):
            # time.sleep(.1)
            count = self.ml.count()
            if count > 10:
                max = 10
            else:
                max = count
            if direction == "next":
                if len(self.shuffle_list) == max:
                    self.shuffle_list.pop()
                for i in range(0, 10):
                    next_index = random.randint(0, count-1)
                    if not next_index in self.shuffle_list:
                        break
                self.shuffle_list.insert(0, next_index)
                index = self.shuffle_list[0]
            elif direction == "prev":
                if len(self.shuffle_list) > 1:
                    self.shuffle_list.pop(0)
                    index = self.shuffle_list[0]
                else:
                    self.shuffle_list = []
                    return self.do_shuffle("next")
            else:
                return False
            if self.ml.item_at_index(index):
                for i in range(0, 1000):
                    if self.mp.will_play():
                        return self.play_index(index)
                    time.sleep(.01)
                else:
                    print("coud'nt shuffle")
                    return self.do_shuffle(direction)
            else:
                self.shuffle_list.pop(0)
                return self.do_shuffle(direction)
        threading.Thread(target=shuffle, args=[direction]).start()
        # threading.Thread(target=shuffle, args=[direction], daemon=True).start()

    def toggle_playback_mode(self):
        """ loop through the playback modes in order shuffle > loop > normal
        """
        self.shuffle_list = []
        if self.playback_mode == "shuffle":
            self.playback_mode = "loop"
            # self.mlp.set_playback_mode(vlclib.PlaybackMode.loop)
            lcd.lcd_display_string("%s" % chr(6), 1, 0, 6)
        elif self.playback_mode == "loop":
            self.playback_mode = "normal"
            self.mlp.set_playback_mode(vlclib.PlaybackMode.default)
            lcd.lcd_display_string(" ", 1, 0, 6)
        else:
            self.playback_mode = "shuffle"
            self.mlp.set_playback_mode(vlclib.PlaybackMode.loop)
            lcd.lcd_display_string("%s" % chr(3), 1, 0, 6)
        wss.send_to_all({"cmd": "mode",
                         "data": self.get_playback_mode()})

    def get_playback_mode(self):
        """ return playback mode as string: "shuffle", "loop" or "normal"
        """
        return self.playback_mode


class System():
    """
    direct system interaction
    """
    def __init__(self):
        self.current_dir = default["pibox_home_dir"]
        threading.Thread(target=self.check_wifi, daemon=True).start()

    # change config and save to file
    def change_config(self, new_config):
        for property in config:
            config[property] = new_config[property]
        with open(config_file_path, "w", encoding="utf-8-sig") as config_file:
            config_file.write(json.dumps(config, indent=4, ensure_ascii=False))
        self.restart_script()

    # parse the given directory and return a json string
    def parse_dir(self, url):
        if not (os.path.isdir(url) and url.startswith(default["pibox_home_dir"])):
            url = default["pibox_home_dir"]
        self.current_dir = url
        filelist = {"directory": url, "content": []}
        if not url == default["pibox_home_dir"]:
            filelist["content"].append({"type": "back",
                                        "url": url.rsplit("/", 1)[0],
                                        "name": "Return"})
        if url == default["pibox_radio_dir"]:
            for root, directories, files in os.walk(url):
                for file in sorted(files):
                    if file.endswith(".m3u"):
                        for station in self.parse_m3u(os.path.join(root, file)):
                            filelist["content"].append({"type": "radio",
                                                        "url": station["path"],
                                                        "name": station["title"]})
        else:
            for root, directories, files in os.walk(url):
                count = 0
                for dirname in sorted(directories):
                    if not dirname.startswith("."):
                        amount = os.listdir(os.path.join(root, dirname))
                        if not amount == []:
                            url = os.path.join(root, dirname)
                            amount = len(amount)
                            extra = {}
                            count += 1
                            filelist["content"].append({"type": "dir",
                                                        "url": url,
                                                        "name": dirname,
                                                        "extra": extra})
                for filename in sorted(files):
                    url = os.path.join(root, filename)
                    name = os.path.splitext(filename)[0]
                    extra = {}
                    if filename.endswith(tuple(config["file_extensions"])):
                        type = "file"
                    elif filename.endswith(".m3u"):
                        type = "playlist"
                        amount = len(self.parse_m3u(os.path.join(root, filename)))
                        extra["badge"] = amount
                    else:
                        continue
                    count += 1
                    filelist["content"].append({"type": type,
                                                "url": url,
                                                "name": name,
                                                "extra": extra})
                if count == 0:
                    filelist["content"].append({"type": "empty",
                                                "name": "He's dead, Jim!"})
                break
        return filelist


    def beauty_path(self, url):
        """ beautify the given path by replacing home dir with pibox name
            return: the beautify url string
        """
        return url.replace(default["pibox_home_dir"], config["pibox_name"])

    # parse a m3u file and return a list of dicts{"length","title","path"}
    def parse_m3u(self, url):
        try:
            with open(url, "r", encoding="utf-8-sig") as file:
                line = file.readline()
                if not line.startswith("#EXTM3U"):
                    return
                playlist = []
                for line in file:
                    line = line.strip()
                    if line.startswith("#EXTINF:"):
                        self.length, self.title = line.split("#EXTINF:")[1].split(",", 1)
                    elif (len(line) != 0):
                        self.path = line
                        playlist.append({"length": self.length,
                                         "title": self.title,
                                         "path": self.path})
                return playlist
        except OSError as e:
            return

    # create a m3u file out of the current playlist
    def create_m3u(self, file):
        save_path = default["pibox_playlist_dir"]
        if file == "":
            return
        if mp.tracklist_empty():
            return
        if not os.path.isdir(save_path):
            os.makedirs(save_path)
        file = "%s/%s.m3u" % (save_path, file)
        try:
            file = open(file, "w", encoding="utf-8")
        except Exception:
            return
        file.write("#EXTM3U\n")
        for i in range(0, mp.ml.count()):
            file.write("#EXTINF:%d,%s\n" % (
                mp.get_duration(i),
                mp.get_title(i)))
            file.write("%s\n" % mp.get_mrl(i))
        file.close()
        return True

    # rename the selected m3u playlist
    def rename_m3u(self, old_name, new_name):
        if not new_name.endswith('.m3u'):
            new_name = "%s.m3u" % new_name
        new_name = os.path.join(default["pibox_playlist_dir"], new_name)
        try:
            os.rename(old_name, new_name)
        except OSError:
            return False
        return True

    # delete the selected m3u playlist
    def delete_m3u(self, file):
        try:
            os.remove(file)
        except OSError:
            return False
        return True

    # check the wifi connection after 5 minutes all 5 minutes and reconnect it
    def check_wifi(self):
        time.sleep(300)
        while True:
            if self.get_ip() == "no IP found":
                print("| wifi connection error", flush=True)
                self.restart_wifi(False)
            time.sleep(300)

    # get the internal ip or "no IP found"
    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = "no IP found"
        finally:
            s.close()
        return IP

    # show the ip adress on the display
    def show_ip(self):
        lcd.lcd_display_string("<%s>" % (("%s" % self.get_ip()).center(14)), 2, 2)

    # make what it said
    def restart_wifi(self, user=True):
        print("| restart wifi", flush=True)
        if user:
            lcd.lcd_display_string("<%s>" % (("Wait......").center(14)), 2, 2)
        os.system("sudo ifconfig wlan0 down && sleep 5 && sudo ifconfig wlan0 up")
        print("| wifi reconnected", flush=True)
        if user:
            lcd.lcd_display_string("<%s>" % (("Reconnect!").center(14)), 2, 2)

    def restart_script(self):
        print("| restarted script", flush=True)
        if config["enable_lcd"]:
            lcd.restart_script_screen()
            time.sleep(3)
        cleanup()
        os.execv(sys.executable, ["python3"] + sys.argv)

    def system_reboot(self):
        print("| reboot system", flush=True)
        if config["enable_lcd"]:
            lcd.restart_screen()
            time.sleep(3)
        cleanup()
        os.system("sudo reboot")
        hard_exit()

    def system_shutdown(self):
        if config["enable_lcd"]:
            lcd.shutdown_screen()
            time.sleep(3)
        cleanup()
        os.system("sudo shutdown -h now")
        hard_exit()


class RotaryEncoder():
    """
    handle the rotary encoder
    """
    def __init__(self, switch_clk, switch_dt, switch_sw, longpress_delay):
        if config["enable_re"]:
            self.switch_clk = switch_clk
            self.switch_dt = switch_dt
            self.switch_sw = switch_sw
            self.longpress_delay = longpress_delay
            self.encoder = rotenc.Rotary_Encoder(self.switch_clk, self.switch_dt, self.on_turn,
                                                 self.switch_sw, self.on_press,
                                                 self.longpress_delay, self.on_long_press)

    def on_turn(self, direction):
        lcd.lcd_backlight_active()
        # print(direction)
        if direction:
            if lcd.menu_shown():
                lcd.menu_set_active()
                lcd.osm.next_select()
                lcd.update_menu()
            else:
                mp.volume_up()
        else:
            if lcd.menu_shown():
                lcd.menu_set_active()
                lcd.osm.prev_select()
                lcd.update_menu()
            else:
                mp.volume_down()

    def on_press(self):
        lcd.lcd_backlight_active()
        if lcd.menu_shown():
            lcd.menu_set_active()
            type = lcd.osm.get_type()
            # onscreen menu filetypes
            if type == "submenu":
                lcd.osm.set_menu(lcd.osm.get_select()["data"])
                lcd.update_menu()
            elif type == "callback":
                lcd.osm.do_function()
                # lcd.update_menu()
            elif type == "return":
                if lcd.osm.get_parent():
                    lcd.osm.go_parent()
                    lcd.update_menu()
                else:
                    lcd.hide_menu()
            # local path filetypes
            elif type in ("dir", "file", "playlist", "radio"):
                lcd.osm.create_context_menu(type, lcd.osm.get_select()["data"],
                                            lcd.osm.get_select()["name"])
                # lcd.update_menu()
            elif type == "back":
                lcd.osm.create_local_files_menu(lcd.osm.get_select()["data"])
                # lcd.update_menu()
            else:
                print("| osm unkown type: %s" % type, flush=True)
        else:
            mp.toggle_pause()

    def on_long_press(self):
        lcd.lcd_backlight_active()
        if not lcd.menu_shown():
            lcd.show_menu()
        else:
            lcd.hide_menu()
            lcd.osm.set_menu("0")

    def clean(self):
        if config["enable_re"]:
            self.encoder.clean()


class LCD():
    """
    handle lcd display
    """
    def __init__(self, lcd_i2c_addr, lcd_row, lcd_col, backlight_timeout, menu_timeout):
        if config["enable_lcd"]:
            self.lcd_i2c_addr = int(lcd_i2c_addr, 0)
            self.lcd_row = lcd_row
            self.lcd_col = lcd_col
            self.lcd_lib = i2clcd.I2C_LCD(1, self.lcd_i2c_addr, self.lcd_row,
                                          self.lcd_col)
            self.write_custom_char()

            self.osm = self.OnScreenMenu(self)
            self.menu_visible = False
            self.menu_timeout = menu_timeout
            self.menu_inactive = True

            self.backlight_timeout = backlight_timeout
            self.lcd_backlight_timeout_thread = {}
            self.lcd_backlight_timeout_thread["event"] = threading.Event()
            self.lcd_backlight_timeout_thread["thread"] = threading.Thread(
                target=self.lcd_backlight_timeout,
                args=(self.lcd_backlight_timeout_thread["event"],
                      self.backlight_timeout))
            self.lcd_backlight_timeout_thread["thread"].daemon = True
            self.lcd_backlight_timeout_thread["thread"].start()

            self.lcd_display_string_queue_thread = {}
            self.lcd_display_string_queue_thread["queue"] = queue.Queue()
            self.lcd_display_string_queue_thread["thread"] = threading.Thread(
                target=self.lcd_display_string_queue,
                args=[self.lcd_display_string_queue_thread["queue"]])
            self.lcd_display_string_queue_thread["thread"].daemon = True
            self.lcd_display_string_queue_thread["thread"].start()

            self.lcd_display_string_prepare_threads = {}
            for i in range(1, self.lcd_row + 1):
                self.lcd_display_string_prepare_threads[i] = {}
                self.lcd_display_string_prepare_threads[i]["queue"] = queue.Queue(maxsize=1)
                self.lcd_display_string_prepare_threads[i]["event"] = threading.Event()
                self.lcd_display_string_prepare_threads[i]["thread"] = threading.Thread(
                    target=self.lcd_display_string_prepare,
                    args=(self.lcd_display_string_prepare_threads[i]["event"],
                          self.lcd_display_string_prepare_threads[i]["queue"]))
                self.lcd_display_string_prepare_threads[i]["thread"].daemon = True
                self.lcd_display_string_prepare_threads[i]["thread"].start()

    # display a string on display queue based fifo to prevent smbus overload
    def lcd_display_string_queue(self, queue):
        while True:
            while not queue.empty():
                data = queue.get()
                string = data["string"][:self.lcd_col]
                line = data["line"]
                align = data["align"]
                start_pos = data["start_pos"]
                # print(data)  # print display outpu
                self.lcd_lib.lcd_display_string(string, line, align, start_pos)
            time.sleep(.1)

    # put the strings to display inside a queue
    def lcd_display_string_queue_put(self, string, line=1, align=1, start_pos=1):
        self.lcd_display_string_queue_thread["queue"].put(
            {"string": string,
             "line": line,
             "align": align,
             "start_pos": start_pos})

    # preperate string for display in specific line on the lcd
    # align options(0=append to start_pos, 1=left, 2=center, 3=right)
    def lcd_display_string(self, string, line=1, align=1, start_pos=1, prefix=None, suffix=None):
        if config["enable_lcd"]:
            # self.lcd_display_string_thread_string = {"string": string,
            #                                          "line": line,
            #                                          "align": align,
            #                                          "start_pos": start_pos,
            #                                          "prefix": prefix,
            #                                          "suffix": suffix}
            # self.lcd_display_string_thread_new.set()
            self.lcd_display_string_prepare_threads[line]["queue"].put(
                {"string": string,
                 "line": line,
                 "align": align,
                 "start_pos": start_pos,
                 "prefix": prefix,
                 "suffix": suffix})
            self.lcd_display_string_prepare_threads[line]["event"].set()
            # if line != 0:
            #    self.lcd_display_string_thread_string = {"string": string,
            #                                             "line": line,
            #                                             "align": align,
            #                                             "start_pos": start_pos,
            #                                             "prefix": prefix,
            #                                             "suffix": suffix}
            #    self.lcd_display_string_thread_new.set()
            # if prefix or suffix:
            #    max_size = self.lcd_col - (len(prefix) + len(suffix))
            #    string = "%s%s%s" % (prefix,string[:max_size].center(max_size),suffix)
            # else:
            #    self.lcd_display_queue_put(string, line, align, start_pos)

    # display a string in specific line on the lcd
    # threadbased to use while loop
    def lcd_display_string_prepare(self, event, queue):
        if config["enable_lcd"]:
            # delays in seconds
            start_delay = 1
            step_delay = 0.5
            end_delay = 1
            while True:
                event.wait()
                event.clear()
                data = queue.get()
                string = data["string"]
                line = data["line"]
                align = data["align"]
                start_pos = data["start_pos"]
                prefix = data["prefix"]
                suffix = data["suffix"]
                lcd_col = self.lcd_col
                if prefix or suffix:
                    lcd_col = self.lcd_col - (len(prefix) + len(suffix))
                # display scrolling text, if string bigger than lcd columns
                if len(string) > lcd_col:
                    # display first time before scroll
                    temp_string = string[:lcd_col]
                    if prefix or suffix:
                        temp_string = "%s%s%s" % (
                            prefix,
                            string[:lcd_col].center(lcd_col),
                            suffix)
                    # print(temp_string)
                    self.lcd_display_string_queue_put(
                        temp_string, line, align, start_pos)
                    event.wait(timeout=start_delay)

                    # display during scroll
                    for i in range(1, (len(string) - (lcd_col - 1))):
                        if event.is_set():
                            break
                        temp_string = string[i:(i + lcd_col)]
                        if prefix or suffix:
                            temp_string = "%s%s%s" % (
                                prefix,
                                string[i:(i + lcd_col)].center(lcd_col),
                                suffix)
                        self.lcd_display_string_queue_put(
                            temp_string, line, align, start_pos)
                        event.wait(timeout=step_delay)

                    # display after scroll, the first chars
                    event.wait(timeout=end_delay)
                    if not event.is_set():
                        temp_string = string[:lcd_col]
                        if prefix or suffix:
                            temp_string = "%s%s%s" % (
                                prefix,
                                string[:lcd_col].center(lcd_col),
                                suffix)
                        self.lcd_display_string_queue_put(
                            temp_string, line, align, start_pos)
                else:
                    # display if string length less than lcd columns
                    temp_string = string
                    if prefix or suffix:
                        temp_string = "%s%s%s" % (
                            prefix,
                            string[:lcd_col].center(lcd_col),
                            suffix)
                    self.lcd_display_string_queue_put(
                        temp_string, line, align, start_pos)

    # clear the whole display
    def lcd_clear(self):
        if config["enable_lcd"]:
            for i in range(1, self.lcd_row + 1):
                self.lcd_display_string(" " * self.lcd_col, i)
            # self.lcd_lib.clear()

    # clear the whole specified line
    def lcd_clear_line(self, line=None):
        if not line:
            return
        if config["enable_lcd"]:
            self.lcd_display_string(" " * self.lcd_col, line)

    # set the backlight of the lcd (("on", 1), ("off", 0))
    def lcd_backlight(self, state):
        if config["enable_lcd"]:
            self.lcd_lib.lcd_backlight(state)

    # handle the automatic display backlight timeout
    def lcd_backlight_timeout(self, event, timeout):
        backlight_on = True
        if config["enable_lcd"]:
            while True:
                if event.is_set():
                    if not backlight_on:
                        self.lcd_backlight(1)
                        backlight_on = True
                    event.clear()
                event.wait(timeout=timeout)
                if not event.is_set():
                    self.lcd_backlight(0)
                    backlight_on = False
                event.wait()

    # activate display backlight
    def lcd_backlight_active(self):
        if config["enable_lcd"]:
            self.lcd_backlight_timeout_thread["event"].set()

    # write custom chars in the internal memory of the lcd
    def write_custom_char(self):
        # play icon
        self.lcd_lib.custom_char(
            0, bytearray([0x08, 0x0c, 0x0e, 0x0f, 0x0e, 0x0c, 0x08, 0x00]))
        # stop icon
        self.lcd_lib.custom_char(
            1, bytearray([0x00, 0x1f, 0x1f, 0x1f, 0x1f, 0x1f, 0x00, 0x00]))
        # pause icon
        self.lcd_lib.custom_char(
            2, bytearray([0x1b, 0x1b, 0x1b, 0x1b, 0x1b, 0x1b, 0x1b, 0x00]))
        # shuffle icon
        self.lcd_lib.custom_char(
            3, bytearray([0x07, 0x03, 0x15, 0x08, 0x15, 0x03, 0x07, 0x00]))
        # wait icon
        self.lcd_lib.custom_char(
            4, bytearray([0x1f, 0x11, 0x0a, 0x04, 0x0e, 0x1f, 0x1f, 0x00]))
        # speaker icon
        self.lcd_lib.custom_char(
            5, bytearray([0x01, 0x03, 0x1f, 0x1f, 0x1f, 0x03, 0x01, 0x00]))
        # loop icon
        self.lcd_lib.custom_char(
            6, bytearray([0x0d, 0x13, 0x17, 0x00, 0x1d, 0x19, 0x16, 0x00]))
        # smiley icon
        self.lcd_lib.custom_char(
            7, bytearray([0x00, 0x00, 0x0a, 0x00, 0x11, 0x0e, 0x00, 0x00]))

    # clear lcd and set position back to 0, 0
    def clear(self):
        if config["enable_lcd"]:
            self.lcd_lib.clear()

    """
    onscreen menu
    """
    # show the onscreen menu
    def show_menu(self):
        if config["enable_lcd"]:
            self.update_menu()
            self.menu_visible = True
            menu_timeout_thread = threading.Thread(
                target=self.menu_inactive_timeout)
            menu_timeout_thread.daemon = True
            menu_timeout_thread.start()

    # hide the onscreen menu
    def hide_menu(self):
        if config["enable_lcd"]:
            try:
                self.lcd_display_string("%s" % mp.get_title(), 2, 1)
            except Exception:
                self.lcd_clear_line(2)
            self.osm.set_menu_index(0)
            self.menu_visible = False

    # load a temporary menu for a local path
    def show_local_files(self):
        self.osm.local_files_menu_name = self.osm.get_select()["name"]
        self.osm.create_local_files_menu()
        # self.update_menu()

    # display the new selected item on the lcd with defined prefix and suffix
    def update_menu(self):
        prefix = self.osm.get_select()["pref"]
        suffix = self.osm.get_select()["suff"]
        string = self.osm.get_select()["name"]
        self.lcd_display_string(string, 2, 2, prefix=prefix, suffix=suffix)

    # return True if the menu is visible, else False
    def menu_shown(self):
        if config["enable_lcd"]:
            return self.menu_visible
        return False

    # hide menu if timeout is reached
    def menu_inactive_timeout(self):
        while self.menu_visible:
            for i in range(self.menu_timeout):
                if not self.menu_inactive:
                    break
                time.sleep(1)
            else:
                self.hide_menu()
                self.osm.set_menu("0")
            self.menu_inactive = True

    # reset menu timeout
    def menu_set_active(self):
        if config["enable_lcd"]:
            self.menu_inactive = False

    """
    class that create and handle callbacks for the onscreen menu
    """
    class OnScreenMenu():
        def __init__(self, upper_class):
            self.upper_class = upper_class
            try:
                # load onscreen menu json file
                onscreen_menu = os.path.join(os.path.dirname(__file__),
                                             "etc/onscreen_menu.json")
                self.onscreen_menu_file = json.load(
                    open(onscreen_menu, encoding="utf-8-sig"),
                    object_pairs_hook=collections.OrderedDict)
                # load context menu json file
                context_menu = os.path.join(os.path.dirname(__file__),
                                            "etc/context_menu.json")
                self.context_menu_file = json.load(
                    open(context_menu, encoding="utf-8-sig"),
                    object_pairs_hook=collections.OrderedDict)
            except Exception as e:
                print("| json file, wrong codec, need utf-8: %s" % e, flush=True)
                return
            self.menus = {}
            self.select = ["0", 0]
            self.create_menu(self.onscreen_menu_file, "0")

        # create the dictionary for the menu
        def create_menu(self, dict, current, name="Main", parent=False):
            self.menus[current] = {"menu": [], "name": name, "parent": parent}
            for key in dict.keys():
                type = self.check_type(key, dict)
                if type == "submenu":
                    data = "0%s" % list(dict.keys()).index(key)
                    self.create_menu(dict[key]["content"], data, key, current)
                elif type == "callback":
                    data = dict[key]["content"]
                self.menus[current]["menu"].append({"name": key,
                                                    "type": type,
                                                    "data": data,
                                                    "pref": "<",
                                                    "suff": ">"})
            self.menus[current]["menu"].append({"name": "Zurück",
                                                "type": "return",
                                                "data": parent,
                                                "pref": "<<",
                                                "suff": ">>"})

        # create the temporary dictionary with local files
        def create_local_files_menu(self, dir=None):
            if not dir:
                dir = default["pibox_home_dir"]
            dict = sy.parse_dir(dir)
            current = "1"
            parent = "0"
            self.menus[current] = {"menu": [],
                                   "name": self.local_files_menu_name,
                                   "parent": parent}
            for key in dict["content"]:
                self.menus[current]["menu"].append({"name": key["name"],
                                                    "type": key["type"],
                                                    "data": key["url"],
                                                    "pref": "<",
                                                    "suff": ">"})
            if dir == default["pibox_home_dir"]:
                self.menus[current]["menu"].append({"name": "Zurück",
                                                    "type": "return",
                                                    "data": parent,
                                                    "pref": "<<",
                                                    "suff": ">>"})
                self.set_menu(current)
            else:
                self.set_menu(current, 1)
            self.upper_class.update_menu()

        # create the temporary context menu
        def create_context_menu(self, type, url, name):
            current = "11"
            parent = "1"
            self.menus[current] = {"menu": [], "name": name, "parent": parent}
            for key in self.context_menu_file.keys():
                if key == type:
                    for key, content in self.context_menu_file[key]["content"].items():
                        self.menus[current]["menu"].append({"name": key,
                                                            "type": "callback",
                                                            "data": content["content"],
                                                            "args": url,
                                                            "pref": "<|",
                                                            "suff": "|>"})
                    self.menus[current]["menu"].append({"name": "Zurück",
                                                        "type": "return",
                                                        "data": parent,
                                                        "pref": "<|",
                                                        "suff": "|>"})
            self.set_menu(current)
            self.upper_class.update_menu()

        # check the type of current item
        def check_type(self, key, dict):
            if not isinstance(dict[key]["content"], str):
                return "submenu"
            return "callback"

        # return the type of the selected item in the current menu
        def get_type(self):
            return self.menus[self.select[0]]["menu"][self.select[1]]["type"]

        # return the name key of the current menu
        def get_menu(self):
            return self.select[0]

        # return the name key of the parent menu
        def get_parent(self):
            return self.menus[self.select[0]]["parent"]

        # return the index of the menu name in the parent menu
        def get_parent_index(self):
            for index, item in enumerate(list(self.menus[self.get_parent()]["menu"])):
                if item["name"] == self.menus[self.select[0]]["name"]:
                    return index
            return 0

        # set the selection to the parent menu selected the current menu
        def go_parent(self):
            self.set_menu(self.get_parent(), self.get_parent_index())

        # return the selected item in a dict {"name","type","data"}
        def get_select(self):
            return self.menus[self.select[0]]["menu"][self.select[1]]

        # return the index(zero-based) of the selected item in the current menu
        def get_select_index(self):
            return self.select[1]

        # return the number(one-based) of the selected item in the current menu
        def get_select_number(self):
            return self.select[1] + 1

        # select the previous item in the current menu
        def prev_select(self):
            if self.select[1] <= 0:
                self.select[1] = len(self.menus[self.select[0]]["menu"]) - 1
            else:
                self.select[1] -= 1

        # select the next item in the current menu
        def next_select(self):
            if self.select[1] >= len(self.menus[self.select[0]]["menu"]) - 1:
                self.select[1] = 0
            else:
                self.select[1] += 1

        # set the selection to given menu, optional with specified index
        def set_menu(self, menu, index=0):
            self.select[0] = menu
            self.select[1] = index

        # set the selection to given index in current menu
        def set_menu_index(self, index):
            self.select[1] = index

        # return True if selected item is a submenu
        def check_if_menu(self):
            if self.menus[self.select[0]]["menu"][self.select[1]]["type"] == "submenu":
                return True

        # call the callback function
        def do_callback(self):
            callback = self.get_select()["data"]
            try:
                if isinstance(callback, str):
                    if callback.endswith("()"):
                        callback = callback[:-2]
                    if "args" in self.get_select():
                        eval("%s('%s')" % (callback, self.get_select()["args"]))
                    else:
                        eval("%s()" % callback)
                elif callable(callback):
                    callback()
            except Exception as e:
                print("| osm callback error: %s" % e, flush=True)

        # call the callback function
        def do_function(self, dict=None):
            self.do_callback()

    """
    predefined splash screens
    """
    # screen when the programm starts
    def start_screen(self):
        self.lcd_display_string(config["pibox_name"], 1, 2)
        self.lcd_display_string("Willkommen", 2, 2)
        time.sleep(2)

    # first screen after start
    def idle_screen(self):
        self.lcd_clear()
        self.lcd_display_string("%s%s%%" % (chr(5), mp.get_volume()), 1, 1)
        self.lcd_display_string("%s" % chr(1), 1, 0, 7)

    # screen if the script is going to reload
    def restart_script_screen(self):
        self.lcd_display_string("Script wird", 1, 2)
        self.lcd_display_string("neu gestartet", 2, 2)
        time.sleep(2)

    # screen if the pi reboot
    def restart_screen(self):
        self.lcd_display_string("System wird", 1, 2)
        self.lcd_display_string("neu gestartet", 2, 2)
        time.sleep(2)

    # screen if the pi going to shutdown
    def shutdown_screen(self):
        self.lcd_display_string("System wird", 1, 2)
        self.lcd_display_string("heruntergefahren", 2, 2)
        time.sleep(2)

    # screen when the programm ends
    def end_screen(self):
        self.lcd_display_string("Auf", 1, 2)
        self.lcd_display_string("Wiedersehen", 2, 2)
        time.sleep(2)

"""
MAIN PROGRAM
"""
if __name__ == "__main__":
    # import traceback
    signal.signal(signal.SIGTERM, signal_term_handler)
    try:
        print("| prepare submodules...", flush=True)
        lcd = LCD(config["lcd_i2c_addr"],
                  config["lcd_row"],
                  config["lcd_col"],
                  config["display_timeout"],
                  config["menu_timeout"])
        rotenc = RotaryEncoder(config["switch_clk"],
                               config["switch_dt"],
                               config["switch_sw"],
                               config["longpress_delay"])
        https = HTTPServer(config["webserver_port"])
        wss = WSServer(config["websocket_port"])
        sy = System()
        mp = MediaPlayer(config["default_volume"])
        if config["enable_lcd"]:
            lcd.start_screen()
            lcd.idle_screen()
        https.start()
        wss.start()
        print("| ready to use", flush=True)
        keep_running = True
        while keep_running:
            time.sleep(.1)
    except KeyboardInterrupt:
        print("| keyboard interrupt (ctrl+c)", flush=True)
    except Exception as e:
        print("| main error: %s" % e, flush=True)
        # traceback.print_exc()
    finally:
        cleanup()
        hard_exit()
