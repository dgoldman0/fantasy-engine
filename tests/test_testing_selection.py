"""Selection over a small repository: what runs, what is skipped, and why."""

import io
import os
import shutil
import subprocess
import textwrap

import pytest

from fantasy_engine.testing.runner import Runner, launch_key
from fantasy_engine.testing.store import Store
from fantasy_engine.testing.suites import AkashicRepo, Locations, PytestRepo, Unit

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


def test_where_a_caller_finds_megapad_or_e2fsprogs_splits_no_record(
        demo, store, tmp_path, monkeypatch):
    run(demo, store, tmp_path)
    monkeypatch.setenv("MEGAPAD_ROOT", str(tmp_path / "another-megapad"))
    monkeypatch.setenv("AKASHIC_E2FSPROGS_TOOL_DIR", str(tmp_path / "sbin"))
    summary, ran, _ = run(demo, store, tmp_path)
    assert ran == ["tests/test_d.py"]  # it starts a program, so it always runs
    assert summary.skipped == len(TESTS) - 1


@pytest.fixture
def akashic(tmp_path, monkeypatch):
    pinned = tmp_path / "pinned-sbin"
    pinned.mkdir()
    monkeypatch.setattr(AkashicRepo, "PINNED_E2FSPROGS", pinned)
    monkeypatch.delenv("MEGAPAD_ROOT", raising=False)
    monkeypatch.delenv("AKASHIC_E2FSPROGS_TOOL_DIR", raising=False)
    return AkashicRepo(tmp_path / "akashic", tmp_path / "megapad"), pinned


def akashic_launch(repo, store, tmp_path):
    """The environment and launch key of one Akashic unit, as a run makes them."""
    runner = Runner(store, repos=[repo], out=io.StringIO(),
                    scratch=tmp_path / "scratch", partial_root=tmp_path / "partial")
    launch = repo.launch(Unit(repo, "local_testing/test_x.py"), runner.python)
    env = runner.environment(launch, tmp_path / "t", tmp_path / "r")
    return env, launch_key(launch.argv, launch.cwd, env, runner.python)


def test_akashic_units_get_the_workspace_megapad_and_the_pinned_e2fsprogs(
        akashic, store, tmp_path, monkeypatch):
    repo, pinned = akashic
    env, plain = akashic_launch(repo, store, tmp_path)
    assert env["MEGAPAD_ROOT"] == str(tmp_path / "megapad")
    assert env["AKASHIC_E2FSPROGS_TOOL_DIR"] == str(pinned)
    assert repo.notes(os.environ) == []

    # A caller that exports the pinned build, or names another MegaPad,
    # launches the same unit, and the run says which MegaPad it used.
    monkeypatch.setenv("MEGAPAD_ROOT", str(tmp_path / "another-megapad"))
    monkeypatch.setenv("AKASHIC_E2FSPROGS_TOOL_DIR", str(pinned))
    env, exported = akashic_launch(repo, store, tmp_path)
    assert exported == plain
    assert env["MEGAPAD_ROOT"] == str(tmp_path / "megapad")
    [note] = repo.notes(os.environ)
    assert "another-megapad" in note and str(tmp_path / "megapad") in note
    monkeypatch.setenv("MEGAPAD_ROOT", str(tmp_path / "megapad"))
    assert repo.notes(os.environ) == []

    # Another e2fsprogs build is another launch.
    monkeypatch.setenv("AKASHIC_E2FSPROGS_TOOL_DIR", str(tmp_path / "other-sbin"))
    env, other = akashic_launch(repo, store, tmp_path)
    assert other != plain
    assert env["AKASHIC_E2FSPROGS_TOOL_DIR"] == str(tmp_path / "other-sbin")


def test_akashic_units_lack_e2fsprogs_only_when_none_is_built_or_named(
        akashic, store, tmp_path, monkeypatch):
    repo, _ = akashic
    monkeypatch.setattr(AkashicRepo, "PINNED_E2FSPROGS", tmp_path / "absent")
    env, _ = akashic_launch(repo, store, tmp_path)
    assert "AKASHIC_E2FSPROGS_TOOL_DIR" not in env
    assert env["MEGAPAD_ROOT"] == str(tmp_path / "megapad")


