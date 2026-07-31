import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (PROJECT_ROOT / "static" / "index.html").read_text(
    encoding="utf-8"
)
APP_JS = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")


class FirstScreenClarityTests(unittest.TestCase):
    def test_first_screen_states_the_complete_interaction_in_plain_language(self):
        self.assertIn(
            "20 abilities keep this creature alive.",
            INDEX_HTML,
        )
        self.assertIn(
            "To talk to it, take one away.",
            INDEX_HTML,
        )
        self.assertIn(
            "When none remain, it dies.",
            INDEX_HTML,
        )
        self.assertIn("choose what it loses", INDEX_HTML)

    def test_artwork_is_not_covered_by_the_explainer_on_arrival(self):
        explainer = re.search(
            r'<section id="work-explainer"(?P<attrs>[^>]*)>',
            INDEX_HTML,
        )
        self.assertIsNotNone(explainer)
        attrs = explainer.group("attrs")
        self.assertIn("hidden", attrs)
        self.assertIn('aria-hidden="true"', attrs)
        self.assertIn('aria-expanded="false"', INDEX_HTML)
        self.assertIn("setExplainerOpen(false);", APP_JS)

    def test_primary_choice_copy_does_not_lead_with_internal_law_names(self):
        self.assertIn(
            'consequence.textContent = "IF YOU TAKE THIS AWAY:";',
            APP_JS,
        )
        self.assertIn(
            "option.consequence ||",
            APP_JS,
        )
        self.assertIn(
            "sendButton.textContent = `take ${option.word} & ask`;",
            APP_JS,
        )
        self.assertNotIn(
            "sendButton.textContent = `erase ${law} & ask`;",
            APP_JS,
        )

    def test_cache_busting_assets_share_the_same_release_version(self):
        versions = re.findall(
            r'/(?:style\.css|world\.js|app\.js)\?v=([^"]+)',
            INDEX_HTML,
        )
        self.assertEqual(versions, ["world-clear-v8"] * 3)


if __name__ == "__main__":
    unittest.main()
