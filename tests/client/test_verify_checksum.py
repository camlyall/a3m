# This file is part of Archivematica.
#
# Copyright 2010-2017 Artefactual Systems Inc. <http://artefactual.com>
#
# Archivematica is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Archivematica is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Archivematica.  If not, see <http://www.gnu.org/licenses/>.
"""Test Verify Checksum Job in Archivematica.

Tests for the verify checksum Job in Archivematica which makes calls out to the
hashsum checksum utilities. We need to ensure that the output of the tool is
mapped consistently to something that can be understood by users when
debugging their preservation workflow.
"""
import os
import subprocess
from uuid import UUID

import pytest
from django.core.management import call_command

from a3m.client.clientScripts.verify_checksum import get_file_queryset
from a3m.client.clientScripts.verify_checksum import Hashsum
from a3m.client.clientScripts.verify_checksum import NoHashCommandAvailable
from a3m.client.clientScripts.verify_checksum import PREMISFailure
from a3m.client.clientScripts.verify_checksum import write_premis_event_per_file
from a3m.client.job import Job
from a3m.main.models import Event
from a3m.main.models import File


THIS_DIR = os.path.dirname(__file__)


class TestHashsum:
    """Hashsum test runner object."""

    assert_exception_string = "Hashsum exception string returned is incorrect"
    assert_return_value = "Hashsum comparison returned something other than 1: {}"

    @staticmethod
    def setup_hashsum(path, job):
        """Return a hashsum instance to calling functions and perform any
        other additional setup as necessary.
        """
        return Hashsum(path, job)

    def test_invalid_initialisation(self):
        """Test that we don't return a Hashsum object if there isn't a tool
        configured to work with the file path provided.
        """
        with pytest.raises(NoHashCommandAvailable):
            Hashsum("checksum.invalid_hash")

    @pytest.mark.parametrize(
        "fixture",
        [
            ("metadata/checksum.md5", True),
            ("metadata/checksum.sha1", True),
            ("metadata/checksum.sha256", True),
            ("metadata/checksum.sha512", True),
            ("metadata/checksum_md5", False),
            ("metadata/checksum_sha1", False),
            ("metadata/checksum_sha256", False),
            ("metadata/checksum_sha512", False),
        ],
    )
    def test_valid_initialisation(self, fixture):
        """Test that we don't return a Hashsum object if there isn't a tool
        configured to work with the file path provided.
        """
        if fixture[1]:
            assert isinstance(
                Hashsum(fixture[0]), Hashsum
            ), "Hashsum object not instantiated correctly"
        else:
            with pytest.raises(NoHashCommandAvailable):
                Hashsum(fixture[0])

    def test_provenance_string(self, mocker):
        """Test to ensure that the string output to the PREMIS event for this
        microservice Job is consistent with what we're expecting. Provenance
        string includes the command called, plus the utility's version string.
        """
        hash_file = "metadata/checksum.md5"
        hashsum = self.setup_hashsum(hash_file, Job("stub", "stub", ["", ""]))
        version_string = [
            "md5sum (GNU coreutils) 8.28",
            "Copyright (C) 2017 Free Software Foundation, Inc.",
        ]
        mock = mocker.patch.object(hashsum, "_call", return_value=version_string)
        assert (
            hashsum.version() == "md5sum (GNU coreutils) 8.28"
        ), "Hashsum version retrieved is incorrect"
        mock.assert_called_once_with("--version")
        mocker.patch.object(
            hashsum,
            "command_called",
            (hashsum.COMMAND,) + ("-c", "--strict", hash_file),
        )
        expected_provenance = 'program="md5sum -c --strict metadata/checksum.md5"; version="md5sum (GNU coreutils) 8.28"'
        provenance_output = hashsum.get_command_detail()
        assert (
            provenance_output == expected_provenance
        ), f"Provenance output is incorrect: {provenance_output}"

    def test_provenance_string_no_command(self):
        """When nothing has happened, e.g. the checksums haven't been validated
        then it should be practically impossible to write to the database and
        generate some form of false-positive.
        """
        hash_file = "metadata/checksum.sha1"
        hashsum = self.setup_hashsum(hash_file, Job("stub", "stub", ["", ""]))
        try:
            hashsum.get_command_detail()
        except PREMISFailure:
            pass

    def test_compare_hashes_failed(self, mocker):
        """Ensure we get consistent output when the checksum comparison fails."""
        hash_file = "metadata/checksum.sha256"
        job = Job("stub", "stub", ["", ""])
        hashsum = self.setup_hashsum(hash_file, job)
        toolname = "sha256sum"
        objects_dir = "objects"
        output_string = (
            b"objects/file1.bin: OK\n"
            b"objects/file2.bin: FAILED\n"
            b"objects/nested/\xe3\x83\x95\xe3\x82\xa1\xe3\x82\xa4\xe3\x83\xab"
            b"3.bin: FAILED\n"
            b"objects/readonly.file: FAILED open or read"
        )
        exception_string = (
            "sha256: comparison exited with status: 1. Please check the formatting of the checksums or integrity of the files.\n"
            "sha256: objects/file2.bin: FAILED\n"
            "sha256: objects/nested/ファイル3.bin: FAILED\n"
            "sha256: objects/readonly.file: FAILED open or read"
        )
        mock = mocker.patch.object(hashsum, "_call", return_value=output_string)
        mocker.patch.object(hashsum, "count_and_compare_lines", return_value=True)
        mock.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=toolname, output=output_string
        )
        ret = hashsum.compare_hashes("")
        mock.assert_called_once_with(
            "-c", "--strict", hash_file, transfer_dir=objects_dir
        )
        assert ret == 1, self.assert_return_value.format(ret)
        assert (
            job.get_stderr().strip() == exception_string
        ), self.assert_exception_string

    def test_compare_hashes_with_bad_files(self, mocker):
        """Ensure that the formatting of errors is consistent if improperly
        formatted files are provided to hashsum.
        """
        hash_file = "metadata/checksum.sha1"
        job = Job("stub", "stub", ["", ""])
        hashsum = self.setup_hashsum(hash_file, job)
        toolname = "sha1sum"
        objects_dir = "objects"
        no_proper_output = (
            b"sha1sum: metadata/checksum.sha1: no properly formatted SHA1 "
            b"checksum lines found"
        )
        except_string_no_proper_out = (
            "sha1: comparison exited with status: 1. Please check the formatting of the checksums or integrity of the files.\n"
            "sha1: sha1sum: metadata/checksum.sha1: no properly formatted "
            "SHA1 checksum lines found"
        )
        improper_formatting = b"sha1sum: WARNING: 1 line is improperly formatted"
        except_string_improper_format = (
            "sha1: comparison exited with status: 1. Please check the formatting of the checksums or integrity of the files.\n"
            "sha1: sha1sum: WARNING: 1 line is improperly formatted"
        )
        mock = mocker.patch.object(hashsum, "_call", return_value=no_proper_output)
        mocker.patch.object(hashsum, "count_and_compare_lines", return_value=True)
        mock.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=toolname, output=no_proper_output
        )
        ret = hashsum.compare_hashes("")
        mock.assert_called_once_with(
            "-c", "--strict", hash_file, transfer_dir=objects_dir
        )
        assert (
            job.get_stderr().strip() == except_string_no_proper_out
        ), self.assert_exception_string
        assert ret == 1, self.assert_return_value.format(ret)
        # Flush job.error as it isn't flushed automatically.
        job.error = ""
        mock = mocker.patch.object(hashsum, "_call", return_value=improper_formatting)
        mock.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="sha1sum", output=improper_formatting
        )
        ret = hashsum.compare_hashes("")
        assert (
            job.get_stderr().strip() == except_string_improper_format
        ), self.assert_exception_string
        mock.assert_called_once_with(
            "-c", "--strict", hash_file, transfer_dir=objects_dir
        )
        assert ret == 1, self.assert_return_value.format(ret)

    def test_line_comparison_fail(self, mocker):
        """If the checksum line and object comparison function fails then
        we want to return early and _call shouldn't be called.
        """
        hash_file = "metadata/checksum.sha1"
        hashsum = self.setup_hashsum(hash_file, Job("stub", "stub", ["", ""]))
        toolname = "sha1sum"
        mock = mocker.patch.object(hashsum, "_call", return_value=None)
        mocker.patch.object(hashsum, "count_and_compare_lines", return_value=False)
        mock.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=toolname, output=None
        )
        ret = hashsum.compare_hashes("")
        mock.assert_not_called()
        assert ret == 1, self.assert_return_value.format(ret)

    @pytest.mark.parametrize(
        "fixture",
        [
            ("checksum.md5", "md5"),
            ("checksum.sha1", "sha1"),
            ("checksum.sha256", "sha256"),
            ("checksum_md5", "checksum_md5"),
            ("checksum_sha1", "checksum_sha1"),
            ("checksum_sha256", "checksum_sha256"),
        ],
    )
    def test_get_ext(self, fixture):
        """get_ext helps to format usefully."""
        assert (
            Hashsum.get_ext(fixture[0]) == fixture[1]
        ), "Incorrect extension returned from Hashsum"

    @staticmethod
    def test_decode_and_version_string():
        """Test that we can separate the version and license information
        correctly from {command} --version.
        """
        version_string = (
            b"sha256sum (GNU coreutils) 8.28\n"
            b"Copyright (C) 2017 Free Software Foundation, Inc."
        )
        assert Hashsum._decode(version_string)[
            0
        ], "Version string incorrectly decoded by Hashsum"
        assert (
            Hashsum._decode(version_string)[0] == "sha256sum (GNU coreutils) 8.28"
        ), "Invalid version string decoded by Hashsum"

    @staticmethod
    @pytest.fixture(scope="class")
    def django_db_setup(django_db_blocker):
        """Load the various database fixtures required for our tests."""
        fixtures_dir = "microservice_agents"
        # hashsum_agents and hashsum_unitvars work in concert to return the
        # Archivematica current user to the result set.
        fixture_files = [
            "transfer.json",
            "files-transfer-unicode.json",
            os.path.join(fixtures_dir, "microservice_agents.json"),
        ]
        fixtures = []
        for fixture in fixture_files:
            fixtures.append(os.path.join(THIS_DIR, "fixtures", fixture))
        with django_db_blocker.unblock():
            for fixture in fixtures:
                call_command("loaddata", fixture)

    @pytest.mark.django_db
    def test_write_premis_event_to_db(self):
        """Test that the microservice job connects to the database as
        anticipated, writes its data, and that data can then be retrieved.
        """
        # Values the job will write.
        algorithms = ["md5", "sha512", "sha1"]
        event_type = "fixity check"
        event_outcome = "pass"
        # Values we will write.
        detail = "suma de verificación validada: OK"
        package_uuid = "e95ab50f-9c84-45d5-a3ca-1b0b3f58d9b6"
        kwargs = {"removedtime__isnull": True, "transfer_id": package_uuid}
        file_objs_queryset = File.objects.filter(**kwargs)
        for algorithm in algorithms:
            event_detail = f"{algorithm}: {detail}"
            write_premis_event_per_file(file_objs_queryset, package_uuid, event_detail)
        file_uuids = File.objects.filter(**kwargs).values_list("uuid")
        assert file_uuids

        event_algorithms = []
        for uuid_ in file_uuids:
            events = Event.objects.filter(file_uuid=uuid_, event_type=event_type)
            assert len(events) == len(algorithms)
            assert events[0].event_outcome == event_outcome
            assert detail in events[0].event_detail
            UUID(str(events[0].event_id), version=4)
            assert len(events) == 3
            assert events[0].agents.count() == 2
            assert events[0].agents.get(identifiertype="preservation system")
            assert events[0].agents.get(identifiertype="repository code")
            assert events[1].agents.count() == 2
            assert events[1].agents.get(identifiertype="preservation system")
            assert events[1].agents.get(identifiertype="repository code")
            assert events[2].agents.count() == 2
            assert events[2].agents.get(identifiertype="preservation system")
            assert events[2].agents.get(identifiertype="repository code")
            # Collect the different checksum algorithms written to ensure they
            # were all written independently in the function.
            for event in events:
                event_algorithms.append(event.event_detail.split(":", 1)[0])

        assert set(event_algorithms) == set(algorithms)

    @pytest.mark.django_db
    def test_get_file_obj_queryset(self):
        """Test the retrieval and failure of the queryset used for creating
        events for all the file objects associated with the transfer checksums.
        """
        package_uuid = "e95ab50f-9c84-45d5-a3ca-1b0b3f58d9b6"
        assert get_file_queryset(package_uuid)
        invalid_package_uuid = "badf00d1-9c84-45d5-a3ca-1b0b3f58d9b6"
        with pytest.raises(PREMISFailure):
            get_file_queryset(invalid_package_uuid)
