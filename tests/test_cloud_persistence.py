import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cloud_persistence


class FakeNotFound(Exception):
    code = 404


class FakeBlob:
    def __init__(self):
        self.data = None
        self.generation = None
        self.preconditions = []
        self.download_preconditions = []
        self.fail_upload = False

    def reload(self):
        if self.data is None:
            raise FakeNotFound("404")

    def download_to_filename(self, filename, *, if_generation_match):
        self.download_preconditions.append(if_generation_match)
        Path(filename).write_bytes(self.data)

    def upload_from_filename(
        self,
        filename,
        *,
        content_type,
        if_generation_match,
        timeout,
    ):
        if self.fail_upload:
            raise RuntimeError("storage unavailable")
        self.preconditions.append(if_generation_match)
        self.data = Path(filename).read_bytes()
        self.generation = (self.generation or 0) + 1


class CloudPersistenceTests(unittest.TestCase):
    def setUp(self):
        cloud_persistence._generation = None
        cloud_persistence._storage_client = None
        cloud_persistence._dirty = False
        self.blob = FakeBlob()
        self.bucket_patch = mock.patch.object(
            cloud_persistence,
            "_BACKUP_BUCKET",
            "test-bucket",
        )
        self.bootstrap_patch = mock.patch.object(
            cloud_persistence,
            "_ALLOW_EMPTY_BOOTSTRAP",
            False,
        )
        self.blob_patch = mock.patch.object(
            cloud_persistence,
            "_get_blob",
            return_value=self.blob,
        )
        self.bucket_patch.start()
        self.bootstrap_patch.start()
        self.blob_patch.start()

    def tearDown(self):
        self.blob_patch.stop()
        self.bootstrap_patch.stop()
        self.bucket_patch.stop()

    def test_committed_database_round_trips_through_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "live.db"
            source = sqlite3.connect(db_path)
            source.execute("CREATE TABLE state(value TEXT)")
            source.execute("INSERT INTO state VALUES ('still here')")
            source.commit()

            with mock.patch.object(
                cloud_persistence,
                "_ALLOW_EMPTY_BOOTSTRAP",
                True,
            ):
                self.assertTrue(
                    cloud_persistence.backup_database(source, db_path)
                )
            source.close()
            db_path.unlink()

            cloud_persistence._generation = None
            self.assertTrue(cloud_persistence.restore_database(db_path))
            restored = sqlite3.connect(db_path)
            try:
                value = restored.execute(
                    "SELECT value FROM state"
                ).fetchone()[0]
            finally:
                restored.close()

            self.assertEqual(value, "still here")
            self.assertEqual(self.blob.preconditions, [0])
            self.assertEqual(self.blob.download_preconditions, [1])

    def test_restore_never_overwrites_an_existing_local_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "live.db"
            db_path.write_bytes(b"local")
            self.blob.data = b"remote"
            self.blob.generation = 4

            self.assertFalse(cloud_persistence.restore_database(db_path))
            self.assertEqual(db_path.read_bytes(), b"local")

    def test_missing_remote_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "live.db"
            with self.assertRaisesRegex(
                RuntimeError,
                "refusing an implicit",
            ):
                cloud_persistence.restore_database(db_path)
            self.assertFalse(db_path.exists())

    def test_failed_upload_marks_persistence_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "live.db"
            source = sqlite3.connect(db_path)
            source.execute("CREATE TABLE state(value TEXT)")
            source.commit()
            self.blob.fail_upload = True
            with mock.patch.object(
                cloud_persistence,
                "_ALLOW_EMPTY_BOOTSTRAP",
                True,
            ):
                with self.assertRaises(
                    cloud_persistence.PersistenceUnavailable
                ):
                    cloud_persistence.backup_database(source, db_path)
            source.close()
            self.assertTrue(cloud_persistence.persistence_pending())


if __name__ == "__main__":
    unittest.main()