def test_a_dry_run_reports_without_running(demo, store, tmp_path):
    run(demo, store, tmp_path)
    before = store.latest("demo:tests/test_b.py").run_id
    (demo.root / "data" / "b.txt").write_text("broken")
    _, ran, text = run(demo, store, tmp_path, dry_run=True)
    assert ran == ["tests/test_b.py", "tests/test_d.py"]
    assert "RUN?  demo:tests/test_b.py  changed:" in text
    assert store.latest("demo:tests/test_b.py").run_id == before


STANDALONE = """
    def main():
        print("a driver that runs on its own")


    if __name__ == "__main__":
        main()
"""


def commit_file(root, name, source, message):
    (root / name).write_text(textwrap.dedent(source))
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", message], check=True)


def unit_line(text, unit_id):
    [line] = [line for line in text.splitlines() if "  %s  " % unit_id in line]
    return line


def test_a_unit_that_ran_nothing_is_reported_apart_from_the_passes(
        demo, store, tmp_path):
    commit_file(demo.root, "tests/test_s.py", STANDALONE, "standalone")
    units = [u for u in demo.units() if u.name in ("tests/test_a.py", "tests/test_s.py")]
    summary, ran, text = run(demo, store, tmp_path, units=units)
    assert ran == ["tests/test_a.py", "tests/test_s.py"]
    assert summary.passed == 1 and summary.empty == ["demo:tests/test_s.py"]
    line = unit_line(text, "demo:tests/test_s.py")
    assert "no passing run on record -> empty in" in line
    assert line.endswith("; it ran nothing")
    assert ": 1 passed, 1 ran nothing, 0 failed." in text

    # It is skipped while unchanged, as a pass is, and its line says that
    # the run it relies on ran nothing.
    summary, ran, text = run(demo, store, tmp_path, units=units)
    assert ran == [] and summary.skipped == 2 and summary.skipped_empty == 1
    assert unit_line(text, "demo:tests/test_s.py").endswith(", in which it ran nothing")
    assert "ran nothing" not in unit_line(text, "demo:tests/test_a.py")
    assert "1 of which ran nothing in the run they rely on." in text

    # A dry run marks a unit to run whose last run ran nothing.
    (demo.root / "tests" / "test_s.py").write_text(
        textwrap.dedent(STANDALONE) + "# changed\n")
    summary, ran, text = run(demo, store, tmp_path, units=units, dry_run=True)
    assert ran == ["tests/test_s.py"] and summary.last_empty == 1
    assert unit_line(text, "demo:tests/test_s.py").endswith(
        "; it ran nothing at its last run")
    assert "Would run 1 units, 1 of which ran nothing at their last run, and skip 1 " in text


COLLECTED_WHEN_FLAGGED = """
    import os

    # os.path.exists raises no audit event, so this read goes unrecorded.
    if os.path.exists("data/collect"):
        def test_now_collected():
            pass
"""


def test_a_full_run_finds_tests_that_appeared_where_the_unit_ran_nothing(
        demo, store, tmp_path):
    commit_file(demo.root, "tests/test_f.py", COLLECTED_WHEN_FLAGGED, "flagged")
    unit = [u for u in demo.units() if u.name == "tests/test_f.py"]
    summary, _, _ = run(demo, store, tmp_path, units=unit)
    assert summary.empty == ["demo:tests/test_f.py"]
    (demo.root / "data" / "collect").write_text("")
    _, ran, _ = run(demo, store, tmp_path, units=unit)
    assert ran == []  # wrongly skipped
    summary, ran, text = run(demo, store, tmp_path, units=unit, full=True)
    assert summary.passed == 1 and summary.missed == ["demo:tests/test_f.py"]
    assert "MISSED INPUT: the selection would have skipped it as unchanged since" in text
    assert unit_line(text, "demo:tests/test_f.py").endswith(", in which it ran nothing")


