import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from corpus import cli, report, scan, sim, status  # noqa: E402

DAY = 86400


def mk(path, text, mtime=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if mtime:
        os.utime(path, (mtime, mtime))


class ScanTests(unittest.TestCase):
    def test_never_existing_example_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "README.md"),
               "# P\n\nPut your file at `src/foo.py`.\n")
            result = report.analyze(tmp)
            self.assertFalse([f for f in result["findings"]
                              if f["kind"] == "missing-ref"], result["findings"])

    def test_scaffold_templates_are_not_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "docs", "story", "chapters", "_template.md"),
               "---\nid: ch-01\n---\n")
            mk(os.path.join(tmp, "README.md"), "# P\n")
            paths = set(scan.scan(tmp)["artifacts"])
            self.assertIn("README.md", paths)
            self.assertNotIn("docs/story/chapters/_template.md", paths,
                             "lifecycle's pack scaffold is not a document")

    def test_title_kind_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "docs", "guide.md"),
               "# The guide\n\nSee [api](api.md) and [site](https://example.com).\n")
            mk(os.path.join(tmp, "docs", "api.md"), "# API\n\nUses `src/app.py`.\n")
            mk(os.path.join(tmp, "README.md"), "# Project\n\n[docs](docs/guide.md)\n")
            index = scan.scan(tmp)
            arts = index["artifacts"]
            self.assertEqual(arts["docs/guide.md"]["title"], "The guide")
            self.assertEqual(arts["docs/guide.md"]["kind"], "doc")
            self.assertEqual(arts["README.md"]["kind"], "readme")
            self.assertEqual(arts["docs/guide.md"]["links_out"], ["docs/api.md"])
            self.assertEqual(arts["docs/api.md"]["refs"], ["src/app.py"])
            back = scan.inbound(index)
            self.assertEqual(back["docs/api.md"], ["docs/guide.md"])
            self.assertEqual(back["docs/guide.md"], ["README.md"])

    def test_ignored_dirs_and_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "node_modules", "x", "README.md"), "# no\n")
            mk(os.path.join(tmp, "LICENSE"), "MIT\n")
            mk(os.path.join(tmp, "a.md"), "# a\n")
            self.assertEqual(sorted(scan.scan(tmp)["artifacts"]), ["a.md"])

    def test_dot_directories_are_not_mangled(self):
        """Regression: lstrip('./') turned '.projtruth/x.json' into 'projtruth/x.json'."""
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, ".projtruth", "requirements.json"), "{}")
            mk(os.path.join(tmp, "doc.md"), "# d\n\nSee `.projtruth/requirements.json`.\n")
            refs = scan.scan(tmp)["artifacts"]["doc.md"]["refs"]
            self.assertEqual(refs, [".projtruth/requirements.json"])

    def test_scratch_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "tmp-notes.md"), "# t\n")
            mk(os.path.join(tmp, "draft-plan.md"), "# p\n")
            mk(os.path.join(tmp, "notes.md"), "# n\n")
            mk(os.path.join(tmp, "real.md"), "# r\n")
            arts = scan.scan(tmp)["artifacts"]
            self.assertTrue(arts["tmp-notes.md"]["scratch"])
            self.assertTrue(arts["draft-plan.md"]["scratch"])
            self.assertFalse(arts["real.md"]["scratch"])
            self.assertFalse(arts["notes.md"]["scratch"])


class SimTests(unittest.TestCase):
    def test_near_duplicates_found(self):
        para = ("A cache stores responses so repeated requests do not reach the origin. "
                "It expires entries after one minute and never serves a stale body. ") * 8
        docs = {"a.md": para,
                "b.md": para + "One extra closing sentence here.",
                "c.md": "An unrelated document about database migrations and indexes. " * 8}
        pairs = sim.near_duplicates(docs, threshold=0.7)
        self.assertEqual(len(pairs), 1, pairs)
        self.assertIn("a.md", pairs[0])
        self.assertIn("b.md", pairs[0])

    def test_cjk_query_terms(self):
        self.assertIn("发布", sim.terms("如何发布技能"))
        self.assertGreater(sim.score_against("发布技能", "这里讲如何发布技能到市场"), 0.9)
        self.assertLess(sim.score_against("发布技能", "完全无关的文本内容"), 0.2)


