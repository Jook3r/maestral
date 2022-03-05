import sys
import os
import os.path as osp
import shutil
import requests
import subprocess

import pytest

from maestral.exceptions import (
    NotFoundError,
    UnsupportedFileTypeForDiff,
    SharedLinkError,
    SyncError,
)
from maestral.constants import FileStatus, IDLE
from maestral.utils.path import delete
from maestral.utils.integration import get_inotify_limits

from .conftest import wait_for_idle, resources


if not ("DROPBOX_ACCESS_TOKEN" in os.environ or "DROPBOX_REFRESH_TOKEN" in os.environ):
    pytest.skip("Requires auth token", allow_module_level=True)


# API unit tests


def test_status_properties(m):

    assert not m.pending_link
    assert not m.pending_dropbox_folder

    assert m.status == IDLE
    assert m.running
    assert m.connected
    assert not m.paused
    assert not m.sync_errors
    assert not m.fatal_errors

    m._root_logger.info("test message")
    assert m.status == "test message"


def test_file_status(m):

    # test synced folder
    file_status = m.get_file_status(m.dropbox_path)
    assert file_status == FileStatus.Synced.value

    # test unwatched outside of dropbox
    file_status = m.get_file_status("/url/local")
    assert file_status == FileStatus.Unwatched.value

    # test unwatched non-existent
    file_status = m.get_file_status("/this is not a folder")
    assert file_status == FileStatus.Unwatched.value

    # test unwatched when paused
    m.stop_sync()
    wait_for_idle(m)

    file_status = m.get_file_status(m.dropbox_path)
    assert file_status == FileStatus.Unwatched.value

    m.start_sync()
    wait_for_idle(m)

    # test error status
    invalid_local_folder = m.dropbox_path + "/test_folder\\"
    os.mkdir(invalid_local_folder)
    wait_for_idle(m)

    file_status = m.get_file_status(invalid_local_folder)
    file_status_parent = m.get_file_status(m.dropbox_path)

    assert file_status == FileStatus.Error.value
    assert file_status_parent == FileStatus.Error.value


def test_move_dropbox_folder(m):
    new_dir_short = "~/New Dropbox"
    new_dir = osp.realpath(osp.expanduser(new_dir_short))

    m.move_dropbox_directory(new_dir_short)
    assert osp.isdir(new_dir)
    assert m.dropbox_path == new_dir

    wait_for_idle(m)

    # assert that sync was resumed after moving folder
    assert m.running


def test_move_dropbox_folder_to_itself(m):

    m.move_dropbox_directory(m.dropbox_path)

    # assert that sync is still running
    assert m.running


def test_move_dropbox_folder_to_existing(m):

    new_dir_short = "~/New Dropbox"
    new_dir = osp.realpath(osp.expanduser(new_dir_short))
    os.mkdir(new_dir)

    try:

        with pytest.raises(FileExistsError):
            m.move_dropbox_directory(new_dir)

        # assert that sync is still running
        assert m.running

    finally:
        # cleanup
        delete(new_dir)


# API integration tests


def test_selective_sync_api(m):
    """
    Tests :meth:`Maestral.exclude_item`, :meth:`MaestralMaestral.include_item`,
    :meth:`Maestral.excluded_status` and :meth:`Maestral.excluded_items`.
    """

    dbx_dirs = [
        "/selective_sync_test_folder",
        "/independent_folder",
        "/selective_sync_test_folder/subfolder_0",
        "/selective_sync_test_folder/subfolder_1",
    ]

    local_dirs = [m.to_local_path(dbx_path) for dbx_path in dbx_dirs]

    # create folder structure
    for path in local_dirs:
        os.mkdir(path)

    wait_for_idle(m)

    # exclude "/selective_sync_test_folder" from sync
    m.exclude_item("/selective_sync_test_folder")
    wait_for_idle(m)

    # check that local items have been deleted
    assert not osp.exists(m.to_local_path("/selective_sync_test_folder"))

    # check that `Maestral.excluded_items` only contains top-level folder
    assert "/selective_sync_test_folder" in m.excluded_items
    assert "/selective_sync_test_folder/subfolder_0" not in m.excluded_items
    assert "/selective_sync_test_folder/subfolder_1" not in m.excluded_items

    # check that `Maestral.excluded_status` returns the correct values
    assert m.excluded_status("") == "partially excluded"
    assert m.excluded_status("/independent_folder") == "included"

    for dbx_path in dbx_dirs:
        if dbx_path != "/independent_folder":
            assert m.excluded_status(dbx_path) == "excluded"

    # include folder in sync, check that it worked
    m.include_item("/selective_sync_test_folder")
    wait_for_idle(m)

    assert osp.exists(m.to_local_path("/selective_sync_test_folder"))
    assert "/selective_sync_test_folder" not in m.excluded_items

    for dbx_path in dbx_dirs:
        assert m.excluded_status(dbx_path) == "included"

    # test excluding a non-existent folder
    with pytest.raises(NotFoundError):
        m.exclude_item("/bogus_folder")

    # check for fatal errors
    assert not m.fatal_errors