def test_list_and_explain_mark_a_unit_whose_last_run_ran_nothing(
        tmp_path, store, capsys):
    from fantasy_engine.testing.__main__ import main
    from fantasy_engine.testing.suites import repositories

    workspace = tmp_path / "ws"
    root = workspace / "akashic"
    (root / "local_testing").mkdir(parents=True)
    (root / "local_testing" / "test_p.py").write_text("def test_p():\n    pass\n")
    (root / "local_testing" / "test_s.py").write_text(textwrap.dedent(STANDALONE))
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "akashic"], check=True)
    [repo] = repositories(workspace)
    Runner(store, repos=[repo], out=io.StringIO(), scratch=tmp_path / "scratch",
           partial_root=tmp_path / "partial").run(repo.units())
    common = ["--workspace", str(workspace), "--store", str(store.path)]

    main(["list", "--recorded", *common])
    listed = capsys.readouterr().out.splitlines()
    assert listed == ["akashic:local_testing/test_p.py",
                      "akashic:local_testing/test_s.py  (ran nothing at its last run)"]

    main(["explain", *common])
    explained = capsys.readouterr().out.splitlines()
    assert explained[0].startswith("akashic:local_testing/test_p.py: unchanged since ")
    assert "ran nothing" not in explained[0]
    assert explained[1].startswith("akashic:local_testing/test_s.py: unchanged since ")
    assert explained[1].endswith(", in which it ran nothing")

    (root / "local_testing" / "test_s.py").write_text(
        textwrap.dedent(STANDALONE) + "# changed\n")
    main(["explain", "test_s", *common])
    explained = capsys.readouterr().out.splitlines()
    assert explained[0].startswith("akashic:local_testing/test_s.py: changed: ")
    assert explained[0].endswith("; it ran nothing at its last run")


ALL_SKIPPED = """
    import pytest

    @pytest.mark.skip(reason="needs an image this checkout lacks")
    def test_marked():
        pass

    def test_skips_itself():
        pytest.skip("needs a program this machine lacks")
"""

MODULE_SKIPPED = """
    import pytest

    pytest.skip("needs a library this machine lacks", allow_module_level=True)

    def test_never_collected():
        pass
"""

ONE_SKIPPED = """
    import pytest

    def test_runs():
        pass

    @pytest.mark.skip(reason="not on this machine")
    def test_skips():
        pass
"""


def test_a_unit_whose_tests_all_skip_is_reported_apart_and_runs_again(
        demo, store, tmp_path):
    commit_file(demo.root, "tests/test_k.py", ALL_SKIPPED, "all skip")
    commit_file(demo.root, "tests/test_m.py", MODULE_SKIPPED, "module skips")
    commit_file(demo.root, "tests/test_n.py", ONE_SKIPPED, "one skips")
    names = ("tests/test_k.py", "tests/test_m.py", "tests/test_n.py")
    units = [u for u in demo.units() if u.name in names]
    summary, ran, text = run(demo, store, tmp_path, units=units)
    assert ran == list(names)
    assert summary.passed == 1 and not summary.empty and not summary.failed
    assert sorted(summary.all_skipped) == ["demo:tests/test_k.py", "demo:tests/test_m.py"]
    for unit_id in summary.all_skipped:
        line = unit_line(text, unit_id)
        assert "no passing run on record -> all-skipped in" in line
        assert line.endswith("; all its tests skipped")
        assert "  skipped all its tests: %s" % unit_id in text
    assert ": 1 passed, 2 skipped all their tests, 0 failed." in text
    assert store.latest("demo:tests/test_k.py").all_skipped
    assert store.latest_pass("demo:tests/test_k.py") is None

    # Unchanged, both run again, since nothing on record says why their
    # tests skipped; the unit that passed a test is skipped.
    summary, ran, text = run(demo, store, tmp_path, units=units, dry_run=True)
    assert ran == ["tests/test_k.py", "tests/test_m.py"]
    assert summary.last_all_skipped == 2 and summary.skipped == 1
    assert unit_line(text, "demo:tests/test_m.py").endswith(
        "no passing run on record; all its tests skipped at its last run")
    assert ("Would run 2 units, 2 of which skipped all their tests at their last "
            "run, and skip 1 ") in text
    summary, ran, _ = run(demo, store, tmp_path, units=units)
    assert ran == ["tests/test_k.py", "tests/test_m.py"]
    assert len(summary.all_skipped) == 2 and summary.skipped == 1


