import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


_temp_dir = tempfile.TemporaryDirectory(prefix="lastwords-world-tests-")
if "app" not in sys.modules:
    os.environ["LASTWORDS_DB"] = str(Path(_temp_dir.name) / "test.db")

import app as lastwords  # noqa: E402


class WorldStateTests(unittest.TestCase):
    def setUp(self):
        with lastwords.get_db() as conn:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM utterances")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM recent_messages")
            conn.execute("DELETE FROM world_editions")
            conn.execute("DELETE FROM words")
            conn.executemany(
                "INSERT INTO words(word, status) VALUES (?, 'alive')",
                [(word,) for word in lastwords.SEED_WORDS],
            )
            conn.execute(
                "UPDATE stats SET value=0 WHERE key='message_count'"
            )
            conn.execute(
                """
                UPDATE ending
                SET silenced=0, poem=NULL, silenced_at=NULL,
                    finalized_at=NULL, archived_at=NULL
                WHERE id=1
                """
            )
            conn.execute(
                """
                UPDATE world_state
                SET version=0,
                    genome_json=?,
                    last_word=NULL,
                    last_law=NULL,
                    last_consequence=NULL,
                    build_status='pending',
                    build_ms=NULL,
                    updated_at=?,
                    edition_number=1,
                    born_at=?,
                    lineage_seed=?
                WHERE id=1
                """,
                (
                    json.dumps(
                        lastwords.INITIAL_WORLD_GENOME,
                        sort_keys=True,
                    ),
                    lastwords.now_iso(),
                    lastwords.now_iso(),
                    lastwords.INITIAL_LINEAGE_SEED,
                ),
            )

    def snapshot(self):
        with lastwords.get_db() as conn:
            return {
                "world": lastwords.get_world_state(conn),
                "ending": lastwords.get_ending(conn),
                "words": [
                    tuple(row)
                    for row in conn.execute(
                        """
                        SELECT word, status, burned_at, revived_count
                        FROM words
                        ORDER BY word
                        """
                    ).fetchall()
                ],
                "message_count": conn.execute(
                    "SELECT value FROM stats WHERE key='message_count'"
                ).fetchone()["value"],
                "events": conn.execute(
                    "SELECT COUNT(*) AS c FROM events"
                ).fetchone()["c"],
                "utterances": conn.execute(
                    "SELECT COUNT(*) AS c FROM utterances"
                ).fetchone()["c"],
                "sessions": conn.execute(
                    "SELECT COUNT(*) AS c FROM sessions"
                ).fetchone()["c"],
                "recent_messages": conn.execute(
                    "SELECT COUNT(*) AS c FROM recent_messages"
                ).fetchone()["c"],
                "editions": [
                    tuple(row)
                    for row in conn.execute(
                        """
                        SELECT edition_number, final_poem, archived_at
                        FROM world_editions
                        ORDER BY edition_number
                        """
                    ).fetchall()
                ],
            }

    def first_option(self):
        state = lastwords.api_state()
        self.assertEqual(len(state["sacrifice_options"]), 3)
        return state["sacrifice_options"][0]

    def leave_only_world_law(self, law):
        genome = {
            name: 0.0
            for name in lastwords.INITIAL_WORLD_GENOME
        }
        genome[law] = lastwords.INITIAL_WORLD_GENOME[law]
        with lastwords.get_db() as conn:
            conn.execute(
                """
                UPDATE world_state
                SET version=19,
                    genome_json=?,
                    last_word='memory',
                    last_law='memory',
                    last_consequence='the last remembered trail vanished',
                    build_status='pending',
                    build_ms=NULL,
                    updated_at=?
                WHERE id=1
                """,
                (
                    json.dumps(genome, sort_keys=True),
                    lastwords.now_iso(),
                ),
            )

    def finish_current_world(self, session_id="world-final-helper"):
        self.leave_only_world_law("gravity")
        before = lastwords.api_state()
        option = before["sacrifice_options"][0]
        self.assertEqual(option["law"], "gravity")
        with mock.patch.object(lastwords, "LLM_AVAILABLE", False):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id=session_id,
                    sacrifice_word=option["word"],
                )
            )
        self.assertEqual(response.status_code, 200)
        return before, option, json.loads(response.body)

    def test_state_has_stable_three_alive_sacrifice_options(self):
        first_state = lastwords.api_state()
        second_state = lastwords.api_state()

        self.assertEqual(first_state["world"]["version"], 0)
        self.assertEqual(
            first_state["world"]["genome"],
            lastwords.INITIAL_WORLD_GENOME,
        )
        self.assertEqual(first_state["world"]["build_status"], "pending")
        self.assertIsNone(first_state["world"]["build_ms"])
        self.assertEqual(first_state["world"]["edition_number"], 1)
        self.assertEqual(first_state["edition"]["number"], 1)
        self.assertEqual(first_state["edition"]["label"], "WORLD 001")
        self.assertEqual(first_state["edition"]["status"], "alive")
        self.assertEqual(
            first_state["edition"]["lineage_seed"],
            lastwords.INITIAL_LINEAGE_SEED,
        )
        self.assertEqual(
            first_state["world"]["lineage_seed"],
            lastwords.INITIAL_LINEAGE_SEED,
        )
        self.assertTrue(first_state["edition"]["born_at"])
        self.assertIsNone(first_state["edition"]["died_at"])
        self.assertIsNone(first_state["edition"]["rebirth_at"])
        self.assertIsNone(first_state["edition"]["rebirth_in_seconds"])
        self.assertEqual(first_state["archives"], [])
        self.assertEqual(first_state["archive_count"], 0)
        self.assertIsNone(first_state["latest_archive"])
        self.assertEqual(
            first_state["sacrifice_options"],
            second_state["sacrifice_options"],
        )
        self.assertEqual(len(first_state["sacrifice_options"]), 3)

        with lastwords.get_db() as conn:
            for option in first_state["sacrifice_options"]:
                row = conn.execute(
                    "SELECT status FROM words WHERE word=?",
                    (option["word"],),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["status"], "alive")
                self.assertIn(option["law"], first_state["world"]["genome"])
                self.assertTrue(option["consequence"])
                self.assertIn("\u2192", option["preview"])
                self.assertEqual(option["parameter"], option["law"])
                self.assertIsInstance(option["to"], float)

        edition_index = lastwords.api_editions()
        self.assertEqual(edition_index["current"], first_state["edition"])
        self.assertEqual(edition_index["editions"], [])
        missing = lastwords.api_edition(1)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            json.loads(missing.body)["code"],
            "edition_not_found",
        )

    def test_init_db_backfills_missing_genome_keys_without_resetting_history(self):
        old_genome = {
            law: value
            for law, value in list(
                lastwords.INITIAL_WORLD_GENOME.items()
            )[:12]
        }
        old_genome["gravity"] = 0.123
        preserved_updated_at = "2026-07-30T12:34:56+00:00"
        with lastwords.get_db() as conn:
            conn.execute(
                """
                UPDATE world_state
                SET version=7,
                    genome_json=?,
                    last_word='memory',
                    last_law='memory',
                    last_consequence='preserve me',
                    build_status='complete',
                    build_ms=87,
                    updated_at=?
                WHERE id=1
                """,
                (
                    json.dumps(old_genome, sort_keys=True),
                    preserved_updated_at,
                ),
            )

        lastwords.init_db()

        with lastwords.get_db() as conn:
            migrated = lastwords.get_world_state(conn)
        self.assertEqual(
            set(migrated["genome"]),
            set(lastwords.INITIAL_WORLD_GENOME),
        )
        self.assertEqual(migrated["genome"]["gravity"], 0.123)
        for law, value in old_genome.items():
            self.assertEqual(migrated["genome"][law], value)
        for law in set(lastwords.INITIAL_WORLD_GENOME) - set(old_genome):
            self.assertEqual(
                migrated["genome"][law],
                lastwords.INITIAL_WORLD_GENOME[law],
            )
        self.assertEqual(migrated["version"], 7)
        self.assertEqual(migrated["last_word"], "memory")
        self.assertEqual(migrated["last_law"], "memory")
        self.assertEqual(migrated["last_consequence"], "preserve me")
        self.assertEqual(migrated["build_status"], "complete")
        self.assertEqual(migrated["build_ms"], 87)
        self.assertEqual(migrated["updated_at"], preserved_updated_at)

    def test_mock_reply_semantically_reflects_every_changed_law(self):
        alive_words = list(lastwords.SEED_WORDS)
        alive = set(alive_words)
        for law, palette in lastwords.LAW_MOCK_WORDS.items():
            generation_text = (
                "hello\n\n"
                "The visitor sacrificed a word; the shared world "
                f"has now lost {law}, so the world changed. "
                "Answer as a being living under that changed law."
            )
            first = lastwords.mock_reply(generation_text, alive_words)
            second = lastwords.mock_reply(generation_text, alive_words)
            chosen = lastwords.content_tokens(first)

            with self.subTest(law=law):
                self.assertEqual(first, second)
                self.assertGreaterEqual(len(chosen), 2)
                self.assertLessEqual(len(chosen), 3)
                self.assertEqual(len(chosen), len(set(chosen)))
                self.assertTrue(set(chosen).issubset(set(palette)))
                self.assertTrue(set(chosen).issubset(alive))
                self.assertTrue(
                    all(
                        not lastwords.is_stopword_or_short(word)
                        for word in chosen
                    )
                )

    def test_valid_sacrifice_burns_word_and_changes_world(self):
        option = self.first_option()
        before = lastwords.api_state()
        captured_generation_text = []

        def fake_generate_reply(text, conn):
            captured_generation_text.append(text)
            return "I am."

        with mock.patch.object(
            lastwords,
            "generate_reply",
            side_effect=fake_generate_reply,
        ):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-valid",
                    sacrifice_word=option["word"],
                )
            )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.body)
        self.assertEqual(data["sacrificed"]["word"], option["word"])
        self.assertEqual(data["sacrificed"]["law"], option["law"])
        self.assertEqual(data["sacrificed"]["version"], 1)
        self.assertEqual(data["sacrificed"]["parameter"], option["parameter"])
        self.assertEqual(data["sacrificed"]["to"], option["to"])
        self.assertEqual(data["burned_now"], [])
        self.assertEqual(data["world"]["version"], 1)
        self.assertEqual(data["world"]["genome"][option["law"]], 0.0)
        self.assertNotEqual(data["world"]["genome"], before["world"]["genome"])
        self.assertEqual(data["world"]["build_status"], "pending")
        self.assertIsNone(data["world"]["build_ms"])
        self.assertEqual(data["total"], before["total"])

        self.assertEqual(len(captured_generation_text), 1)
        generation_text = captured_generation_text[0]
        self.assertTrue(generation_text.startswith("hello\n\n"))
        self.assertIn(
            f"The visitor sacrificed {option['word']}",
            generation_text,
        )
        self.assertIn(
            f"has now lost {option['law']}",
            generation_text,
        )
        self.assertIn(option["consequence"], generation_text)
        self.assertIn(
            "Answer as a being living under that changed law.",
            generation_text,
        )

        after = lastwords.api_state()
        self.assertEqual(after["world"], data["world"])
        self.assertEqual(after["total"], before["total"])
        self.assertNotIn(
            option["word"],
            {item["word"] for item in after["sacrifice_options"]},
        )
        with lastwords.get_db() as conn:
            word_row = conn.execute(
                "SELECT status FROM words WHERE word=?",
                (option["word"],),
            ).fetchone()
            event = conn.execute(
                """
                SELECT kind, word
                FROM events
                WHERE word=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (option["word"],),
            ).fetchone()
        self.assertEqual(word_row["status"], "burned")
        self.assertEqual((event["kind"], event["word"]), ("burn", option["word"]))

    def test_reused_and_unknown_sacrifices_return_409_without_side_effects(self):
        option = self.first_option()
        with mock.patch.object(
            lastwords,
            "generate_reply",
            return_value="I am.",
        ):
            first = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-first",
                    sacrifice_word=option["word"],
                )
            )
        self.assertEqual(first.status_code, 200)
        baseline = self.snapshot()

        with mock.patch.object(
            lastwords,
            "generate_reply",
            side_effect=AssertionError("LLM path must not run"),
        ):
            reused = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-reused",
                    sacrifice_word=option["word"],
                )
            )
            unknown = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-unknown",
                    sacrifice_word="zzzxylophone",
                )
            )

        self.assertEqual(reused.status_code, 409)
        self.assertEqual(unknown.status_code, 409)
        self.assertEqual(
            json.loads(reused.body)["code"],
            "sacrifice_conflict",
        )
        self.assertEqual(
            json.loads(unknown.body)["code"],
            "sacrifice_conflict",
        )
        self.assertEqual(self.snapshot(), baseline)

    def test_late_sacrifice_conflict_rolls_back_the_whole_request(self):
        option = self.first_option()
        baseline = self.snapshot()

        def mutate_then_conflict(conn, sacrifice_word):
            conn.execute(
                """
                UPDATE words
                SET status='burned', burned_at=?
                WHERE word=?
                """,
                (lastwords.now_iso(), sacrifice_word),
            )
            lastwords.log_event(conn, "burn", sacrifice_word)
            raise lastwords.SacrificeConflict("simulated late conflict")

        with mock.patch.object(
            lastwords,
            "sacrifice_world_law",
            side_effect=mutate_then_conflict,
        ), mock.patch.object(
            lastwords,
            "generate_reply",
            side_effect=AssertionError("LLM path must not run"),
        ):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-late-conflict",
                    sacrifice_word=option["word"],
                )
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(), baseline)

    def test_sacrifice_helper_rolls_back_its_own_partial_mutation(self):
        option = self.first_option()

        class NoWorldUpdate:
            rowcount = 0

        class FailedWorldCasConnection:
            def __init__(self, conn):
                self.conn = conn

            def execute(self, sql, parameters=()):
                if "UPDATE world_state" in sql:
                    return NoWorldUpdate()
                return self.conn.execute(sql, parameters)

        with lastwords.get_db() as conn:
            proxy = FailedWorldCasConnection(conn)
            with self.assertRaises(lastwords.SacrificeConflict):
                lastwords.sacrifice_world_law(proxy, option["word"])

        with lastwords.get_db() as conn:
            row = conn.execute(
                "SELECT status, burned_at FROM words WHERE word=?",
                (option["word"],),
            ).fetchone()
            event_count = conn.execute(
                "SELECT COUNT(*) AS c FROM events WHERE word=?",
                (option["word"],),
            ).fetchone()["c"]
            world = lastwords.get_world_state(conn)

        self.assertEqual(row["status"], "alive")
        self.assertIsNone(row["burned_at"])
        self.assertEqual(event_count, 0)
        self.assertEqual(world["version"], 0)

    def test_two_visitors_cannot_sacrifice_the_same_word(self):
        option = self.first_option()
        total_before = lastwords.api_state()["total"]
        first_is_generating = threading.Event()
        release_first = threading.Event()
        generation_calls = 0
        calls_lock = threading.Lock()
        responses = []

        def slow_first_reply(text, conn):
            nonlocal generation_calls
            with calls_lock:
                generation_calls += 1
                call_number = generation_calls
            if call_number == 1:
                first_is_generating.set()
                self.assertTrue(release_first.wait(timeout=5))
            return "I am."

        def send(session_id):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id=session_id,
                    sacrifice_word=option["word"],
                )
            )
            responses.append(response)

        with mock.patch.object(
            lastwords,
            "generate_reply",
            side_effect=slow_first_reply,
        ):
            first = threading.Thread(target=send, args=("world-race-a",))
            second = threading.Thread(target=send, args=("world-race-b",))
            first.start()
            self.assertTrue(first_is_generating.wait(timeout=5))
            second.start()
            time.sleep(0.05)
            release_first.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(
            sorted(response.status_code for response in responses),
            [200, 409],
        )
        self.assertEqual(generation_calls, 1)
        state = lastwords.api_state()
        self.assertEqual(state["world"]["version"], 1)
        self.assertEqual(state["total"], total_before)
        with lastwords.get_db() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM words WHERE word=?",
                    (option["word"],),
                ).fetchone()["status"],
                "burned",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM sessions"
                ).fetchone()["c"],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM recent_messages"
                ).fetchone()["c"],
                1,
            )

    def test_slow_generation_does_not_block_a_distinct_sacrifice(self):
        options = lastwords.api_state()["sacrifice_options"]
        first_option, second_option = options[:2]
        self.assertNotEqual(first_option["law"], second_option["law"])
        first_is_generating = threading.Event()
        release_first = threading.Event()
        second_done = threading.Event()
        responses = {}
        failures = []
        generation_transaction_states = []

        def controlled_reply(text, conn):
            generation_transaction_states.append(conn.in_transaction)
            if f"sacrificed {first_option['word']}" in text:
                first_is_generating.set()
                if not release_first.wait(timeout=5):
                    raise AssertionError("slow generation was not released")
            return "I am."

        def send(name, option):
            try:
                responses[name] = lastwords.api_message(
                    lastwords.MessageIn(
                        text="hello",
                        session_id=f"world-distinct-{name}",
                        sacrifice_word=option["word"],
                    )
                )
            except Exception as error:  # noqa: BLE001
                failures.append(error)
            finally:
                if name == "second":
                    second_done.set()

        with mock.patch.object(
            lastwords,
            "generate_reply",
            side_effect=controlled_reply,
        ):
            first = threading.Thread(
                target=send,
                args=("first", first_option),
            )
            second = threading.Thread(
                target=send,
                args=("second", second_option),
            )
            first.start()
            self.assertTrue(first_is_generating.wait(timeout=5))

            state_while_generating = lastwords.api_state()
            self.assertEqual(state_while_generating["world"]["version"], 1)

            second.start()
            completed_without_release = second_done.wait(timeout=2)
            release_first.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertTrue(completed_without_release)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(responses["first"].status_code, 200)
        self.assertEqual(responses["second"].status_code, 200)
        self.assertEqual(
            lastwords.api_state()["world"]["version"],
            2,
        )
        self.assertTrue(generation_transaction_states)
        self.assertTrue(
            all(
                in_transaction is False
                for in_transaction in generation_transaction_states
            )
        )

    def test_database_busy_is_a_structured_503_not_a_raw_error(self):
        with mock.patch.object(
            lastwords,
            "_api_message",
            side_effect=lastwords.sqlite3.OperationalError(
                "database is locked"
            ),
        ):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-busy",
                )
            )

        self.assertEqual(response.status_code, 503)
        body = json.loads(response.body)
        self.assertEqual(body["code"], "database_busy")
        self.assertEqual(response.headers["retry-after"], "1")

    def test_fallback_options_are_stable_when_curated_words_are_gone(self):
        with lastwords.get_db() as conn:
            conn.executemany(
                """
                UPDATE words
                SET status='burned', burned_at=?
                WHERE word=?
                """,
                [
                    (lastwords.now_iso(), word)
                    for word in lastwords.CURATED_SACRIFICES
                ],
            )

        first = lastwords.api_state()["sacrifice_options"]
        second = lastwords.api_state()["sacrifice_options"]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertTrue(
            all(
                option["word"] not in lastwords.CURATED_SACRIFICES
                for option in first
            )
        )
        with lastwords.get_db() as conn:
            for option in first:
                row = conn.execute(
                    "SELECT status FROM words WHERE word=?",
                    (option["word"],),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["status"], "alive")

    def test_original_text_can_revive_then_resacrifice_the_same_word(self):
        option = self.first_option()
        with lastwords.get_db() as conn:
            conn.execute(
                """
                UPDATE words
                SET status='burned', burned_at=?
                WHERE word=?
                """,
                (lastwords.now_iso(), option["word"]),
            )

        with mock.patch.object(
            lastwords,
            "generate_reply",
            return_value="I am.",
        ):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text=option["word"],
                    session_id="world-revive-sacrifice",
                    sacrifice_word=option["word"],
                )
            )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.body)
        self.assertEqual(data["revived"], [option["word"]])
        self.assertEqual(data["sacrificed"]["word"], option["word"])
        self.assertNotIn(option["word"], data["burned_now"])
        with lastwords.get_db() as conn:
            row = conn.execute(
                "SELECT status, revived_count FROM words WHERE word=?",
                (option["word"],),
            ).fetchone()
            events = [
                tuple(event)
                for event in conn.execute(
                    """
                    SELECT kind, word
                    FROM events
                    WHERE word=?
                    ORDER BY id
                    """,
                    (option["word"],),
                ).fetchall()
            ]
        self.assertEqual(row["status"], "burned")
        self.assertEqual(row["revived_count"], 1)
        self.assertEqual(
            events,
            [
                ("revive", option["word"]),
                ("burn", option["word"]),
            ],
        )

    def test_deleting_final_law_persists_reply_and_silences_current_edition(self):
        self.leave_only_world_law("gravity")

        before = lastwords.api_state()
        self.assertFalse(before["silenced"])
        self.assertGreater(before["alive"], lastwords.END_THRESHOLD)
        self.assertEqual(len(before["sacrifice_options"]), 3)
        final_option = before["sacrifice_options"][0]
        self.assertEqual(final_option["law"], "gravity")

        with mock.patch.object(lastwords, "LLM_AVAILABLE", False):
            response = lastwords.api_message(
                lastwords.MessageIn(
                    text="hello",
                    session_id="world-final-law",
                    sacrifice_word=final_option["word"],
                )
            )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.body)
        self.assertTrue(data["silenced"])
        self.assertTrue(data["just_silenced"])
        self.assertEqual(data["sacrifice_options"], [])
        self.assertTrue(lastwords.world_is_erased(data["world"]))
        self.assertEqual(data["total"], before["total"])
        rendered_reply = lastwords.segments_to_text(data["segments"])
        self.assertEqual(data["poem"], rendered_reply)
        chosen = lastwords.content_tokens(data["poem"])
        self.assertGreaterEqual(len(chosen), 2)
        self.assertLessEqual(len(chosen), 3)
        self.assertTrue(
            set(chosen).issubset(
                set(lastwords.LAW_MOCK_WORDS["gravity"])
            )
        )

        ended_state = lastwords.api_state()
        self.assertTrue(ended_state["silenced"])
        self.assertEqual(ended_state["sacrifice_options"], [])
        self.assertEqual(ended_state["poem"], data["poem"])
        baseline = self.snapshot()

        frozen = lastwords.api_message(
            lastwords.MessageIn(
                text="memory returns",
                session_id="world-after-ending",
            )
        )
        self.assertEqual(frozen.status_code, 200)
        self.assertTrue(json.loads(frozen.body)["silenced"])
        self.assertEqual(self.snapshot(), baseline)

    def test_finished_world_is_archived_with_complete_immutable_artifacts(self):
        before, option, finished = self.finish_current_world(
            "world-archive-artifacts"
        )

        self.assertEqual(finished["edition"]["number"], 1)
        self.assertEqual(finished["edition"]["label"], "WORLD 001")
        self.assertEqual(finished["edition"]["status"], "silenced")
        self.assertTrue(finished["edition"]["died_at"])
        self.assertTrue(finished["edition"]["finalized_at"])
        self.assertTrue(finished["edition"]["rebirth_at"])
        self.assertGreaterEqual(
            finished["edition"]["rebirth_in_seconds"],
            0,
        )
        self.assertEqual(len(finished["archives"]), 1)
        self.assertEqual(finished["archive_count"], 1)
        self.assertEqual(
            finished["latest_archive"],
            finished["archives"][0],
        )

        detail = lastwords.api_edition(1)
        self.assertEqual(detail["label"], "WORLD 001")
        self.assertEqual(detail["status"], "archived")
        self.assertEqual(
            detail["lineage_seed"],
            lastwords.INITIAL_LINEAGE_SEED,
        )
        self.assertEqual(detail["final_poem"], finished["poem"])
        self.assertEqual(detail["world_version"], 20)
        self.assertEqual(detail["genome"], finished["world"]["genome"])
        self.assertTrue(lastwords.world_is_erased({"genome": detail["genome"]}))
        self.assertEqual(detail["total_count"], before["total"])
        self.assertEqual(detail["message_count"], 1)
        self.assertEqual(
            detail["final_message"]["segments"],
            finished["segments"],
        )
        self.assertEqual(
            detail["final_message"]["burned_now"],
            finished["burned_now"],
        )
        self.assertIn(
            option["word"],
            {item["word"] for item in detail["burned_words"]},
        )
        self.assertIn(
            ("burn", option["word"]),
            {
                (item["kind"], item["word"])
                for item in detail["graveyard"]
            },
        )

        frozen_archive = json.loads(json.dumps(detail, sort_keys=True))
        with lastwords.get_db() as conn:
            conn.execute(
                """
                UPDATE words
                SET status='alive', burned_at=NULL
                WHERE word=?
                """,
                (option["word"],),
            )
            lastwords.archive_current_edition(conn)
            archived_again = lastwords.get_world_edition(conn, 1)
        self.assertEqual(archived_again, frozen_archive)

    def test_rebirth_waits_then_resets_current_organism_without_losing_archive(self):
        _before, _option, finished = self.finish_current_world(
            "world-rebirth"
        )
        finalized_at = datetime.fromisoformat(
            finished["edition"]["finalized_at"]
        )
        if finalized_at.tzinfo is None:
            finalized_at = finalized_at.replace(tzinfo=timezone.utc)

        original_delay = lastwords.EDITION_REBIRTH_SECONDS
        lastwords.EDITION_REBIRTH_SECONDS = 60
        try:
            with lastwords.get_db() as conn:
                archived_before = lastwords.get_world_edition(conn, 1)
                self.assertFalse(
                    lastwords.maybe_birth_next_edition(
                        conn,
                        now=finalized_at + timedelta(seconds=59),
                    )
                )
                self.assertTrue(lastwords.get_ending(conn)["silenced"])

            with lastwords.get_db() as conn:
                self.assertTrue(
                    lastwords.maybe_birth_next_edition(
                        conn,
                        now=finalized_at + timedelta(seconds=61),
                    )
                )
        finally:
            lastwords.EDITION_REBIRTH_SECONDS = original_delay

        state = lastwords.api_state()
        self.assertFalse(state["silenced"])
        self.assertEqual(state["edition"]["number"], 2)
        self.assertEqual(state["edition"]["label"], "WORLD 002")
        self.assertEqual(state["edition"]["status"], "alive")
        self.assertEqual(state["world"]["edition_number"], 2)
        self.assertEqual(
            state["edition"]["lineage_seed"],
            state["world"]["lineage_seed"],
        )
        self.assertEqual(
            state["edition"]["lineage_seed"],
            lastwords.derive_lineage_seed(archived_before),
        )
        self.assertNotEqual(
            state["edition"]["lineage_seed"],
            archived_before["lineage_seed"],
        )
        self.assertEqual(state["world"]["version"], 0)
        self.assertEqual(
            state["world"]["genome"],
            lastwords.INITIAL_WORLD_GENOME,
        )
        self.assertEqual(state["alive"], state["total"])
        self.assertEqual(state["message_count"], 0)
        self.assertEqual(state["graveyard"], [])
        self.assertIsNone(state["latest_utterance"])
        self.assertEqual(len(state["archives"]), 1)
        self.assertEqual(state["archive_count"], 1)
        self.assertEqual(state["latest_archive"]["number"], 1)

        with lastwords.get_db() as conn:
            archived_after = lastwords.get_world_edition(conn, 1)
            dirty_word_count = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM words
                WHERE status!='alive'
                   OR burned_at IS NOT NULL
                   OR revived_count!=0
                """
            ).fetchone()["c"]
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM utterances"
                ).fetchone()["c"],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM sessions"
                ).fetchone()["c"],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM recent_messages"
                ).fetchone()["c"],
                0,
            )
        self.assertEqual(dirty_word_count, 0)
        self.assertEqual(archived_after, archived_before)

    def test_unfinalized_reservation_never_rebirths_or_archives(self):
        original_delay = lastwords.EDITION_REBIRTH_SECONDS
        lastwords.EDITION_REBIRTH_SECONDS = 0
        try:
            with lastwords.get_db() as conn:
                self.assertTrue(
                    lastwords.persist_reply_as_ending(
                        conn,
                        "I am.",
                        finalized=False,
                    )
                )
                self.assertFalse(
                    lastwords.maybe_birth_next_edition(
                        conn,
                        now=datetime.now(timezone.utc) + timedelta(days=1),
                    )
                )
                ending = lastwords.get_ending(conn)
                current = lastwords.get_current_edition(conn)
                archives = lastwords.list_world_editions(conn)
        finally:
            lastwords.EDITION_REBIRTH_SECONDS = original_delay

        self.assertTrue(ending["silenced"])
        self.assertIsNone(ending["finalized_at"])
        self.assertEqual(current["number"], 1)
        self.assertEqual(current["status"], "silenced")
        self.assertIsNone(current["rebirth_at"])
        self.assertEqual(archives, [])

    def test_simultaneous_rebirth_checks_create_exactly_one_new_world(self):
        self.finish_current_world("world-rebirth-race")
        original_delay = lastwords.EDITION_REBIRTH_SECONDS
        lastwords.EDITION_REBIRTH_SECONDS = 0
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def attempt_rebirth():
            try:
                barrier.wait(timeout=5)
                with lastwords.get_db() as conn:
                    results.append(lastwords.maybe_birth_next_edition(conn))
            except Exception as error:  # noqa: BLE001
                errors.append(error)

        try:
            first = threading.Thread(target=attempt_rebirth)
            second = threading.Thread(target=attempt_rebirth)
            first.start()
            second.start()
            first.join(timeout=5)
            second.join(timeout=5)
        finally:
            lastwords.EDITION_REBIRTH_SECONDS = original_delay

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [False, True])
        with lastwords.get_db() as conn:
            self.assertEqual(
                lastwords.get_world_state(conn)["edition_number"],
                2,
            )
            self.assertEqual(
                len(lastwords.list_world_editions(conn)),
                1,
            )

    def test_final_law_reservation_has_no_unburned_content_words(self):
        self.leave_only_world_law("gravity")
        final_option = lastwords.api_state()["sacrifice_options"][0]
        generation_started = threading.Event()
        release_generation = threading.Event()
        responses = []

        def slow_semantic_reply(text, conn):
            generation_started.set()
            if not release_generation.wait(timeout=5):
                raise AssertionError("final generation was not released")
            alive_words = [
                row["word"]
                for row in conn.execute(
                    "SELECT word FROM words WHERE status='alive'"
                ).fetchall()
            ]
            return lastwords.mock_reply(text, alive_words)

        def send_final_sacrifice():
            responses.append(
                lastwords.api_message(
                    lastwords.MessageIn(
                        text="hello",
                        session_id="world-final-reservation",
                        sacrifice_word=final_option["word"],
                    )
                )
            )

        with mock.patch.object(
            lastwords,
            "generate_reply",
            side_effect=slow_semantic_reply,
        ):
            request = threading.Thread(target=send_final_sacrifice)
            request.start()
            self.assertTrue(generation_started.wait(timeout=5))

            mid_state = lastwords.api_state()
            self.assertTrue(mid_state["silenced"])
            self.assertEqual(mid_state["sacrifice_options"], [])
            self.assertEqual(mid_state["poem"], "I am.")
            self.assertEqual(
                lastwords.content_tokens(mid_state["poem"]),
                [],
            )
            with lastwords.get_db() as conn:
                sacrificed_row = conn.execute(
                    "SELECT status FROM words WHERE word=?",
                    (final_option["word"],),
                ).fetchone()
            self.assertEqual(sacrificed_row["status"], "burned")

            frozen_baseline = self.snapshot()
            frozen = lastwords.api_message(
                lastwords.MessageIn(
                    text="memory returns",
                    session_id="world-final-reservation-frozen",
                )
            )
            self.assertEqual(frozen.status_code, 200)
            self.assertTrue(json.loads(frozen.body)["silenced"])
            self.assertEqual(self.snapshot(), frozen_baseline)

            release_generation.set()
            request.join(timeout=5)

        self.assertFalse(request.is_alive())
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].status_code, 200)
        completed = json.loads(responses[0].body)
        self.assertTrue(completed["silenced"])
        self.assertNotEqual(completed["poem"], "I am.")
        self.assertEqual(
            completed["poem"],
            lastwords.segments_to_text(completed["segments"]),
        )

    def test_pipeline_without_sacrifice_remains_backward_compatible(self):
        with lastwords.get_db() as conn:
            total_before = lastwords.counts(conn)[1]
            with mock.patch.object(
                lastwords,
                "generate_reply",
                return_value="I am.",
            ):
                result = lastwords.run_pipeline(conn, "hello")
            total_after = lastwords.counts(conn)[1]

        self.assertIsNone(result["sacrificed"])
        self.assertEqual(result["world"]["version"], 0)
        self.assertEqual(result["world"]["build_status"], "pending")
        self.assertIsNone(result["world"]["build_ms"])
        self.assertEqual(total_before, total_after)


if __name__ == "__main__":
    unittest.main()
