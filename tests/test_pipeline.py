"""Run: python3 -m unittest -v   (no keys, no network)"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ["HH_DB"] = str(Path(tempfile.mkdtemp()) / "t.sqlite")

from hh import classify, draft  # noqa: E402
from hh.cli import main  # noqa: E402


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main(["demo"])
        cls.con = sqlite3.connect(os.environ["HH_DB"])
        cls.con.row_factory = sqlite3.Row

    def acct(self, dom):
        return self.con.execute("SELECT * FROM accounts WHERE domain=?", (dom,)).fetchone()

    def test_team_signal_needs_three_people(self):
        # Northpine has only 2 applicants from one team: the signal must not exist at all
        n = self.con.execute("SELECT COUNT(*) FROM company_signals WHERE domain='northpine.example'").fetchone()[0]
        self.assertEqual(n, 0)
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM company_signals WHERE domain='brightloop.example' AND signal='team_exits'").fetchone())

    def test_private_only_account_is_held(self):
        # Corvid has a private signal but no public fact: never emailed
        self.assertEqual(self.acct("corvid.example")["status"], "hold")
        self.assertIsNone(self.con.execute("SELECT 1 FROM drafts WHERE domain='corvid.example'").fetchone())

    def test_spike_waits(self):
        a = self.acct("quillstack.example")
        self.assertEqual(a["play"], "spike_wait")
        self.assertGreater(a["send_after"], "2026-12-15")

    def test_icp_filters(self):
        self.assertLess(self.acct("tessellate.example")["fit"], 0.1)   # 900 people
        self.assertEqual(self.acct("corti.ai")["fit"], 0.0)              # Denmark
        self.assertEqual(self.acct("ginastechjobs.com")["fit"], 0.0)     # staffing

    def test_offshore_post_ranks_high(self):
        # TechnologyAdvice posted an SDR role as "Philippines, Remote": signal 1, in public
        top = [r[0] for r in self.con.execute("SELECT domain FROM accounts ORDER BY score DESC LIMIT 10")]
        self.assertIn("technologyadvice.com", top)
        self.assertEqual(self.acct("technologyadvice.com")["top_signal"], "offshore_post")

    def test_no_draft_leaks_private_data(self):
        for d in self.con.execute("SELECT * FROM drafts"):
            self.assertEqual(d["lint"], "ok", d["domain"])
            self.assertNotRegex(d["body"], r"(?i)resume|leaving|South Africa|Argentina|Deel")

    def test_first_email_under_90_words_no_links(self):
        for d in self.con.execute("SELECT body FROM drafts WHERE step=0"):
            self.assertLessEqual(len(d["body"].split()), 90)
            self.assertNotRegex(d["body"], r"https?://")

    def test_repeat_applicants_dropped(self):
        hashes = [r[0] for r in self.con.execute("SELECT applicant_hash FROM applications")]
        self.assertGreater(len(hashes), 0)


class Units(unittest.TestCase):
    def test_bucket_order(self):
        self.assertEqual(classify.bucket("Engineering Manager, Growth"), "Engineering")
        self.assertEqual(classify.bucket("SDR"), "GTM")

    def test_offshore_location(self):
        self.assertEqual(classify.location_flags("Philippines, Remote")[2], "philippines")

    def test_lint_catches_leak(self):
        self.assertTrue(draft.lint("Hi Sam, heard Priya is leaving your team", 0, []))
        self.assertFalse(draft.lint("Hi Sam, saw Applied Compute has an AE role open", 0, [], "Applied Compute"))


if __name__ == "__main__":
    unittest.main()