SKIPPED_WITHOUT_IMAGE = """
    import os
    import pytest

    # os.path.exists raises no audit event, so this read goes unrecorded.
    @pytest.mark.skipif(not os.path.exists("data/image"), reason="no image")
    def test_reads_the_image():
        pass
"""


def test_a_full_run_finds_a_unit_whose_tests_now_all_skip(demo, store, tmp_path):
    commit_file(demo.root, "tests/test_i.py", SKIPPED_WITHOUT_IMAGE, "image")
    unit = [u for u in demo.units() if u.name == "tests/test_i.py"]
    (demo.root / "data" / "image").write_text("")
    summary, _, _ = run(demo, store, tmp_path, units=unit)
    assert summary.passed == 1
    (demo.root / "data" / "image").unlink()
    _, ran, _ = run(demo, store, tmp_path, units=unit)
    assert ran == []  # wrongly skipped
    summary, ran, text = run(demo, store, tmp_path, units=unit, full=True)
    assert summary.all_skipped == ["demo:tests/test_i.py"]
    assert summary.missed == ["demo:tests/test_i.py"]
    assert "MISSED INPUT: the selection would have skipped it as unchanged since" in text


def test_list_and_explain_mark_a_unit_whose_tests_all_skipped(
        tmp_path, store, capsys):
    from fantasy_engine.testing.__main__ import main
    from fantasy_engine.testing.suites import repositories

    workspace = tmp_path / "ws"
    root = workspace / "akashic"
    (root / "local_testing").mkdir(parents=True)
    (root / "local_testing" / "test_p.py").write_text("def test_p():\n    pass\n")
    (root / "local_testing" / "test_k.py").write_text(textwrap.dedent(ALL_SKIPPED))
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "akashic"], check=True)
    [repo] = repositories(workspace)
    Runner(store, repos=[repo], out=io.StringIO(), scratch=tmp_path / "scratch",
           partial_root=tmp_path / "partial").run(repo.units())
    common = ["--workspace", str(workspace), "--store", str(store.path)]

    main(["list", "--recorded", *common])
    listed = capsys.readouterr().out.splitlines()
    assert listed == [
        "akashic:local_testing/test_k.py  (all its tests skipped at its last run)",
        "akashic:local_testing/test_p.py"]

    main(["explain", *common])
    explained = capsys.readouterr().out.splitlines()
    assert explained[0] == ("akashic:local_testing/test_k.py: no passing run on "
                            "record; all its tests skipped at its last run")
    assert explained[1].startswith("akashic:local_testing/test_p.py: unchanged since ")
    assert "skipped" not in explained[1]


def test_a_resumed_unit_counts_the_passes_of_its_interrupted_attempt(tmp_path):
    from fantasy_engine.testing.runner import passed_no_test

    passed, skipped = tmp_path / "passed", tmp_path / "skipped"
    # Neither list: only expected failures ran, and they ran.
    assert not passed_no_test(passed, skipped)
    skipped.write_text("tests/test_r.py::test_three\n")
    assert passed_no_test(passed, skipped)
    # The interrupted attempt passed a test before the rest skipped.
    passed.write_text("tests/test_r.py::test_one\n")
    assert not passed_no_test(passed, skipped)


