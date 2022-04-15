#!/usr/bin/env python
# coding=utf-8

import base64
import logging
import os
import requests
import signal
import sys
import telebot
from telebot import types

TOKEN='5310592421:AAH9f5sbngLbHuIzsd6qWTvz1YoOWqLQ9YY'
VPN_LINK = 'http://www.vpngate.net/api/iphone/'
LOG_FORMAT = '%(asctime)s(%(threadName)s) %(levelname)s - %(message)s'
CHUNK_SIZE = 1024 * 1024 # 1Mb
CANDIDATES = 10

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT))
logging.getLogger().addHandler(handler)

bot = telebot.TeleBot(TOKEN)

def get_flag(code):
    flag_offset = 0x1F1E6
    ascii_offset = 0x41
    return chr(ord(code[0]) - ascii_offset + flag_offset) + chr(ord(code[1]) - ascii_offset + flag_offset)

def get_csv(link):
    result = requests.get(VPN_LINK, stream=True, allow_redirects=False)
    if not result.ok:
        logging.error(f"Cannot acceess {link}")
        return None
    return result

def speed_str(speed):
    if speed < 1024:
        return str(speed) + " b/s"
    elif speed < 1024 * 1024:
        return str(int(speed / 1024 * 100) / 100) + " Kb/s"
    else:
        return str(int(speed / (1024 * 1024) * 100) / 100) + " Mb/s"

def get_config(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    find = types.KeyboardButton("Найти")
    keyboard.add(find)

    csv = get_csv(VPN_LINK)
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

    best = max(candidates, key=lambda row: row[layout["Score"]])
    if not best:
        logging.error(f"Cannot obtain vest VPN server")
        bot.send_message(message.chat.id, text="Не получается определить лучший сервер", reply_markup=keyboard)
        return

    name    = best[layout['HostName']]
    ip      = best[layout['IP']]
    #score   = best[layout['Score']]
    ping    = best[layout['Ping']]
    speed   = best[layout['Speed']]
    country = best[layout['CountryLong']]
    country_code = best[layout['CountryShort']]
    users   = best[layout['TotalUsers']]

    filename = name + ".ovpn"
    with open(filename, 'wb') as ovpn_cfg:
        ovpn = base64.b64decode(best[layout['OpenVPN_ConfigData_Base64']])
        ovpn_cfg.write(ovpn)

    with open(filename, 'rb') as ovpn_cfg:
        bot.send_document(message.chat.id, document=ovpn_cfg, reply_markup=keyboard, caption=
            "Server name: {0} ({1} {2})\n"
            "IP: {3}\n"
            "Speed: {4}\n"
            "Ping: {5} ms\n"
            "TotalUsers: {6}\n".format(name, get_flag(country_code), country, ip, speed_str(float(speed)), ping, users))

    if os.path.exists(filename):
        os.remove(filename)

@bot.message_handler(commands=['start', 'get'])
def start(message):
    get_config(message)

@bot.message_handler(func=lambda message: True)
def get(message):
    get_config(message)


def signal_handler(sig, frame):
    bot.stop_bot()
    print('Interrupted Ctrl+C')

signal.signal(signal.SIGINT, signal_handler)

bot.infinity_polling()
sys.exit(0)
