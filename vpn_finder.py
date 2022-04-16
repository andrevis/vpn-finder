#!/usr/bin/env python
# coding=utf-8

import base64
from datetime import datetime
import logging
import os
from ping3 import ping
import threading
from time import sleep
import requests
import signal
import speedtest
import sys
import telebot
from telebot import types
import queue

TOKEN='5310592421:AAH9f5sbngLbHuIzsd6qWTvz1YoOWqLQ9YY'
VPN_LINK = 'http://www.vpngate.net/api/iphone/'
LOG_FORMAT = '%(asctime)s(%(threadName)s) %(levelname)s - %(message)s'
CHUNK_SIZE = 1024 * 1024 # 1Mb
CANDIDATES = 10
MAX_HISTORY = 10

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
logging.getLogger().addHandler(handler)


def signal_handler(sig, frame):
    raise RuntimeError('Interrupted Ctrl+C')

signal.signal(signal.SIGINT, signal_handler)


class Utils:
    @staticmethod
    def get_flag(code):
        flag_offset = 0x1F1E6
        ascii_offset = 0x41
        return chr(ord(code[0]) - ascii_offset + flag_offset) + chr(ord(code[1]) - ascii_offset + flag_offset)

    @staticmethod
    def get_csv(link):
        result = requests.get(VPN_LINK, stream=True, allow_redirects=False)
        if not result.ok:
            logging.error(f"Cannot acceess {link}")
            return None
        return result

    @staticmethod
    def get_speed_str(speed):
        if speed < 1024:
            return str(speed) + " b/s"
        elif speed < 1024 * 1024:
            return str(int(speed / 1024 * 100) / 100) + " Kb/s"
        else:
            return str(int(speed / (1024 * 1024) * 100) / 100) + " Mb/s"

    @staticmethod
    def get_ping(host):
        resp = ping(host)
        return int(resp * 1000 * 100) / 100

    @staticmethod
    def get_speed(host):
        st = speedtest.Speedtest()
        return Utils.get_speed_str(st.download())


class BestScoreSelector:
    @staticmethod
    def get(layout, candidates):
        return max(candidates, key=lambda row: row[layout["Score"]])


class LowPingSelector:
    @staticmethod
    def get(layout, candidates):
        min_ping = sys.maxsize - 1
        min_index = 0

        for index, entry in enumerate(candidates):
            ip      = entry[layout['IP']]
            ping    = Utils.get_ping(ip)
            if ping < min_ping:
                min_ping = ping
                min_index = index
        return candidates[min_index]


class Bot(threading.Thread):
    __bot__ = telebot.TeleBot(TOKEN)
    __history__ = queue.Queue()

    def __init__(self):
        threading.Thread.__init__(self, name="Finder")

        @self.__bot__.message_handler(commands=['start', 'get'])
        def __start__(message):
            self.__get_config__(message)

        @self.__bot__.message_handler(func=lambda message: True)
        def __get__(message):
            self.__get_config__(message)

    def run(self):
        self.__bot__.infinity_polling()

    def stop(self):
        self.__bot__.stop_bot()

    def push(self, msg):
        self.__history__.put(msg)
        while (self.__history__.qsize() >= MAX_HISTORY):
            head = self.__history__.get()
            self.__bot__.delete_message(head.chat.id, head.message_id)

    def __get_config__(self, message):
        self.push(message)

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        find = types.KeyboardButton("Найти")
        keyboard.add(find)

        csv = Utils.get_csv(VPN_LINK)
        if not csv:
            return

        filename = None
        layout = None
        candidates = []

        for line in csv.iter_lines(chunk_size=CHUNK_SIZE, decode_unicode=True):
            if not filename:
                filename = line.strip('*')
                continue
            if not layout:
                layout = { value: index for index, value in enumerate(line.strip('#').split(',')) }
                continue

            candidates.append(line.split(','))

            if len(candidates) >= CANDIDATES:
                break

        logging.debug(f'{layout}')

        best = LowPingSelector.get(layout, candidates)
        if not best:
            logging.error(f"Cannot obtain vest VPN server")
            msg = self.__bot__.send_message(message.chat.id, text="Не получается определить лучший сервер", reply_markup=keyboard)
            self.push(msg)
            return

        name    = best[layout['HostName']]
        ip      = best[layout['IP']]
        country = best[layout['CountryLong']]
        users   = best[layout['TotalUsers']]
        ping    = Utils.get_ping(ip)
        speed   = Utils.get_speed(ip)
        flag    = Utils.get_flag(best[layout['CountryShort']])

        filename = name + ".ovpn"
        with open(filename, 'wb') as ovpn_cfg:
            ovpn = base64.b64decode(best[layout['OpenVPN_ConfigData_Base64']])
            ovpn_cfg.write(ovpn)

        with open(filename, 'rb') as ovpn_cfg:
            msg = self.__bot__.send_document(message.chat.id, document=ovpn_cfg, reply_markup=keyboard, caption=
                "Server name: {0} ({1} {2})\n"
                "IP: {3}\n"
                "Speed: {4}\n"
                "Ping: {5} ms\n"
                "TotalUsers: {6}\n".format(name, flag, country, ip, speed, ping, users))
            self.push(msg)

        if os.path.exists(filename):
            os.remove(filename)


class TimeThread(threading.Thread):
    __need_running__ = True

    __start__ = datetime.now()
    __now__ = None
    __delta__ = None

    def __init__(self):
        threading.Thread.__init__(self, name="TimeThread")

    def now(self):
        return self.__now__

    def run(self):
        while self.__need_running__:
            self.__now__ = datetime.now()
            self.__delta__ = self.__now__ - self.__start__
            sleep(0.5)

    def stop(self):
        self.__need_running__ = False



timer = TimeThread()
timer.start()

bot = Bot()
bot.start()

while (True):
    sleep(1)

