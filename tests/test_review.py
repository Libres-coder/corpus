"""Regressions from the first independent review of corpus 0.1.0."""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from corpus import cli, report, scan, status  # noqa: E402


def mk(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class LinkParsingTests(unittest.TestCase):
    def test_link_title_and_encoded_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "my file.md"), "# f\n")
            mk(os.path.join(tmp, "README.md"),
               '# P\n\n[a](my%20file.md) and [b](my file.md "the title")\n')
            res = report.analyze(tmp)
            self.assertFalse([f for f in res["findings"] if f["kind"] == "broken-link"])

    def test_reference_style_and_html_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "a.md"), "# A\n\n[x][ref]\n\n[ref]: b.md\n")
            mk(os.path.join(tmp, "h.md"), '# H\n\n<a href="c.md">c</a>\n')
            mk(os.path.join(tmp, "b.md"), "# B\n")
            mk(os.path.join(tmp, "c.md"), "# C\n")
            back = scan.inbound(scan.scan(tmp))
            self.assertEqual(back["b.md"], ["a.md"])
            self.assertEqual(back["c.md"], ["h.md"])

    def test_inline_code_is_not_a_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "README.md"), "# P\n\nWrite `[x](missing.md)` like that.\n")
            res = report.analyze(tmp)
            self.assertFalse([f for f in res["findings"] if f["kind"] == "broken-link"])

    def test_links_outside_the_repo_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "README.md"), "# P\n\n[x](../other/x.md)\n")
            self.assertEqual(scan.scan(tmp)["artifacts"]["README.md"]["links_out"], [])

    def test_cjk_backticked_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "doc.md"), "# D\n\nSee `文档/说明.md`.\n")
            mk(os.path.join(tmp, "文档", "说明.md"), "# S\n")
            self.assertEqual(scan.scan(tmp)["artifacts"]["doc.md"]["refs"],
                             ["文档/说明.md"])

    def test_symlinked_copy_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "# Same\n\n" + "text\n" * 40
            mk(os.path.join(tmp, "AGENTS.md"), body)
            try:
                os.symlink(os.path.join(tmp, "AGENTS.md"),
                           os.path.join(tmp, "CLAUDE.md"))
            except (OSError, NotImplementedError, AttributeError):
                self.skipTest("symlinks not available")
            self.assertEqual(sorted(scan.scan(tmp)["artifacts"]), ["AGENTS.md"])


class StatusRobustnessTests(unittest.TestCase):
    def test_status_tolerates_hand_edited_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, ".corpus", "status.json"),
               '{"paths": {"a.md": "archived", "b.md": {"at": "x"},'
               ' "c.md": {"status": "archived"}}}')
            data = status.load(tmp)
            self.assertEqual(sorted(data["paths"]), ["c.md"])
            self.assertEqual(status.status_of(data, "a.md"), "active")

    def test_status_keeps_dotted_paths_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, ".github", "x.md"), "# x\n")
            status.set_status(tmp, ".github/x.md", "archived")
            self.assertIn(".github/x.md", status.load(tmp)["paths"])


class CliContractTests(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = cli.main(argv)
        finally:
            sys.stdout = old
        return rc, buf.getvalue()

    def test_repo_must_be_a_directory(self):
        self.assertEqual(cli.main(["--repo", "no-such-dir-xyz", "check"]), 2)

    def test_glob_is_additive(self):
        with tempfile.TemporaryDirectory() as tmp:
            mk(os.path.join(tmp, "a.md"), "# a\n")
            mk(os.path.join(tmp, "b.mdx"), "# b\n")
            index = scan.scan(tmp, ["**/*.md", "**/*.mdx"])
            self.assertEqual(sorted(index["artifacts"]), ["a.md", "b.mdx"])
            self.assertEqual(cli.main(["--repo", tmp, "--glob", "**/*.mdx", "scan"]), 0)
            res = report.analyze(tmp, globs=["**/*.md", "**/*.mdx"])
            self.assertEqual(len(res["index"]["artifacts"]), 2)

    def test_find_skips_retired_when_an_active_match_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "# Deployment\n\n" + "deploy to staging with the script\n" * 20
            mk(os.path.join(tmp, "old.md"), body)
            mk(os.path.join(tmp, "new.md"), body)
            status.set_status(tmp, "old.md", "superseded", by="new.md")
            rc, out = self._run(["--repo", tmp, "find", "deploy to staging"])
            self.assertEqual(rc, 0)
            self.assertIn("new.md", out)
            self.assertNotIn("old.md", out)

    def test_dupes_names_the_copy_to_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "# Same\n\n" + "shared paragraph of text\n" * 30
            mk(os.path.join(tmp, "keep.md"), body)
            mk(os.path.join(tmp, "copy.md"), body)
            rc, out = self._run(["--repo", tmp, "dupes"])
            self.assertEqual(rc, 0)
            self.assertIn("keep", out)
            self.assertIn("archive", out)


if __name__ == "__main__":
    unittest.main()