class ReportTests(unittest.TestCase):
    def _repo(self, tmp):
        return os.path.abspath(tmp)

    def test_exact_duplicate_is_incorrect(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "# Same\n\n" + "text\n" * 50
            mk(os.path.join(tmp, "a.md"), body)
            mk(os.path.join(tmp, "b.md"), body)
            res = report.analyze(tmp)
            kinds = [(f["kind"], f["severity"]) for f in res["findings"]]
            self.assertIn(("duplicate-exact", report.INCORRECT), kinds)

    def test_broken_link_severity_depends_on_doc_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "README.md"), "# P\n\n[gone](missing.md)\n")
            mk(os.path.join(tmp, "research", "note.md"), "# N\n\n[gone](missing.md)\n")
            res = report.analyze(tmp)
            by_path = dict((f["path"], f) for f in res["findings"] if f["kind"] == "broken-link")
            self.assertEqual(by_path["README.md"]["severity"], report.INCORRECT)
            self.assertEqual(by_path["research/note.md"]["severity"], report.NOISE)

    def test_stale_respects_grace_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = time.time()
            mk(os.path.join(tmp, "code.py"), "x = 1\n", mtime=now)
            mk(os.path.join(tmp, "doc.md"), "# D\n\nCalls `code.py`.\n", mtime=now - 3 * DAY)
            fresh = report.analyze(tmp, stale_days=7)
            self.assertFalse([f for f in fresh["findings"] if f["kind"] == "stale"])
            old = report.analyze(tmp, stale_days=1)
            self.assertTrue([f for f in old["findings"] if f["kind"] == "stale"])

    def test_orphan_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "README.md"), "# P\n\n[listed](listed.md)\n")
            mk(os.path.join(tmp, "listed.md"), "# listed\n")
            mk(os.path.join(tmp, "lonely.md"), "# lonely\n")
            res = report.analyze(tmp)
            orphans = [f["path"] for f in res["findings"] if f["kind"] == "orphan"]
            self.assertIn("lonely.md", orphans)
            self.assertNotIn("listed.md", orphans)
            self.assertNotIn("README.md", orphans)

    def test_links_to_retired_is_incorrect(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "a.md"), "# A\n\n[old](old.md)\n")
            mk(os.path.join(tmp, "old.md"), "# Old\n\nobsolete\n")
            mk(os.path.join(tmp, "new.md"), "# New\n\nreplacement\n")
            status.set_status(tmp, "old.md", "superseded", by="new.md")
            res = report.analyze(tmp)
            kinds = [(f["kind"], f["severity"]) for f in res["findings"]]
            self.assertIn(("links-retired", report.INCORRECT), kinds)

    def test_directory_without_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(8):
                mk(os.path.join(tmp, "docs", "d%d.md" % i), "# d%d\n" % i)
            res = report.analyze(tmp)
            self.assertTrue([f for f in res["findings"] if f["kind"] == "no-index"])

    def test_metrics_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "a.md"), "# a\n")
            m = report.metrics(report.analyze(tmp))
            self.assertEqual(m["artifacts"], 1)
            self.assertIn("severity", m)
            self.assertIn("reading_tokens", m)


class StatusTests(unittest.TestCase):
    def test_supersede_archive_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "old.md"), "# o\n")
            mk(os.path.join(tmp, "new.md"), "# n\n")
            ok, _ = status.set_status(tmp, "old.md", "superseded", by="new.md")
            self.assertTrue(ok)
            self.assertEqual(status.status_of(status.load(tmp), "old.md"), "superseded")
            self.assertTrue(status.clear(tmp, "old.md")[0])
            self.assertEqual(status.status_of(status.load(tmp), "old.md"), "active")
            self.assertFalse(status.set_status(tmp, "old.md", "bogus")[0])


class GateTests(unittest.TestCase):
    def test_check_fails_on_incorrect_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "README.md"), "# P\n\n[gone](missing.md)\n")
            self.assertEqual(cli.main(["--repo", tmp, "check"]), 1)
            self.assertEqual(cli.main(["--repo", tmp, "check", "--strict"]), 1)

    def test_check_passes_with_only_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "START.md"), "# s\n")
            mk(os.path.join(tmp, "lonely.md"), "# l\n")
            self.assertEqual(cli.main(["--repo", tmp, "check"]), 0)

    def test_strict_gates_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = time.time()
            mk(os.path.join(tmp, "code.py"), "x\n", mtime=now)
            mk(os.path.join(tmp, "doc.md"), "# D\n\n`code.py`\n", mtime=now - 30 * DAY)
            self.assertEqual(cli.main(["--repo", tmp, "check", "--stale-days", "7"]), 0)
            self.assertEqual(cli.main(["--repo", tmp, "check", "--strict",
                                       "--stale-days", "7"]), 1)


class MissingRefTests(unittest.TestCase):
    GIT = shutil.which("git")

    def _git(self, tmp, *args):
        subprocess.run([self.GIT, "-C", tmp] + list(args), check=True,
                       capture_output=True, text=True)

    @unittest.skipUnless(GIT, "git not installed")
    def test_a_deleted_file_still_named_is_incorrect(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._git(tmp, "init", "-q")
            self._git(tmp, "config", "user.email", "t@example.com")
            self._git(tmp, "config", "user.name", "t")
            mk(os.path.join(tmp, "src", "app.py"), "x = 1\n")
            self._git(tmp, "add", "-A")
            self._git(tmp, "commit", "-qm", "add")
            self._git(tmp, "rm", "-q", "src/app.py")
            self._git(tmp, "commit", "-qm", "remove")
            mk(os.path.join(tmp, "README.md"), "# P\n\nSee `src/app.py`.\n")
            result = report.analyze(tmp)
            hits = [f for f in result["findings"] if f["kind"] == "missing-ref"]
            self.assertTrue(hits, result["findings"])
            self.assertEqual(hits[0]["severity"], report.INCORRECT)
            self.assertIn("src/app.py", hits[0]["detail"])


class CliTests(unittest.TestCase):
    def test_find_and_dupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "# Cache\n\n" + "requests are cached for a minute\n" * 40
            mk(os.path.join(tmp, "cache.md"), body)
            mk(os.path.join(tmp, "cache2.md"), body)
            self.assertEqual(cli.main(["--repo", tmp, "find", "caching requests"]), 0)
            self.assertEqual(cli.main(["--repo", tmp, "dupes"]), 0)

    def test_scan_writes_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "a.md"), "# a\n")
            self.assertEqual(cli.main(["--repo", tmp, "scan"]), 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, ".corpus", "index.json")))


if __name__ == "__main__":
    unittest.main()
