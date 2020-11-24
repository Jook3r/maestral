# -*- coding: utf-8 -*-
"""This module contains migration code to run after an update."""

# system imports
import os
from typing import TypeVar

# local imports
from ..config import MaestralConfig, MaestralState
from ..utils.appdirs import get_data_path, get_log_path
from ..utils.path import delete


_C = TypeVar("_C", bound=str)


def remove_configuration(config_name: str) -> None:
    """
    Removes all config and state files associated with the given configuration.

    :param config_name: The configuration to remove.
    """

    index_file = get_data_path("maestral", f"{config_name}.index")  # obsolete
    db_file = get_data_path("maestral", f"{config_name}.db")
    log_dir = get_log_path("maestral")

    MaestralConfig(config_name).cleanup()
    MaestralState(config_name).cleanup()
    delete(index_file)
    delete(db_file)

    log_files = []

    for file_name in os.listdir(log_dir):
        if file_name.startswith(config_name):
            log_files.append(os.path.join(log_dir, file_name))

    for file in log_files:
        delete(file)


def validate_config_name(string: _C) -> _C:
    """
    Validates that the config name does not contain any whitespace.

    :param string: String to validate.
    :returns: The input value.
    :raises ValueError: if the config name contains whitespace.
    """
    if len(string.split()) > 1:
        raise ValueError("Config name may not contain any whitespace")

    return string