def test_selective_sync_api_global(m):
    """Test :meth:`Maestral.exclude_items` to change all items at once."""

    dbx_dirs = [
        "/selective_sync_test_folder",
        "/independent_folder",
        "/selective_sync_test_folder/subfolder_0",
        "/selective_sync_test_folder/subfolder_1",
    ]

    local_dirs = [m.to_local_path(dbx_path) for dbx_path in dbx_dirs]

    # create folder structure
    for path in local_dirs:
        os.mkdir(path)

    wait_for_idle(m)

    # exclude "/selective_sync_test_folder" and one child from sync
    m.excluded_items = [
        "/selective_sync_test_folder",
        "/selective_sync_test_folder/subfolder_0",
    ]
    wait_for_idle(m)

    # check that local items have been deleted
    assert not osp.exists(m.to_local_path("/selective_sync_test_folder"))

    # check that `Maestral.excluded_items` has been updated correctly
    assert m.excluded_items == ["/selective_sync_test_folder"]

    # exclude only child folder from sync, check that it worked
    m.excluded_items = ["/selective_sync_test_folder/subfolder_0"]
    wait_for_idle(m)

    assert osp.exists(m.to_local_path("/selective_sync_test_folder"))
    assert osp.exists(m.to_local_path("/selective_sync_test_folder/subfolder_1"))
    assert m.excluded_items == ["/selective_sync_test_folder/subfolder_0"]

    # check for fatal errors
    assert not m.fatal_errors


def test_selective_sync_api_nested(m):
    """Tests special cases of nested selected sync changes."""

    dbx_dirs = [
        "/selective_sync_test_folder",
        "/independent_folder",
        "/selective_sync_test_folder/subfolder_0",
        "/selective_sync_test_folder/subfolder_1",
    ]

    local_dirs = [m.to_local_path(dbx_path) for dbx_path in dbx_dirs]

    # create folder structure
    for path in local_dirs:
        os.mkdir(path)

    wait_for_idle(m)

    # exclude "/selective_sync_test_folder" from sync
    m.exclude_item("/selective_sync_test_folder")
    wait_for_idle(m)

    # test including a folder inside "/selective_sync_test_folder",
    # "/selective_sync_test_folder" should become included itself but
    # its other children will still be excluded
    m.include_item("/selective_sync_test_folder/subfolder_0")

    assert "/selective_sync_test_folder" not in m.excluded_items
    assert "/selective_sync_test_folder/subfolder_1" in m.excluded_items

    # check for fatal errors
    assert not m.fatal_errors


def test_create_file_diff(m):
    """Tests file diffs for supported and unsupported files."""

    def write_and_get_rev(dbx_path, content, o="w"):
        """
        Open the dbx_path locally and write the content to the string.
        If it should append something, you can set 'o = "a"'.
        """

        local_path = m.to_local_path(dbx_path)
        with open(local_path, o) as f:
            f.write(content)
        wait_for_idle(m)
        return m.client.get_metadata(dbx_path).rev

    dbx_path_success = "/file.txt"
    dbx_path_fail_pdf = "/diff.pdf"
    dbx_path_fail_ext = "/bin.txt"

    with pytest.raises(UnsupportedFileTypeForDiff):
        # Write some dummy stuff to create two revs
        old_rev = write_and_get_rev(dbx_path_fail_pdf, "old")
        new_rev = write_and_get_rev(dbx_path_fail_pdf, "new")
        m.get_file_diff(old_rev, new_rev)

    with pytest.raises(UnsupportedFileTypeForDiff):
        # Add a compiled helloworld c file with .txt extension
        shutil.copy(resources + "/bin.txt", m.dropbox_path)
        wait_for_idle(m)
        old_rev = m.client.get_metadata(dbx_path_fail_ext).rev
        # Just some bytes
        new_rev = write_and_get_rev(dbx_path_fail_ext, b"hi", o="ab")
        m.get_file_diff(old_rev, new_rev)

    old_rev = write_and_get_rev(dbx_path_success, "old")
    new_rev = write_and_get_rev(dbx_path_success, "new")
    # If this does not raise an error,
    # the function should have been successful
    _ = m.get_file_diff(old_rev, new_rev)


