#!/usr/bin/env python3

'''
Pi-hole DNS traffic visualizer for the Raspberry Pi Sense HAT
By Sam Lindley, 2/21/2018
'''

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from sense_hat import SenseHat

SENSE = SenseHat()

if os.geteuid() == 0:
    LOGGER = logging.getLogger(__name__)
    LOGGER.setLevel(logging.INFO)

    HANDLER = logging.FileHandler('/var/log/pihole-visualizer.log')
    FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    HANDLER.setFormatter(FORMATTER)
    LOGGER.addHandler(HANDLER)


def joystick_up(color_mode):
    color_options = ('basic', 'traffic', 'ads', 'alternate')
    color_index = color_options.index(color_mode)

    if color_index == 3:
        color_index = 0
    else:
        color_index += 1

    color_mode = color_options[color_index]

    return color_mode

def joystick_right(interval):
    interval_options = (10, 30, 60, 120)
    interval_index = interval_options.index(interval)

    if interval_index == 3:
        interval_index = 0
    else:
        interval_index += 1

    interval = interval_options[interval_index]

    return interval

def joystick_down(lowlight):
    if lowlight:
        lowlight = False
    else:
        lowlight = True

    return lowlight

def joystick_left(orientation):
    orientation_options = (0, 90, 180, 270)
    orientation_index = orientation_options.index(orientation)

    if orientation_index == 3:
        orientation_index = 0
    else:
        orientation_index += 1

    orientation = orientation_options[orientation_index]

    return orientation

def joystick_middle(ripple):
    if ripple:
        ripple = False
    else:
        ripple = True

    return ripple

def joystick_middle_held():
    if os.geteuid() == 0:
        LOGGER.info('Program terminated by user.')
    print('Program terminated by user.')

    SENSE.clear()

    sys.exit()

#color code interval
def color_dict(level):
    return {
        0 : (0, 0, 255),
        1 : (0, 128, 255),
        2 : (0, 255, 255),
        3 : (255, 128, 0),
        4 : (0, 255, 0),
        5 : (128, 255, 0),
        6 : (255, 255, 0),
        7 : (255, 128, 0),
        8 : (255, 0, 0),
    }[level]

def api_request(address):
    if not hasattr(api_request, "initial_connection"):
        api_request.initial_connection = True
    max_attempts = 300 if api_request.initial_connection else 30
    attempts = 0

    #retrieve and decode json data from server
    while True:
        try:
            if attempts == 0 and api_request.initial_connection:
                if os.geteuid() == 0:
                    LOGGER.info('Initiating connection with server.')
                print('Initiating connection with server.')
            with urllib.request.urlopen("http://%s/admin/api.php?overTimeData10mins" % \
            address) as url:
                attempts += 1
                raw_data = json.loads(url.read().decode())
                break
        except json.decoder.JSONDecodeError:
            if attempts < max_attempts:
                time.sleep(1)
                continue
            else:
                if os.geteuid() == 0:
                    LOGGER.error('Exceeded max attempts to connect with server.')
                print('Error: Exceeded max attempts to connect with server.')
                sys.exit(1)
        except urllib.error.URLError:
            if os.geteuid() == 0:
                LOGGER.error('Invalid address for DNS server.')
            print("Error: Invalid address for DNS server. Try again.")
            sys.exit(1)

    if 'domains_over_time' not in raw_data or 'ads_over_time' not in raw_data:
        if os.geteuid() == 0:
            LOGGER.error('Invalid data returned from server. Ensure pihole-FTL service is running.')
        print('Error: Invalid data returned from server. Ensure pihole-FTL service is running.')
        sys.exit(1)

    if api_request.initial_connection:
        if os.geteuid() == 0:
            LOGGER.info('Successful connection with server.')
        print('Successful connection with server.')

    api_request.initial_connection = False

    return raw_data

def organize_data(raw_data, interval):
    clean_data = []
    domains = 0
    ads = 0

    #sort and reverse data so that latest time intervals appear first in list
    for counter, key in enumerate(sorted(raw_data['domains_over_time'].keys(), reverse=True)):
        if interval == 10:
            domains = raw_data['domains_over_time'][key]
            ads = raw_data['ads_over_time'][key]
            clean_data.append([domains, (ads / domains) * 100 if domains > 0 else 0])
        else:
            if interval == 30:
                if counter > 0 and counter % 3 == 0:
                    clean_data.append([domains, (ads / domains) * 100 if domains > 0 else 0])
                    domains = 0
                    ads = 0
            elif interval == 60:
                if counter > 0 and counter % 6 == 0:
                    clean_data.append([domains, (ads / domains) * 100 if domains > 0 else 0])
                    domains = 0
                    ads = 0
            elif interval == 120:
                if counter > 0 and counter % 12 == 0:
                    clean_data.append([domains, (ads / domains) * 100 if domains > 0 else 0])
                    domains = 0
                    ads = 0
            domains += raw_data['domains_over_time'][key]
            ads += raw_data['ads_over_time'][key]

    #extract a slice of the previous 24 hours
    if interval == 10:
        clean_data = clean_data[:144]
    elif interval == 30:
        clean_data = clean_data[:48]
    elif interval == 60:
        clean_data = clean_data[:24]
    elif interval == 120:
        clean_data = clean_data[:12]

    return clean_data

