from __future__ import annotations

import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from era_cli import main as cli_main
from era_integrations.inbox_publish import (
    MAX_STORE_BYTES,
    PublishResult,
    publish_export,
    resolve_inbox,
)
from tests.test_eval_validation import ValidationBase


def make_inbox(root: Path, mode: int = 0o700) -> Path:
    inbox = root / "era-inbox"
    inbox.mkdir(mode=mode)
    os.chmod(inbox, mode)
    return inbox


class PublishTests(ValidationBase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_dir = self.make_runs()[1]

    def env(self, inbox: Path) -> dict[str, str]:
        return {"DFL_ERA_DROP_DIR": str(inbox)}

    def test_location_default_and_override(self) -> None:
        self.assertEqual(resolve_inbox({}), Path("~/.dataforge-local/era-inbox").expanduser())
        self.assertEqual(resolve_inbox({"DFL_ERA_DROP_DIR": "/x/y"}), Path("/x/y"))

    def test_publishes_the_exact_export_by_rename(self) -> None:
        inbox = make_inbox(self.root)
        result = publish_export(self.run_dir, self.env(inbox))
        self.assertEqual((result.status, result.reason), ("published", "published"))
        published = inbox / f"era_evaluation_export.{self.run_dir.name}.json"
        self.assertEqual(result.path, str(published))
        self.assertEqual(published.read_bytes(), (self.run_dir / "evaluation_export.json").read_bytes())
        self.assertEqual(stat.S_IMODE(published.stat().st_mode), 0o600)
        self.assertEqual([p.name for p in inbox.iterdir()], [published.name])  # no temporary file is left

    def test_the_temporary_name_is_one_the_consumer_ignores(self) -> None:
        inbox = make_inbox(self.root)
        seen = []
        real_replace = os.replace

        def spy(source, target):
            seen.append(Path(source).name)
            return real_replace(source, target)

        with mock.patch("os.replace", spy):
            publish_export(self.run_dir, self.env(inbox))
        self.assertTrue(seen[0].startswith(".") and seen[0].endswith(".tmp"))

    def test_republishing_the_same_run_is_idempotent(self) -> None:
        inbox = make_inbox(self.root)
        first = publish_export(self.run_dir, self.env(inbox))
        second = publish_export(self.run_dir, self.env(inbox))
        self.assertEqual((first.path, second.path, second.status), (second.path, first.path, "published"))
        self.assertEqual(len(list(inbox.iterdir())), 1)

    def test_a_missing_inbox_is_never_created(self) -> None:
        inbox = self.root / "not-there"
        result = publish_export(self.run_dir, self.env(inbox))
        self.assertEqual(result.status, "skipped")
        self.assertIn("inbox_missing", result.reason)
        self.assertFalse(inbox.exists())

    def test_an_unsafe_inbox_is_skipped(self) -> None:
        for mode in (0o770, 0o707, 0o777):
            with self.subTest(mode=oct(mode)):
                inbox = self.root / f"unsafe-{mode:o}"
                inbox.mkdir()
                os.chmod(inbox, mode)
                result = publish_export(self.run_dir, self.env(inbox))
                self.assertEqual(result.status, "skipped")
                self.assertIn("writable", result.reason)
                self.assertEqual(list(inbox.iterdir()), [])

    def test_a_symlinked_or_non_directory_inbox_is_skipped(self) -> None:
        real = make_inbox(self.root)
        link = self.root / "link"
        link.symlink_to(real)
        self.assertIn("symlink", publish_export(self.run_dir, self.env(link)).reason)
        file_path = self.root / "afile"
        file_path.write_text("x")
        self.assertIn("not a directory", publish_export(self.run_dir, self.env(file_path)).reason)
        self.assertEqual(list(real.iterdir()), [])

    def test_a_foreign_owner_is_skipped(self) -> None:
        inbox = make_inbox(self.root)
        with mock.patch("os.getuid", return_value=os.getuid() + 1):
            result = publish_export(self.run_dir, self.env(inbox))
        self.assertIn("owned by another user", result.reason)

    def test_a_run_without_an_export_publishes_nothing(self) -> None:
        inbox = make_inbox(self.root)
        (self.run_dir / "evaluation_export.json").unlink()
        self.assertIn("no_export", publish_export(self.run_dir, self.env(inbox)).reason)
        self.assertEqual(list(inbox.iterdir()), [])

    def test_a_file_that_is_not_the_admitted_family_is_skipped(self) -> None:
        inbox = make_inbox(self.root)
        path = self.run_dir / "evaluation_export.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for change, needle in (({"artifact_family": "other"}, "wrong_family"),):
            path.write_text(json.dumps({**data, **change}), encoding="utf-8")
            self.assertIn(needle, publish_export(self.run_dir, self.env(inbox)).reason)
        path.write_text("{nope", encoding="utf-8")
        self.assertIn("export_unreadable", publish_export(self.run_dir, self.env(inbox)).reason)
        self.assertEqual(list(inbox.iterdir()), [])

    def test_an_export_over_the_store_limit_is_skipped_visibly(self) -> None:
        inbox = make_inbox(self.root)
        path = self.run_dir / "evaluation_export.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["payload"]["pad"] = "x" * MAX_STORE_BYTES
        path.write_text(json.dumps(data), encoding="utf-8")
        result = publish_export(self.run_dir, self.env(inbox))
        self.assertIn("export_too_large", result.reason)
        self.assertEqual(list(inbox.iterdir()), [])

    def test_a_write_failure_is_reported_and_leaves_no_temporary_file(self) -> None:
        inbox = make_inbox(self.root)
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            result = publish_export(self.run_dir, self.env(inbox))
        self.assertEqual(result.status, "skipped")
        self.assertIn("write_failed", result.reason)
        self.assertEqual(list(inbox.iterdir()), [])

    def test_the_outcome_is_recorded_next_to_the_run_outside_the_hash_chain(self) -> None:
        inbox = make_inbox(self.root)
        publish_export(self.run_dir, self.env(inbox))
        receipt = json.loads((self.run_dir / "publish_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "published")
        from era_core.validation import validate_run_dir

        self.assertTrue(validate_run_dir(self.run_dir)["ok"])  # the receipt does not disturb validation
        hashes = json.loads((self.run_dir / "hashes.json").read_text(encoding="utf-8"))
        self.assertNotIn("publish_receipt.json", [e["path"] for e in hashes["entries"]])

    def test_the_line_is_readable(self) -> None:
        self.assertTrue(PublishResult("skipped", "inbox_missing: x").line().startswith("era export skipped: inbox_missing"))


class CliTests(unittest.TestCase):
    """The command publishes by default and stays quiet on stdout, so scripts that read the run path keep working."""

    def run_cli(self, inbox: Path | None, *extra: str):
        from tests.test_artifact_generation import init_git_repo
        from tests.test_eval_lane import write_quality, write_v2_manifest

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        era_root, repo = root / "era", root / "repo"
        era_root.mkdir()
        repo.mkdir()
        init_git_repo(repo)
        write_quality(repo, 0.95)
        write_v2_manifest(era_root, repo.name)
        parser_args = ["run", "--repo", str(repo), "--lanes", "efficiency", "--mode", "full", "--trusted-target",
                       "--no-sandbox", "--artifacts-root", str(era_root / "artifacts" / "era-runs"), *extra]
        env = {"DFL_ERA_DROP_DIR": str(inbox)} if inbox else {}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out), redirect_stderr(err):
            code = cli_main.main(parser_args)
        return code, out.getvalue(), err.getvalue(), era_root

    def test_default_publishes_and_reports_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            inbox = make_inbox(Path(temp))
            code, out, err, era_root = self.run_cli(inbox)
            self.assertEqual(code, 0)
            self.assertEqual(len(out.strip().splitlines()), 1)  # stdout is still just the run path
            self.assertIn("era export published", err)
            self.assertEqual(len(list(inbox.iterdir())), 1)

    def test_no_publish_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            inbox = make_inbox(Path(temp))
            code, _, err, _ = self.run_cli(inbox, "--no-publish")
            self.assertEqual(code, 0)
            self.assertNotIn("era export", err)
            self.assertEqual(list(inbox.iterdir()), [])

    def test_a_missing_inbox_does_not_fail_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            code, out, err, _ = self.run_cli(Path(temp) / "absent")
            self.assertEqual(code, 0)
            self.assertIn("inbox_missing", err)
            self.assertTrue(out.strip())

    def test_the_test_session_never_reaches_a_real_inbox(self) -> None:
        self.assertNotEqual(resolve_inbox(), Path("~/.dataforge-local/era-inbox").expanduser())
        self.assertFalse(resolve_inbox().exists())


if __name__ == "__main__":
    unittest.main()
