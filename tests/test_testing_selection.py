"""Selection over a small repository: what runs, what is skipped, and why."""

import io
import subprocess
import textwrap

import pytest

from fantasy_engine.testing.runner import Runner
from fantasy_engine.testing.store import Store
from fantasy_engine.testing.suites import PytestRepo

TESTS = {
    "test_a.py": """
        def test_a():
            assert open("data/a.txt").read() in ("a", "a2")
    """,
    "test_b.py": """
        def test_b():
            assert open("data/b.txt").read() == "b"
    """,
    "test_c.py": """
        import demo_shadowed_helper

        def test_c():
            assert demo_shadowed_helper.VALUE in ("first", "second")
    """,
    "test_d.py": """
        import subprocess

        def test_d():
            subprocess.run(["true"], check=True)
    """,
    "test_e.py": """
        import os

        def test_e():
            # os.path.exists raises no audit event, so this read goes unrecorded.
            assert not os.path.exists("data/flag")
    """,
}


class DemoRepo(PytestRepo):
    name = "demo"

    def __init__(self, root, entries):
        super().__init__(root)
        self.entries = entries

    def pythonpath(self):
        return self.entries


@pytest.fixture
def demo(tmp_path):
    root = tmp_path / "demo"
    (root / "tests").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "data" / "a.txt").write_text("a")
    (root / "data" / "b.txt").write_text("b")
    first, second = root / "first", root / "second"
    first.mkdir()
    second.mkdir()
    (second / "demo_shadowed_helper.py").write_text("VALUE = 'second'\n")
    for name, source in TESTS.items():
        (root / "tests" / name).write_text(textwrap.dedent(source))
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "demo"], check=True)
    return DemoRepo(root, [first, second])


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "store" / "records.sqlite3")
    yield store
    store.close()


def run(repo, store, tmp_path, units=None, **options):
    out = io.StringIO()
    runner = Runner(store, repos=[repo], out=out, scratch=tmp_path / "scratch",
                    partial_root=tmp_path / "partial")
    summary = runner.run(repo.units() if units is None else units, **options)
    lines = out.getvalue().splitlines()
    ran = sorted(line.split()[1].split(":", 1)[1] for line in lines
                 if line.startswith(("RUN ", "RUN?")))
    return summary, ran, out.getvalue()


def test_only_units_whose_inputs_changed_run_again(demo, store, tmp_path):
    every = ["tests/%s" % name for name in sorted(TESTS)]
    summary, ran, _ = run(demo, store, tmp_path)
    assert ran == every and not summary.failed

    # test_d starts a program whose reads go unrecorded, so it always runs.
    summary, ran, text = run(demo, store, tmp_path)
    assert ran == ["tests/test_d.py"]
    assert summary.skipped == 4
    assert "SKIP  demo:tests/test_a.py  unchanged since" in text

    (demo.root / "data" / "a.txt").write_text("a2")
    _, ran, text = run(demo, store, tmp_path)
    assert ran == ["tests/test_a.py", "tests/test_d.py"]
    assert "changed: %s" % (demo.root / "data" / "a.txt") in text

    # A module that would now shadow an import reruns the importing unit.
    (demo.root / "first" / "demo_shadowed_helper.py").write_text("VALUE = 'first'\n")
    _, ran, text = run(demo, store, tmp_path)
    assert ran == ["tests/test_c.py", "tests/test_d.py"]
    assert "imports in %s" % (demo.root / "first") in text


def test_a_full_run_finds_an_input_the_recording_missed(demo, store, tmp_path):
    run(demo, store, tmp_path)
    (demo.root / "data" / "flag").write_text("")
    summary, ran, _ = run(demo, store, tmp_path)
    assert ran == ["tests/test_d.py"]  # test_e is wrongly skipped
    summary, ran, text = run(demo, store, tmp_path, full=True)
    assert len(ran) == len(TESTS)
    assert summary.missed == ["demo:tests/test_e.py"]
    assert "MISSED INPUT" in text


