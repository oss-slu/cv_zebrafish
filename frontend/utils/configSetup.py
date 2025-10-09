import os
import json
from os import path

""" CONFIG SETUP """

def loadConfig(src='LastConfig.json'): # uses previous config by default
    if not path.exists(src):
        print("No config file found, loading base config")

        config = json.load(open('BaseConfig.json', 'r'))
        json.dump(config, open('LastConfig.json', 'w'), indent = 4)
        return config
    else:
        config = json.load(open(src, 'r'))
        return config