def test_recorded_adds_the_units_the_patterns_name(tmp_path, store, capsys):
    from fantasy_engine.testing.__main__ import main
    from fantasy_engine.testing.suites import repositories

    workspace = tmp_path / "ws"
    root = workspace / "akashic"
    (root / "local_testing").mkdir(parents=True)
    for name in ("test_a", "test_b", "test_new"):
        (root / "local_testing" / f"{name}.py").write_text(
            f"def {name}():\n    pass\n")
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "akashic"], check=True)
    [repo] = repositories(workspace)
    # The record holds test_a and test_b; test_new has never run.
    Runner(store, repos=[repo], out=io.StringIO(), scratch=tmp_path / "scratch",
           partial_root=tmp_path / "partial").run(
        [unit for unit in repo.units() if "test_new" not in unit.id])
    common = ["--workspace", str(workspace), "--store", str(store.path)]
    a, b, new = ("akashic:local_testing/%s.py" % name
                 for name in ("test_a", "test_b", "test_new"))

    main(["list", "--recorded", *common])
    assert capsys.readouterr().out.splitlines() == [a, b]
    # Patterns given with --recorded add the units they name to the recorded
    # ones, so a test the record has not seen runs in the same command.
    main(["list", "--recorded", "test_new", *common])
    assert capsys.readouterr().out.splitlines() == [a, b, new]
    main(["list", "--recorded", "test_a", *common])
    assert capsys.readouterr().out.splitlines() == [a, b]
    # Patterns alone name only their units.
    main(["list", "test_new", *common])
    assert capsys.readouterr().out.splitlines() == [new]


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


TOOLED = """
    import os
    import subprocess

    def _ran(name):
        with open(%r, "a") as log:
            log.write(name + "\\n")

    def test_one():
        _ran("one")
        subprocess.run([%r, "data/a.txt"], check=True)

    def test_two():
        _ran("two")

    def test_three():
        _ran("three")
        assert not os.path.exists(%r)
"""


class ToolRepo(DemoRepo):
    """A demo repository that vouches for the programs in one folder."""

    def __init__(self, root, entries, folders):
        super().__init__(root, entries)
        self.folders = folders

    def tool_folders(self, env):
        return list(self.folders)