def test_failing_units_run_until_they_pass_again(demo, store, tmp_path):
    run(demo, store, tmp_path)
    (demo.root / "data" / "b.txt").write_text("broken")
    for _ in range(2):
        summary, ran, _ = run(demo, store, tmp_path)
        assert "tests/test_b.py" in ran
        assert summary.failed == ["demo:tests/test_b.py"]
    (demo.root / "data" / "b.txt").write_text("b")
    _, ran, _ = run(demo, store, tmp_path)
    assert ran == ["tests/test_d.py"]  # back to the inputs of its last pass


def test_launch_settings_belong_to_the_key(demo, store, tmp_path, monkeypatch):
    run(demo, store, tmp_path)
    monkeypatch.setenv("MP64_DEMO_SETTING", "1")
    _, ran, text = run(demo, store, tmp_path)
    assert len(ran) == len(TESTS)
    assert "its launch settings changed" in text


def test_a_dry_run_reports_without_running(demo, store, tmp_path):
    run(demo, store, tmp_path)
    before = store.latest("demo:tests/test_b.py").run_id
    (demo.root / "data" / "b.txt").write_text("broken")
    _, ran, text = run(demo, store, tmp_path, dry_run=True)
    assert ran == ["tests/test_b.py", "tests/test_d.py"]
    assert "RUN?  demo:tests/test_b.py  changed:" in text
    assert store.latest("demo:tests/test_b.py").run_id == before


RESUMABLE = """
    import os

    def _ran(name):
        with open(%r, "a") as log:
            log.write(name + "\\n")

    def test_one():
        _ran("one")
        assert open("data/a.txt").read() in ("a", "a2")

    def test_two():
        _ran("two")

    def test_three():
        _ran("three")
        assert not os.path.exists(%r)
"""


def interrupted_after_its_unit(monkeypatch):
    """The session ends right after the unit's process does."""
    real = Runner.execute

    def execute(self, launch, env, log_path, pid_path=None):
        real(self, launch, env, log_path, pid_path=pid_path)
        raise KeyboardInterrupt

    monkeypatch.setattr(Runner, "execute", execute)


@pytest.fixture
def resumable(demo, tmp_path):
    # The log and the flag sit beside the store, whose folder the recording
    # leaves out, so neither counts as an input of the unit.
    flag = tmp_path / "store" / "fail-three"
    ran = tmp_path / "store" / "ran.log"
    (demo.root / "tests" / "test_r.py").write_text(
        textwrap.dedent(RESUMABLE % (str(ran), str(flag))))
    git = ["git", "-C", str(demo.root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "resumable"], check=True)
    unit = [u for u in demo.units() if u.name == "tests/test_r.py"]
    return unit, flag, ran


def test_an_interrupted_unit_resumes_after_its_passed_tests(
        demo, store, tmp_path, monkeypatch, resumable):
    unit, flag, ran = resumable
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("")
    with monkeypatch.context() as patch:
        interrupted_after_its_unit(patch)
        with pytest.raises(KeyboardInterrupt):
            run(demo, store, tmp_path, units=unit)
    assert ran.read_text().split() == ["one", "two", "three"]

    flag.unlink()
    summary, _, text = run(demo, store, tmp_path, units=unit, dry_run=True)
    assert "resumes after 2 passed tests" in text
    summary, _, text = run(demo, store, tmp_path, units=unit)
    assert ran.read_text().split() == ["one", "two", "three", "three"]
    assert "passed" in text and "resumed after 2 passed tests" in text
    assert not summary.failed
    assert not any((tmp_path / "partial").iterdir())


def test_an_interrupted_unit_starts_over_when_an_input_changed(
        demo, store, tmp_path, monkeypatch, resumable):
    unit, flag, ran = resumable
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("")
    with monkeypatch.context() as patch:
        interrupted_after_its_unit(patch)
        with pytest.raises(KeyboardInterrupt):
            run(demo, store, tmp_path, units=unit)
    flag.unlink()
    (demo.root / "data" / "a.txt").write_text("a2")
    summary, _, text = run(demo, store, tmp_path, units=unit)
    assert ran.read_text().split() == ["one", "two", "three"] * 2
    assert "resumed" not in text
    assert not summary.failed
