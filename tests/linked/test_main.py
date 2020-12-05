# -*- coding: utf-8 -*-

import os
import os.path as osp

import pytest

from maestral.errors import NotFoundError
from maestral.main import FileStatus, IDLE
from maestral.main import logger as maestral_logger
from maestral.utils.path import delete

from .conftest import wait_for_idle


if not os.environ.get("DROPBOX_TOKEN"):
    pytest.skip("Requires auth token", allow_module_level=True)


# API unit tests


def test_status_properties(m):

    assert not m.pending_link
    assert not m.pending_dropbox_folder

    assert m.status == IDLE
    assert m.running
    assert m.connected
    assert m.syncing
    assert not m.paused
    assert not m.sync_errors
    assert not m.fatal_errors

    maestral_logger.info("test message")
    assert m.status == "test message"


def test_file_status(m):

    # test synced folder
    file_status = m.get_file_status(m.test_folder_local)
    assert file_status == FileStatus.Synced.value

    # test unwatched outside of dropbox
    file_status = m.get_file_status("/url/local")
    assert file_status == FileStatus.Unwatched.value

    # test unwatched non-existent
    file_status = m.get_file_status("/this is not a folder")
    assert file_status == FileStatus.Unwatched.value, file_status

    # test unwatched when paused
    m.pause_sync()
    wait_for_idle(m)

    file_status = m.get_file_status(m.test_folder_local)
    assert file_status == FileStatus.Unwatched.value

    m.resume_sync()
    wait_for_idle(m)

    # test error status
    invalid_local_folder = m.test_folder_local + "/test_folder\\"
    os.mkdir(invalid_local_folder)
    wait_for_idle(m)

    file_status = m.get_file_status(invalid_local_folder)
    assert file_status == FileStatus.Error.value


def test_move_dropbox_folder(m):
    new_dir_short = "~/New Dropbox"
    new_dir = osp.realpath(osp.expanduser(new_dir_short))

    m.move_dropbox_directory(new_dir_short)
    assert osp.isdir(new_dir)
    assert m.dropbox_path == new_dir

    wait_for_idle(m)

    # assert that sync was resumed after moving folder
    assert m.syncing


def test_move_dropbox_folder_to_itself(m):

    m.move_dropbox_directory(m.dropbox_path)

    # assert that sync is still running
    assert m.syncing


def test_move_dropbox_folder_to_existing(m):

    new_dir_short = "~/New Dropbox"
    new_dir = osp.realpath(osp.expanduser(new_dir_short))
    os.mkdir(new_dir)

    try:

        with pytest.raises(FileExistsError):
            m.move_dropbox_directory(new_dir)

        # assert that sync is still running
        assert m.syncing

    finally:
        # cleanup
        delete(new_dir)


# API integration tests


def test_selective_sync_api(m):
    """
    Test :meth:`Maestral.exclude_item`, :meth:`MaestralMaestral.include_item`,
    :meth:`Maestral.excluded_status` and :meth:`Maestral.excluded_items`.
    """

    dbx_dirs = [
        "/sync_tests/selective_sync_test_folder",
        "/sync_tests/independent_folder",
        "/sync_tests/selective_sync_test_folder/subfolder_0",
        "/sync_tests/selective_sync_test_folder/subfolder_1",
    ]

    local_dirs = [m.to_local_path(dbx_path) for dbx_path in dbx_dirs]

    # create folder structure
    for path in local_dirs:
        os.mkdir(path)

    wait_for_idle(m)

    # exclude "/sync_tests/selective_sync_test_folder" from sync
    m.exclude_item("/sync_tests/selective_sync_test_folder")
    wait_for_idle(m)

    # check that local items have been deleted
    assert not osp.exists(m.to_local_path("/sync_tests/selective_sync_test_folder"))

    # check that `Maestral.excluded_items` only contains top-level folder
    assert "/sync_tests/selective_sync_test_folder" in m.excluded_items
    assert "/sync_tests/selective_sync_test_folder/subfolder_0" not in m.excluded_items
    assert "/sync_tests/selective_sync_test_folder/subfolder_1" not in m.excluded_items

    # check that `Maestral.excluded_status` returns the correct values
    assert m.excluded_status("/sync_tests") == "partially excluded"
    assert m.excluded_status("/sync_tests/independent_folder") == "included"

    for dbx_path in dbx_dirs:
        if dbx_path != "/sync_tests/independent_folder":
            assert m.excluded_status(dbx_path) == "excluded"

    # include test_path_dbx in sync, check that it worked
    m.include_item("/sync_tests/selective_sync_test_folder")
    wait_for_idle(m)

    assert osp.exists(m.to_local_path("/sync_tests/selective_sync_test_folder"))
    assert "/sync_tests/selective_sync_test_folder" not in m.excluded_items

    for dbx_path in dbx_dirs:
        assert m.excluded_status(dbx_path) == "included"

    # test excluding a non-existent folder
    with pytest.raises(NotFoundError):
        m.exclude_item("/bogus_folder")

    # check for fatal errors
    assert not m.fatal_errors


def test_selective_sync_api_nested(m):
    """Tests special cases of nested selected sync changes."""

    dbx_dirs = [
        "/sync_tests/selective_sync_test_folder",
        "/sync_tests/independent_folder",
        "/sync_tests/selective_sync_test_folder/subfolder_0",
        "/sync_tests/selective_sync_test_folder/subfolder_1",
    ]

    local_dirs = [m.to_local_path(dbx_path) for dbx_path in dbx_dirs]

    # create folder structure
    for path in local_dirs:
        os.mkdir(path)

    wait_for_idle(m)

    # exclude "/sync_tests/selective_sync_test_folder" from sync
    m.exclude_item("/sync_tests/selective_sync_test_folder")
    wait_for_idle(m)

    # test including a folder inside "/sync_tests/selective_sync_test_folder",
    # "/sync_tests/selective_sync_test_folder" should become included itself but it
    # other children will still be excluded
    m.include_item("/sync_tests/selective_sync_test_folder/subfolder_0")

    assert "/sync_tests/selective_sync_test_folder" not in m.excluded_items
    assert "/sync_tests/selective_sync_test_folder/subfolder_1" in m.excluded_items

    # check for fatal errors
    assert not m.fatal_errors