@pytest.fixture
def tooled(demo, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    tool = tools / "checker"
    tool.write_text("#!/bin/sh\ntest -f \"$1\"\n")
    tool.chmod(0o755)
    flag = tmp_path / "store" / "fail-three"
    ran = tmp_path / "store" / "ran.log"
    (demo.root / "tests" / "test_t.py").write_text(
        textwrap.dedent(TOOLED % (str(ran), str(tool), str(flag))))
    git = ["git", "-C", str(demo.root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "tooled"], check=True)
    flag.parent.mkdir(parents=True, exist_ok=True)

    def repo(*folders):
        vouching = ToolRepo(demo.root, demo.entries, folders)
        unit = [u for u in vouching.units() if u.name == "tests/test_t.py"]
        return vouching, unit

    return repo, tool, flag, ran


def interrupt_tooled(repo, unit, store, tmp_path, monkeypatch, flag):
    flag.write_text("")
    with monkeypatch.context() as patch:
        interrupted_after_its_unit(patch)
        with pytest.raises(KeyboardInterrupt):
            run(repo, store, tmp_path, units=unit)
    flag.unlink()


def test_an_interrupted_unit_resumes_when_its_programs_come_from_declared_folders(
        store, tmp_path, monkeypatch, tooled):
    make, tool, flag, ran = tooled
    repo, unit = make(tool.parent)
    interrupt_tooled(repo, unit, store, tmp_path, monkeypatch, flag)
    assert ran.read_text().split() == ["one", "two", "three"]

    _, _, text = run(repo, store, tmp_path, units=unit, dry_run=True)
    assert "resumes after 2 passed tests" in text
    summary, _, text = run(repo, store, tmp_path, units=unit)
    assert ran.read_text().split() == ["one", "two", "three", "three"]
    assert "resumed after 2 passed tests" in text
    assert not summary.failed

    # The tool's file is an input of the recorded result, and a unit whose
    # programs all come from declared folders is skipped like any other while
    # nothing it or its tool read has changed.
    result = store.latest_pass(unit[0].id)
    assert str(tool.resolve()) in result.inputs["files"]
    assert result.inputs["unrecordable"] == []
    summary, ran_units, _ = run(repo, store, tmp_path, units=unit)
    assert ran_units == [] and summary.skipped == 1


def test_a_unit_with_declared_programs_runs_again_when_its_tool_or_a_file_changes(
        demo, store, tmp_path, tooled):
    make, tool, flag, ran = tooled
    repo, unit = make(tool.parent)
    run(repo, store, tmp_path, units=unit)
    _, ran_units, _ = run(repo, store, tmp_path, units=unit)
    assert ran_units == []

    tool.write_text("#!/bin/sh\ntest -f \"$1\" && true\n")
    _, ran_units, text = run(repo, store, tmp_path, units=unit)
    assert ran_units == ["tests/test_t.py"]
    assert "changed: %s" % tool.resolve() in text

    # Only the tool read data/a.txt: the test names it on the command line.
    (demo.root / "data" / "a.txt").write_text("a2")
    _, ran_units, text = run(repo, store, tmp_path, units=unit)
    assert ran_units == ["tests/test_t.py"]
    assert "changed: %s" % (demo.root / "data" / "a.txt") in text


def test_a_unit_that_starts_an_undeclared_program_always_runs(
        store, tmp_path, tooled):
    make, tool, flag, ran = tooled
    repo, unit = make()
    run(repo, store, tmp_path, units=unit)
    _, ran_units, text = run(repo, store, tmp_path, units=unit)
    assert ran_units == ["tests/test_t.py"]
    assert "it starts %s (not Python)" % tool in text


def test_a_changed_tool_starts_the_interrupted_unit_over(
        store, tmp_path, monkeypatch, tooled):
    make, tool, flag, ran = tooled
    repo, unit = make(tool.parent)
    interrupt_tooled(repo, unit, store, tmp_path, monkeypatch, flag)

    tool.write_text("#!/bin/sh\ntest -f \"$1\" && true\n")
    _, _, text = run(repo, store, tmp_path, units=unit, dry_run=True)
    assert "resumes" not in text
    summary, _, text = run(repo, store, tmp_path, units=unit)
    assert ran.read_text().split() == ["one", "two", "three"] * 2
    assert "resumed" not in text
    assert not summary.failed


def test_a_changed_file_handed_to_the_tool_starts_the_unit_over(
        demo, store, tmp_path, monkeypatch, tooled):
    make, tool, flag, ran = tooled
    repo, unit = make(tool.parent)
    interrupt_tooled(repo, unit, store, tmp_path, monkeypatch, flag)

    # Only the tool read data/a.txt: the test names it on the command line.
    (demo.root / "data" / "a.txt").write_text("a2")
    summary, _, text = run(repo, store, tmp_path, units=unit)
    assert ran.read_text().split() == ["one", "two", "three"] * 2
    assert "resumed" not in text
    assert not summary.failed


def test_a_program_from_an_undeclared_folder_keeps_the_unit_from_resuming(
        store, tmp_path, monkeypatch, tooled):
    make, tool, flag, ran = tooled
    # No folder declared, then a folder that does not hold the tool.
    for folders in ((), (tmp_path / "store",)):
        repo, unit = make(*folders)
        interrupt_tooled(repo, unit, store, tmp_path, monkeypatch, flag)
        _, _, text = run(repo, store, tmp_path, units=unit, dry_run=True)
        assert "resumes" not in text
        summary, _, text = run(repo, store, tmp_path, units=unit)
        assert "resumed" not in text
        assert not summary.failed
    assert ran.read_text().split() == ["one", "two", "three"] * 4


def test_akashic_declares_the_folder_its_tool_variable_names(tmp_path):
    from fantasy_engine.testing.suites import AkashicRepo, Repo

    repo = AkashicRepo(tmp_path / "akashic", tmp_path / "megapad")
    assert repo.tool_folders({}) == []
    assert repo.tool_folders({"AKASHIC_E2FSPROGS_TOOL_DIR": ""}) == []
    assert repo.tool_folders(
        {"AKASHIC_E2FSPROGS_TOOL_DIR": "/opt/e2fsprogs/sbin"}
    ) == [tmp_path.__class__("/opt/e2fsprogs/sbin")]
    # A repository declares nothing unless it says so.
    assert Repo(tmp_path).tool_folders(
        {"AKASHIC_E2FSPROGS_TOOL_DIR": "/opt/e2fsprogs/sbin"}) == []


def checkout_copy(demo, tmp_path, name="copy"):
    """Another checkout of the demo repository, as a worktree would be."""
    copy = tmp_path / name
    shutil.copytree(demo.root, copy, symlinks=True)
    return DemoRepo(copy, [copy / "first", copy / "second"])


def test_another_checkout_skips_the_units_whose_files_are_the_same(
        demo, store, tmp_path):
    run(demo, store, tmp_path)
    other = checkout_copy(demo, tmp_path)
    summary, ran, _ = run(other, store, tmp_path)
    assert ran == ["tests/test_d.py"]  # it starts a program, so it always runs
    assert summary.skipped == len(TESTS) - 1

    (other.root / "data" / "a.txt").write_text("a2")
    _, ran, text = run(other, store, tmp_path)
    assert ran == ["tests/test_a.py", "tests/test_d.py"]
    assert "changed: %s" % (other.root / "data" / "a.txt") in text

    # The record now holds the copy's pass, and the first checkout's a.txt
    # differs from the copy's.
    _, ran, text = run(demo, store, tmp_path)
    assert ran == ["tests/test_a.py", "tests/test_d.py"]
    assert "changed: %s" % (demo.root / "data" / "a.txt") in text


def test_an_interrupted_unit_resumes_only_in_its_own_checkout(
        demo, store, tmp_path, monkeypatch, resumable):
    unit, flag, ran = resumable
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("")
    with monkeypatch.context() as patch:
        interrupted_after_its_unit(patch)
        with pytest.raises(KeyboardInterrupt):
            run(demo, store, tmp_path, units=unit)
    flag.unlink()
    other = checkout_copy(demo, tmp_path)
    copied = [u for u in other.units() if u.name == "tests/test_r.py"]
    summary, _, text = run(other, store, tmp_path, units=copied)
    assert "resumed" not in text
    assert ran.read_text().split() == ["one", "two", "three"] * 2
    assert not summary.failed


def test_locations_name_a_repository_path_alike_from_every_checkout(tmp_path):
    real = tmp_path / "real-akashic"
    real.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "akashic").symlink_to(real)
    places = Locations([AkashicRepo(workspace / "akashic", workspace / "megapad")])

    # The folder the repository is given as and the one it resolves to.
    for form in (workspace / "akashic" / "x.f", real / "x.f"):
        assert places.name(str(form)) == "@akashic/x.f"
    assert places.name(str(real)) == "@akashic"
    # A folder whose name merely begins the same is another folder.
    beside = tmp_path / "real-akashic-old" / "x.f"
    assert places.name(str(beside)) == str(beside)
    assert places.names(os.pathsep.join([str(real / "a"), "/usr/lib"])) == \
        os.pathsep.join(["@akashic/a", "/usr/lib"])

    assert places.path("@akashic/x.f") == str(workspace / "akashic" / "x.f")
    assert places.path("@akashic") == str(workspace / "akashic")
    assert places.path("/usr/lib/x") == "/usr/lib/x"
    # A repository this workspace lacks names no file.
    assert places.path("@lm1/emu/x.py") == "@lm1/emu/x.py"