def generate_chart(clean_data, color, ripple, orientation, lowlight):
    info_chart = []
    domain_min = clean_data[0][0]
    domain_max = clean_data[0][0]
    ad_min = clean_data[0][1]
    ad_max = clean_data[0][1]

    #calculate minimum, maximum, and interval values to scale graph appropriately
    for i in clean_data:
        if i[0] > domain_max:
            domain_max = i[0]
        elif i[0] < domain_min:
            domain_min = i[0]

        if i[1] > ad_max:
            ad_max = i[1]
        elif i[1] < ad_min:
            ad_min = i[1]

    domain_interval = (domain_max - domain_min) / 8
    ad_interval = (ad_max - ad_min) / 8

    #append scaled values to new list
    for i in clean_data:
        info_chart.append([int((i[0] - domain_min) / domain_interval) if domain_interval > 0 \
                           else 0, int((i[1] - ad_min) / ad_interval) if ad_interval > 0 else 0])
    info_chart = list(reversed(info_chart[:8]))

    SENSE.clear()
    SENSE.set_rotation(orientation)
    SENSE.low_light = lowlight

    #set pixel values on rgb display
    for row in range(0, 8):
        if info_chart[row][0] > 0:
            for col in range(0, info_chart[row][0]):
                #if color not set, default to red for all values
                if color == 'traffic':
                    SENSE.set_pixel(row, 7 - col, color_dict(info_chart[row][0]))
                    if ripple:
                        time.sleep(0.025)
                elif color == 'ads':
                    SENSE.set_pixel(row, 7 - col, color_dict(info_chart[row][1]))
                    if ripple:
                        time.sleep(0.025)
                elif color == 'basic':
                    SENSE.set_pixel(row, 7 - col, (255, 0, 0))
                    if ripple:
                        time.sleep(0.025)

def main():
    parser = argparse.ArgumentParser(description="Generates a chart to display network traffic \
                                     on the Sense-HAT RGB display")

    parser.add_argument('-i', '--interval', action="store", choices=[10, 30, 60, 120], \
                        type=int, default='60', help="specify interval time in minutes")
    parser.add_argument('-c', '--color', action="store", choices=['basic', 'traffic', 'ads', \
                        'alternate'], default='basic', help="specify 'basic' to generate the \
                        default red chart, 'traffic' to represent the level of network traffic, \
                        'ads' to represent the percentage of ads blocked, or 'alternate' to \
                        switch between traffic level and ad block percentage")
    parser.add_argument('-r', '--ripple', action="store_true", help="this option generates a \
                        ripple effect when producing the chart")
    parser.add_argument('-a', '--address', action="store", default='127.0.0.1', help="specify \
                        address of DNS server, defaults to localhost")
    parser.add_argument('-o', '--orientation', action="store", choices=[0, 90, 180, 270], \
                        type=int, default='0', help="rotate graph to match orientation of RPi")
    parser.add_argument('-ll', '--lowlight', action="store_true", help="set LED matrix to \
                        light mode for use in dark environments")

    args = parser.parse_args()
    color_mode = args.color

    if color_mode == 'alternate':
        color = 'traffic'
    else:
        color = color_mode

    while True:
        joystick_event = False

        raw_data = api_request(args.address)
        clean_data = organize_data(raw_data, args.interval)

        if color_mode == 'alternate':
            for i in range(0, 15):
                color = 'ads' if color == 'traffic' else 'traffic'
                generate_chart(clean_data, color, args.ripple, args.orientation, args.lowlight)

                for i in range(0, 2):
                    events = SENSE.stick.get_events()
                    if events:
                        joystick_event = True
                        last_event = events[-1]
                        if last_event.action == 'held' and last_event.direction == 'middle':
                            joystick_middle_held()
                        else:
                            if last_event.direction == 'up':
                                color_mode = joystick_up(color_mode)
                                print("Color mode switched to '%s'." % color_mode.capitalize())
                                break
                            elif last_event.direction == 'right':
                                args.interval = joystick_right(args.interval)
                                print("Time interval switched to %d minutes." % args.interval)
                                break
                            elif last_event.direction == 'down':
                                args.lowlight = joystick_down(args.lowlight)
                                print("Low-light mode", "enabled." if args.lowlight else \
                                      "disabled.")
                                break
                            elif last_event.direction == 'left':
                                args.orientation = joystick_left(args.orientation)
                                print("Orientation switched to %d degrees." % args.orientation)
                                break
                            elif last_event.direction == 'middle':
                                args.ripple = joystick_middle(args.ripple)
                                print("Ripple mode", "enabled." if args.ripple else "disabled.")
                                break

                    time.sleep(1)

                if joystick_event:
                    break
        else:
            color = color_mode
            generate_chart(clean_data, color, args.ripple, args.orientation, args.lowlight)

            for i in range(0, 30):
                events = SENSE.stick.get_events()
                if events:
                    last_event = events[-1]
                    if last_event.action == 'held' and last_event.direction == 'middle':
                        joystick_middle_held()
                    else:
                        if last_event.direction == 'up':
                            color_mode = joystick_up(color_mode)
                            print("Color mode switched to '%s'." % color_mode.capitalize())
                            break
                        elif last_event.direction == 'right':
                            args.interval = joystick_right(args.interval)
                            print("Time interval switched to %d minutes." % args.interval)
                            break
                        elif last_event.direction == 'down':
                            args.lowlight = joystick_down(args.lowlight)
                            print("Low-light mode", "enabled." if args.lowlight else "disabled.")
                            break
                        elif last_event.direction == 'left':
                            args.orientation = joystick_left(args.orientation)
                            print("Orientation switched to %d degrees." % args.orientation)
                            break
                        elif last_event.direction == 'middle':
                            args.ripple = joystick_middle(args.ripple)
                            print("Ripple mode", "enabled." if args.ripple else "disabled.")
                            break

                time.sleep(1)

if __name__ == '__main__':
    main()
