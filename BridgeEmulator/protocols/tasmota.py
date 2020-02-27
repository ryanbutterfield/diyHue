import json
import logging
import random
import requests

import socket
import sys

from time import sleep
from subprocess import check_output
from functions import light_types, nextFreeId
from functions.colors import convert_rgb_xy, convert_xy
from functions.network import getIpAddress


def sendRequest(url, timeout=3):

    head = {"Content-type": "application/json"}
    response = requests.get(url, timeout=timeout, headers=head)
    return response.text


def discover(bridge_config, new_lights):
    logging.debug("tasmota: <discover> invoked!")

    device_ips = check_output("nmap  " + getIpAddress() + "/24 -p80 --open -n | grep report | cut -d ' ' -f5", shell=True).decode('utf-8').rstrip("\n").split("\n")
    
    for ip in device_ips:
        if not ip:
            continue
        try:
            logging.debug ( "tasmota: probing ip " + ip)
            response = requests.get ("http://" + ip + "/cm?cmnd=Status%200", timeout=3)
            if response.status_code == 200:
                device_data = json.loads(response.text)
                #logging.debug(pretty_json(device_data))

                if "StatusSTS" in device_data and "Channel" in device_data["StatusSTS"]:
                    logging.debug("tasmota: " + ip + " is a Tasmota device ")
                    logging.debug ("tasmota: Hostname: " + device_data["StatusNET"]["Hostname"] )
                    logging.debug ("tasmota: Mac:      " + device_data["StatusNET"]["Mac"] )

                    modelid = "Tasmota-%sChannel" % len(device_data["StatusSTS"]["Channel"])
                    properties = {"rgb": "xt" in light_types[modelid]["state"], "ct": "ct" in light_types[modelid]["state"], "ip": ip, "name": device_data["StatusNET"]["Hostname"], "id": device_data["StatusNET"]["Mac"], "mac": device_data["StatusNET"]["Mac"]}
                    device_exist = False
                    for light in bridge_config["lights_address"].keys():
                        if bridge_config["lights_address"][light]["protocol"] == "tasmota" and  bridge_config["lights_address"][light]["id"] == properties["id"]:
                            device_exist = True
                            bridge_config["lights_address"][light]["ip"] = properties["ip"]
                            logging.debug("tasmota: light id " + properties["id"] + " already exist, updating ip...")
                            break
                    if (not device_exist):
                        light_name = "Tasmota id " + properties["id"][-8:] if properties["name"] == "" else properties["name"]
                        logging.debug("tasmota: Add Tasmota: " + properties["id"])
                        new_light_id = nextFreeId(bridge_config, "lights")
                        bridge_config["lights"][new_light_id] = {"state": light_types[modelid]["state"], "type": light_types[modelid]["type"], "name": light_name, "uniqueid": "4a:e0:ad:7f:cf:" + str(random.randrange(0, 99)) + "-1", "modelid": modelid, "manufacturername": "Tasmota", "swversion": light_types[modelid]["swversion"], "config": light_types[modelid]["config"]}
                        new_lights.update({new_light_id: {"name": light_name}})
                        bridge_config["lights_address"][new_light_id] = {"ip": properties["ip"], "id": properties["id"], "protocol": "tasmota"}

        except Exception as e:
            logging.debug("tasmota: ip " + ip + " is unknow device, " + str(e))



def set_light(address, light, data):
    logging.debug("tasmota: <set_light> invoked! IP=" + address["ip"])

    for key, value in data.items():
        #logging.debug("tasmota: key " + key)

        if key == "on":
            if value:
                sendRequest ("http://"+address["ip"]+"/cm?cmnd=Power%20on")
            else:
                sendRequest ("http://"+address["ip"]+"/cm?cmnd=Power%20off")
        elif key == "bri":
            brightness = int(100.0 * (value / 254.0))
            sendRequest ("http://"+address["ip"]+"/cm?cmnd=Dimmer%20" + str(brightness))
        elif key == "ct":
            sendRequest ("http://"+address["ip"]+"/cm?cmnd=CT%20" + str(value))
        elif key == "xy":
            color = convert_xy(value[0], value[1], light["state"]["bri"])
            sendRequest ("http://"+address["ip"]+"/cm?cmnd=Color%20" + str(color[0]) + "," + str(color[1]) + "," + str(color[2]))

        elif key == "alert":
            if value == "select":
                sendRequest ("http://" + address["ip"] + "/cm?cmnd=dimmer%20100")


def get_light_state(address, light):
    logging.debug("tasmota: <get_light_state> invoked!")
    data = sendRequest ("http://" + address["ip"] + "/cm?cmnd=Status%2011")
    light_data = json.loads(data)["StatusSTS"]
    state = {}

    if 'POWER'in light_data:
        state['on'] = True if light_data["POWER"] == "ON" else False
    elif 'POWER1'in light_data:
        state['on'] = True if light_data["POWER1"] == "ON" else False
    
    channels = light_data['Channel']
    rgb_on = len(channels) >= 3 and (len(channels) != 5 or (channels[3] == 0 and channels[4] == 0))
    ct_on = len(channels) == 2 or (len(channels) == 5 and not rgb_on)   
    
    if rgb_on:
        rgb = light_data["Color"].split(",")
        logging.debug("tasmota: <get_light_state>: red " + str(rgb[0]) + " green " + str(rgb[1]) + " blue " + str(rgb[2]) )
        state["xy"] = convert_rgb_xy(int(rgb[0],16), int(rgb[1],16), int(rgb[2],16))
        state["colormode"] = "xy"
        
    elif ct_on:
        ct = light_data["CT"]
        logging.debug("tasmota: <get_light_state>: ct " + str(ct))
        state["ct"] = ct
        state["colormode"] = "ct"
    
    state["bri"] = int((int(light_data["Dimmer"]) / 100.0) * 254.0)
        
    return state