def test_a_listing_counts_the_names_its_repository_does_not_ignore(
        demo, store, tmp_path):
    (demo.root / ".gitignore").write_text("*.scratch\n")
    git = ["git", "-C", str(demo.root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", ".gitignore"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "ignore scratch"], check=True)
    run(demo, store, tmp_path)
    other = checkout_copy(demo, tmp_path)
    (other.root / "notes.scratch").write_text("")
    summary, ran, _ = run(other, store, tmp_path)
    assert ran == ["tests/test_d.py"]
    assert summary.skipped == len(TESTS) - 1
    (other.root / "notes.txt").write_text("")
    _, ran, text = run(other, store, tmp_path)
    assert "changed: listing of %s" % other.root in text


def test_akashic_runs_its_ext4_files_on_the_emulator_as_final_units(
        tmp_path, store, monkeypatch):
    from fantasy_engine.testing.suites import FINAL_ONLY

    root = tmp_path / "akashic"
    (root / "local_testing").mkdir(parents=True)
    for name in ("test_vfs_ext4.py", "test_vfs_replace_ext4.py", "test_pad.py"):
        (root / "local_testing" / name).write_text("def test_x():\n    pass\n")
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "akashic"], check=True)
    repo = AkashicRepo(root, tmp_path / "megapad")

    names = [unit.name for unit in repo.units()]
    assert "local_testing/test_vfs_ext4.py@emulator" in names
    assert "local_testing/test_vfs_replace_ext4.py@emulator" in names
    assert not any(name.startswith("local_testing/test_pad.py@") for name in names)
    sets = {unit.name: unit.set for unit in repo.units()}
    assert sets["local_testing/test_vfs_ext4.py"] == "release"
    assert sets["local_testing/test_vfs_ext4.py@emulator"] == "final"
    assert "akashic:local_testing/test_vfs_ext4.py@emulator" in FINAL_ONLY

    # A caller's choice of machine reaches no unit; the emulator units choose
    # it themselves and run the file itself.
    monkeypatch.setenv("AKASHIC_EXT4_BACKEND", "emulator")
    runner = Runner(store, repos=[repo], out=io.StringIO(),
                    scratch=tmp_path / "scratch", partial_root=tmp_path / "partial")
    plain = repo.launch(Unit(repo, "local_testing/test_vfs_ext4.py"), runner.python)
    plain_env = runner.environment(plain, tmp_path / "t", tmp_path / "r")
    assert "AKASHIC_EXT4_BACKEND" not in plain_env
    on_emulator = repo.launch(Unit(repo, "local_testing/test_vfs_ext4.py@emulator"),
                              runner.python)
    emulator_env = runner.environment(on_emulator, tmp_path / "t", tmp_path / "r")
    assert emulator_env["AKASHIC_EXT4_BACKEND"] == "emulator"
    assert on_emulator.argv[-1] == "local_testing/test_vfs_ext4.py"
    # The same file on the two machines is launched two ways.
    assert launch_key(plain.argv, plain.cwd, plain_env, runner.python) != \
        launch_key(on_emulator.argv, on_emulator.cwd, emulator_env, runner.python)


