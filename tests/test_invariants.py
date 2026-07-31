import os
import tempfile
import unittest
from pathlib import Path


_temp_dir = tempfile.TemporaryDirectory(prefix="lastwords-tests-")
os.environ["LASTWORDS_DB"] = str(Path(_temp_dir.name) / "test.db")

import app as lastwords  # noqa: E402


class VocabularyInvariantTests(unittest.TestCase):
    def test_unknown_word_is_redacted_without_expanding_vocabulary(self):
        unknown = "zzzxylophone"
        with lastwords.get_db() as conn:
            before = conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()["c"]
            segments, burned, ghosts = lastwords.build_segments_and_burn(
                conn,
                unknown,
                {unknown},
            )
            after = conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()["c"]
            row = conn.execute(
                "SELECT status FROM words WHERE word=?",
                (unknown,),
            ).fetchone()

        self.assertEqual(before, after)
        self.assertIsNone(row)
        self.assertEqual(segments, [{"t": "x"}])
        self.assertEqual(burned, [])
        self.assertEqual(ghosts, [unknown])

    def test_content_word_can_appear_only_once_in_a_reply(self):
        with lastwords.get_db() as conn:
            word = conn.execute(
                "SELECT word FROM words WHERE status='alive' ORDER BY word LIMIT 1"
            ).fetchone()["word"]
            total_before = conn.execute(
                "SELECT COUNT(*) AS c FROM words"
            ).fetchone()["c"]
            segments, burned, ghosts = lastwords.build_segments_and_burn(
                conn,
                f"{word} {word}",
                set(),
            )
            total_after = conn.execute(
                "SELECT COUNT(*) AS c FROM words"
            ).fetchone()["c"]

        self.assertEqual(total_before, total_after)
        self.assertEqual(segments, [{"t": "w", "s": word}, {"t": "x"}])
        self.assertEqual(burned, [word])
        self.assertEqual(ghosts, [word])

    def test_public_greet_route_is_removed(self):
        paths = {route.path for route in lastwords.app.routes}
        self.assertNotIn("/api/greet", paths)

    def test_rate_limit_is_not_presented_as_a_spoken_utterance(self):
        response = lastwords.gentle_rate_limit_reply(100, 200, 3)
        self.assertEqual(response["segments"], [])
        self.assertEqual(response["burned_now"], [])
        self.assertTrue(response["rate_limited"])
        self.assertIn("system_message", response)

    def test_shared_rate_limit_has_a_server_side_ceiling(self):
        original_limit = lastwords.GLOBAL_MESSAGES_PER_MINUTE
        lastwords.GLOBAL_MESSAGES_PER_MINUTE = 2
        try:
            with lastwords.get_db() as conn:
                conn.execute("DELETE FROM recent_messages")
                self.assertTrue(lastwords.claim_global_message_slot(conn, 1000.0))
                self.assertTrue(lastwords.claim_global_message_slot(conn, 1000.1))
                self.assertFalse(lastwords.claim_global_message_slot(conn, 1000.2))
        finally:
            lastwords.GLOBAL_MESSAGES_PER_MINUTE = original_limit


if __name__ == "__main__":
    unittest.main()
