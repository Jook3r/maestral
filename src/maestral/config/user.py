# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
This module provides user configuration file management and is mostly copied from the
config module of the Spyder IDE.
"""

import ast
import os
import os.path as osp
import re
import shutil
import time
import configparser as cp
from threading import RLock
import logging
from typing import Optional, Dict, Any


logger = logging.getLogger(__name__)

DefaultsType = Dict[str, Dict[str, Any]]

# =============================================================================
# Auxiliary classes
# =============================================================================


class NoDefault:
    pass


# =============================================================================
# Defaults class
# =============================================================================


class DefaultsConfig(cp.ConfigParser):
    """
    Class used to save defaults to a file and as base class for UserConfig.
    """

    _lock = RLock()

    def __init__(self, path: str) -> None:
        super().__init__(interpolation=None)

        dirname, basename = osp.split(path)
        filename, ext = osp.splitext(basename)

        self._path = path
        self._dirname = dirname
        self._filename = filename
        self._suffix = ext

    def _set(self, section: str, option: str, value: Any) -> None:
        """Private set method"""
        if not self.has_section(section):
            self.add_section(section)
        if not isinstance(value, str):
            value = repr(value)

        super().set(section, option, value)

    def save(self) -> None:
        """Save config into the associated file."""
        fpath = self.get_config_fpath()

        # See spyder-ide/spyder#1086 and spyder-ide/spyder#1242 for background
        # on why this method contains all the exception handling.

        with self._lock:
            try:
                # The "easy" way
                self.__write_file(fpath)
            except EnvironmentError:
                try:
                    # The "delete and sleep" way
                    if osp.isfile(fpath):
                        os.remove(fpath)

                    time.sleep(0.05)
                    self.__write_file(fpath)
                except Exception:
                    logger.warning(
                        "Failed to write user configuration to disk", exc_info=True
                    )

    def __write_file(self, fpath: str) -> None:

        os.makedirs(self._dirname, exist_ok=True)

        with open(fpath, "w", encoding="utf-8") as configfile:
            self.write(configfile)

    def get_config_fpath(self) -> str:
        """Return the ini file where this configuration is stored."""
        return self._path


# =============================================================================
# User config class
# =============================================================================


class UserConfig(DefaultsConfig):
    """
    UserConfig class, based on ConfigParser.

    Parameters
    ----------
    path:
        Configuration file will be saved to this path.
    defaults:
        Dictionary containing options *or* list of tuples (sec_name, options)
    load:
        If a previous configuration file is found, load will take the values
        from this existing file, instead of using default values.
    version:
        version of the configuration file in 'major.minor.micro' format.
    backup:
        A backup will be created on version changes and on initial setup.
    remove_obsolete:
        If `True`, values that were removed from the configuration on version
        change, are removed from the saved configuration file.

    Notes
    -----
    The 'get' and 'set' arguments number and type differ from the reimplemented
    methods. 'defaults' is an attribute and not a method.
    """

    DEFAULT_SECTION_NAME = "main"

    def __init__(
        self,
        path: str,
        defaults: Optional[DefaultsType] = None,
        load: bool = True,
        version: str = "0.0.0",
        backup: bool = False,
        remove_obsolete: bool = False,
    ) -> None:
        """UserConfig class, based on ConfigParser."""
        super().__init__(path=path)

        self._load = load
        self._backup = backup
        self._remove_obsolete = remove_obsolete

        self._version = self._check_version(version)
        self.default_config = self._set_defaults(defaults)

        # Set all values to defaults. They may be overwritten later
        # when loading form file.
        self.reset_to_defaults(save=False)

        self._defaults_folder = "defaults"
        self._backup_folder = "backups"
        self._backup_suffix = ".bak"
        self._defaults_name_prefix = "defaults"

        if backup:
            self._make_backup()

        if load:
            # If config file already exists, it overrides Default options
            self._load_from_ini(self.get_config_fpath())
            old_version = self.get_version(version)

            # Save new defaults
            self._save_new_defaults(self.default_config)

            # Updating defaults only if major/minor version is different
            major_ver = self._get_major_version(version)
            major_old_ver = self._get_major_version(old_version)

            minor_ver = self._get_minor_version(version)
            minor_old_ver = self._get_minor_version(old_version)

            if major_ver != major_old_ver or minor_ver != minor_old_ver:

                if backup:
                    self._make_backup(version=old_version)

                self.apply_configuration_patches(old_version)

                # Remove deprecated options if major version has changed
                if remove_obsolete and major_ver != major_old_ver:
                    self._remove_deprecated_options()

                # Set new version number
                self.set_version(version, save=False)

    # --- Helpers and checkers ---------------------------------------------------------

    @staticmethod
    def _get_minor_version(version: str) -> str:
        """Return the 'major.minor' components of the version."""
        return version[: version.rfind(".")]

    @staticmethod
    def _get_major_version(version: str) -> str:
        """Return the 'major' component of the version."""
        return version[: version.find(".")]

    @staticmethod
    def _check_version(version: str) -> str:
        """Check version is compliant with format."""
        regex_check = re.match(r"^(\d+).(\d+).(\d+)$", version)
        if regex_check is None:
            raise ValueError(
                "Version number {} is incorrect - must be in "
                "major.minor.micro format".format(version)
            )

        return version

    def _set_defaults(self, defaults: Optional[DefaultsType]) -> DefaultsType:
        """Check if defaults are valid and update defaults values."""

        if not defaults:
            defaults = {}

        if self.DEFAULT_SECTION_NAME not in defaults:
            defaults[self.DEFAULT_SECTION_NAME] = {}

        self.default_config = defaults
        self.default_config[self.DEFAULT_SECTION_NAME]["version"] = self._version

        return self.default_config

    def _check_section(self, section: Optional[str]) -> str:
        """Check section."""
        return section or self.DEFAULT_SECTION_NAME

    def _make_backup(
        self, version: Optional[str] = None, old_version: Optional[str] = None
    ) -> None:
        """
        Make a backup of the configuration file.

        If `old_version` is `None` a normal backup is made. If `old_version`
        is provided, then the backup was requested for minor version changes
        and appends the version number to the backup file.
        """
        fpath = self.get_config_fpath()
        fpath_backup = self.get_backup_fpath_from_version(version=version)
        path = os.path.dirname(fpath_backup)

        if not osp.isdir(path):
            os.makedirs(path)

        try:
            shutil.copyfile(fpath, fpath_backup)
        except IOError:
            pass

    def _load_from_ini(self, fpath: str) -> None:
        """Load config from the associated file found at `fpath`."""

        with self._lock:
            try:
                self.read(fpath, encoding="utf-8")
            except cp.MissingSectionHeaderError:
                logger.error("File contains no section headers.")

    def _load_old_defaults(self, old_version: str) -> cp.ConfigParser:
        """Read old defaults."""
        old_defaults = cp.ConfigParser()
        fpath = self.get_defaults_fpath_from_version(old_version)
        old_defaults.read(fpath)
        return old_defaults

    def _save_new_defaults(self, defaults: DefaultsType) -> None:
        """Save new defaults."""
        path = self.get_defaults_fpath_from_version(self._version)
        new_defaults = DefaultsConfig(path=path)
        if not osp.isfile(new_defaults.get_config_fpath()):
            new_defaults.read_dict(defaults)
            new_defaults.save()

    def _remove_deprecated_options(self) -> None:
        """
        Remove options which are present in the file but not in defaults.
        """
        for section in self.sections():
            for option, _ in self.items(section, raw=True):
                if self.get_default(section, option) is NoDefault:
                    try:
                        self.remove_option(section, option)
                        if len(self.items(section, raw=True)) == 0:
                            self.remove_section(section)
                    except cp.NoSectionError:
                        self.remove_section(section)

    # --- Compatibility API ------------------------------------------------------------

    def get_backup_fpath_from_version(self, version: Optional[str] = None) -> str:
        """
        Get backup location based on version.
        """
        fpath = self.get_config_fpath()
        path = osp.join(osp.dirname(fpath), self._backup_folder)
        new_fpath = osp.join(path, osp.basename(fpath))
        if version is None:
            backup_fpath = "{}{}".format(new_fpath, self._backup_suffix)
        else:
            backup_fpath = "{}-{}{}".format(new_fpath, version, self._backup_suffix)
        return backup_fpath

    def get_defaults_fpath_from_version(self, version: str) -> str:
        """
        Get defaults location based on version.

        To be reimplemented if versions changed defaults location.
        """

        defaults_path = osp.join(
            osp.dirname(self.get_config_fpath()), self._defaults_folder
        )
        name = "{}-{}-{}".format(self._defaults_name_prefix, self._filename, version)

        if not osp.isdir(defaults_path):
            os.makedirs(defaults_path)

        return osp.join(defaults_path, name + self._suffix)

    def apply_configuration_patches(self, old_version: str = None) -> None:
        """
        Apply any patch to configuration values on version changes.

        To be reimplemented if patches to configuration values are needed.
        """
        pass

    # --- Public API -------------------------------------------------------------------

    def get_version(self, version: str = "0.0.0") -> str:
        """Return configuration (not application!) version."""
        return self.get(self.DEFAULT_SECTION_NAME, "version", version)

    def set_version(self, version: str = "0.0.0", save: bool = True) -> None:
        """Set configuration (not application!) version."""
        version = self._check_version(version)
        self.set(self.DEFAULT_SECTION_NAME, "version", version, save=save)

    def reset_to_defaults(
        self, save: bool = True, section: Optional[str] = None
    ) -> None:
        """Reset config to Default values."""

        for sec, options in self.default_config.items():
            if section is None or section == sec:
                for option in options:
                    value = options[option]
                    self._set(sec, option, value)

        if save:
            self.save()

    def get_default(self, section: str, option: str) -> Any:
        """
        Get default value for a given `section` and `option`.

        This is useful for type checking in `get` method.
        """
        secdict = self.default_config.get(section, {})
        return secdict.get(option, NoDefault)

    def get(self, section: str, option: str, default: Any = NoDefault) -> Any:  # type: ignore
        """
        Get an option.

        Parameters
        ----------
        section:
            Section name. If `None` is provide use the default section name.
        option:
            Option name for `section`.
        default:
            Default value (if not specified, an exception will be raised if
            option doesn't exist).
        """
        section = self._check_section(section)

        if not self.has_section(section):
            if default is NoDefault:
                raise cp.NoSectionError(section)
            else:
                self.add_section(section)

        if not self.has_option(section, option):
            if default is NoDefault:
                raise cp.NoOptionError(option, section)
            else:
                self.set(section, option, default)
                return default

        raw_value: str = super(UserConfig, self).get(section, option, raw=True)
        default_value = self.get_default(section, option)
        value: Any

        if isinstance(default_value, str):
            value = raw_value
        else:
            try:
                value = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError):
                value = raw_value

        if default_value is not NoDefault and type(default_value) is not type(value):
            logger.error(
                f"Inconsistent config type for [{section}][{option}]. "
                f"Expected {default_value.__class__.__name__} but "
                f"got {value.__class__.__name__}."
            )

        return value

    def set_default(self, section: str, option: str, default_value: Any) -> None:
        """
        Set Default value for a given `section`, `option`.

        If the section or option does not exist, it will be created.
        """

        if section not in self.default_config:
            self.default_config[section] = {}

        self.default_config[section][option] = default_value

    def set(self, section: str, option: str, value: Any, save: bool = True) -> None:  # type: ignore
        """
        Set an `option` on a given `section`.

        If section is None, the `option` is added to the default section.
        """
        section = self._check_section(section)
        default_value = self.get_default(section, option)

        if default_value is NoDefault:
            default_value = value
            self.set_default(section, option, default_value)

        if isinstance(default_value, float) and isinstance(value, int):
            value = float(value)

        if type(default_value) is not type(value):
            raise ValueError(
                f"Inconsistent config type for [{section}][{option}]. "
                f"Expected {default_value.__class__.__name__} but "
                f"got {value.__class__.__name__}."
            )

        self._set(section, option, value)
        if save:
            self.save()

    def remove_section(self, section: str) -> bool:
        """Remove `section` and all options within it."""
        res = super().remove_section(section)
        self.save()
        return res

    def remove_option(self, section: str, option: str) -> bool:
        """Remove `option` from `section`."""
        res = super().remove_option(section, option)
        self.save()
        return res

    def cleanup(self) -> None:
        """Remove files associated with config and reset to defaults."""

        self.reset_to_defaults(save=False)

        fpath = self.get_config_fpath()

        backup_path = osp.join(self._dirname, self._backup_folder)
        defaults_path = osp.join(self._dirname, self._defaults_folder)

        # remove config file
        try:
            os.remove(fpath)
        except FileNotFoundError:
            pass

        # remove saved backups
        for file in os.scandir(backup_path):
            if file.name.startswith(self._filename):
                try:
                    os.remove(file.path)
                except FileNotFoundError:
                    pass

        # remove saved defaults
        for file in os.scandir(defaults_path):
            if file.name.startswith(f"{self._defaults_name_prefix}-{self._filename}"):
                try:
                    os.remove(file.path)
                except FileNotFoundError:
                    pass
