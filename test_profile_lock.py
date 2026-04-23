from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from profile_lock import ProfileLockStore


class ProfileLockStoreTests(unittest.TestCase):
    def test_set_verify_and_remove_profile_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProfileLockStore(Path(temp_dir) / "profile_locks.json")

            store.set_password("chrome", "Profile 2", "secret123")

            self.assertTrue(store.is_locked("chrome", "Profile 2"))
            self.assertTrue(store.verify_password("chrome", "Profile 2", "secret123"))
            self.assertFalse(store.verify_password("chrome", "Profile 2", "wrong123"))

            store.remove_lock("chrome", "Profile 2")

            self.assertFalse(store.is_locked("chrome", "Profile 2"))

    def test_passwords_are_not_stored_as_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_file = Path(temp_dir) / "profile_locks.json"
            store = ProfileLockStore(lock_file)

            store.set_password("chrome", "Profile 2", "secret123")

            self.assertNotIn("secret123", lock_file.read_text(encoding="utf-8"))

    def test_short_password_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProfileLockStore(Path(temp_dir) / "profile_locks.json")

            with self.assertRaises(ValueError):
                store.set_password("chrome", "Profile 2", "12345")


if __name__ == "__main__":
    unittest.main()
