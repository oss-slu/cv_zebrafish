import os
import json
import pandas as pd

""" CONFIG SETUP """


def getConfig():
    guessCheck = input(
        "Would you like to reset LastConfig?\n (Press enter to use LastConfig, or 'y' to reset): ")

    if guessCheck.lower() in ("y", "yes"):  # If resetting last config
        config_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "configs"))
        base_config_path = os.path.join(config_dir, "BaseConfig.json")
        last_config_path = os.path.join(config_dir, "LastConfig.json")
        config = json.load(open(base_config_path, 'r'))
        json.dump(config, open(last_config_path, 'w'), indent=4)
        return config

    else:
        # Always use absolute paths for config files
        config_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "configs"))
        base_config_path = os.path.join(config_dir, "BaseConfig.json")
        last_config_path = os.path.join(config_dir, "LastConfig.json")
        if os.path.exists(last_config_path):  # Load last edited config
            config = json.load(open(last_config_path, 'r'))
        else:  # If no last edited config, load base config
            config = json.load(open(base_config_path, 'r'))
            # Write back to Config file
            json.dump(config, open(last_config_path, 'w'), indent=4)

        return json.load(open(last_config_path, 'r'))