def test_megapad_prepare_builds_the_simulator_library_its_makefile_names(tmp_path):
    from fantasy_engine.testing.suites import MegaPadRepo

    with_library = tmp_path / "with"
    with_library.mkdir()
    (with_library / "Makefile").write_text(
        "SIMULATOR_ACCEL_LIB := libsim.so\n"
        "accel:\n\t@true\n"
        "$(SIMULATOR_ACCEL_LIB): source.cpp\n\t@cp source.cpp $@\n")
    (with_library / "source.cpp").write_text("one\n")
    MegaPadRepo(with_library).prepare(dict(os.environ))
    assert (with_library / "libsim.so").read_text() == "one\n"

    without = tmp_path / "without"
    without.mkdir()
    (without / "Makefile").write_text("accel:\n\t@true\n")
    MegaPadRepo(without).prepare(dict(os.environ))
    assert sorted(p.name for p in without.iterdir()) == ["Makefile"]


def test_lm1_prepare_builds_the_chiplet_library(tmp_path):
    from fantasy_engine.testing.suites import LM1Repo

    with_chiplet = tmp_path / "with"
    chiplet = with_chiplet / "chiplet"
    chiplet.mkdir(parents=True)
    (chiplet / "Makefile").write_text(
        "all: build/lib.so\n"
        "build/lib.so: source.cpp\n\t@mkdir -p build\n\t@cp source.cpp $@\n")
    (chiplet / "source.cpp").write_text("one\n")
    LM1Repo(with_chiplet).prepare(dict(os.environ))
    assert (chiplet / "build" / "lib.so").read_text() == "one\n"

    # A checkout without the chiplet module builds nothing.
    without = tmp_path / "without"
    without.mkdir()
    LM1Repo(without).prepare(dict(os.environ))
    assert list(without.iterdir()) == []