def test_restore(m):
    """Tests restoring an old revision"""

    dbx_path = "/file.txt"
    local_path = m.to_local_path(dbx_path)

    # create a local file and sync it, remember its rev
    with open(local_path, "w") as f:
        f.write("old content")

    wait_for_idle(m)

    old_md = m.client.get_metadata(dbx_path)

    # modify the file and sync it
    with open(local_path, "w") as f:
        f.write("new content")

    wait_for_idle(m)

    new_md = m.client.get_metadata(dbx_path)

    assert new_md.content_hash == m.sync.get_local_hash(local_path)

    # restore the old rev

    try:
        m.restore(dbx_path, old_md.rev)
    except SyncError as exc:
        # catch all error for restore in progress, raise otherwise
        if "in progress" not in exc.title:
            raise

    wait_for_idle(m)

    with open(local_path) as f:
        restored_content = f.read()

    assert restored_content == "old content"


def test_restore_failed(m):
    """Tests restoring a non-existing file"""

    with pytest.raises(NotFoundError):
        m.restore("/restored-file", "015982ea314dac40000000154e40990")


def test_sharedlink_lifecycle(m):

    # create a folder to share
    dbx_path = "/shared_folder"
    m.client.make_dir(dbx_path)

    # test creating a shared link
    link_data = m.create_shared_link(dbx_path)

    resp = requests.get(link_data["url"])
    assert resp.status_code == 200

    links = m.list_shared_links(dbx_path)
    assert link_data in links

    # test revoking a shared link
    m.revoke_shared_link(link_data["url"])
    links = m.list_shared_links(dbx_path)
    assert link_data not in links


def test_sharedlink_errors(m):

    dbx_path = "/shared_folder"
    m.client.make_dir(dbx_path)

    # test creating a shared link with password, no password provided
    with pytest.raises(ValueError):
        m.create_shared_link(dbx_path, visibility="password")

    # test creating a shared link with password fails on basic account
    account_info = m.get_account_info()

    if account_info["account_type"][".tag"] == "basic":
        with pytest.raises(SharedLinkError):
            m.create_shared_link(dbx_path, visibility="password", password="secret")

    # test creating a shared link with the same settings as an existing link
    m.create_shared_link(dbx_path)

    with pytest.raises(SharedLinkError):
        m.create_shared_link(dbx_path)

    # test creating a shared link with an invalid path
    with pytest.raises(NotFoundError):
        m.create_shared_link("/this_is_not_a_file.txt")

    # test listing shared links for an invalid path
    with pytest.raises(NotFoundError):
        m.list_shared_links("/this_is_not_a_file.txt")

    # test revoking a non existent link
    with pytest.raises(NotFoundError):
        m.revoke_shared_link("https://www.dropbox.com/sh/48r2qxq748jfk5x/AAAS-niuW")

    # test revoking a malformed link
    with pytest.raises(SharedLinkError):
        m.revoke_shared_link("https://www.testlink.de")


@pytest.mark.skipif(sys.platform != "linux", reason="inotify specific test")
@pytest.mark.skipif(os.getenv("CI", False) is False, reason="Only running on CI")
def test_inotify_error(m):

    max_user_watches, max_user_instances, _ = get_inotify_limits()

    try:
        subprocess.check_call(["sudo", "sysctl", "-w", "fs.inotify.max_user_watches=1"])
    except subprocess.CalledProcessError:
        return

    try:

        m.stop_sync()
        wait_for_idle(m)

        # create some folders for us to watch
        os.mkdir(m.dropbox_path + "/folder 1")
        os.mkdir(m.dropbox_path + "/folder 2")
        os.mkdir(m.dropbox_path + "/folder 3")

        m.start_sync()

        assert len(m.fatal_errors) == 1
        assert m.fatal_errors[0]["type"] == "InotifyError"

    finally:
        subprocess.check_call(
            ["sudo", "sysctl", "-w", f"fs.inotify.max_user_watches={max_user_watches}"]
        )
