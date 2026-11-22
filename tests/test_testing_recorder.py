"""What the recorder notes in the Python processes of a run."""

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from fantasy_engine.testing import records
from fantasy_engine.testing.runner import RECORDER_DIR


def run_recorded(script: str, tmp_path: Path, *, extra_path=(), env=None) -> records.Observation:
    record = tmp_path / "record"
    shutil.rmtree(record, ignore_errors=True)
    program = tmp_path / "program.py"
    program.write_text(textwrap.dedent(script))
    environment = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.pathsep.join([str(RECORDER_DIR), *map(str, extra_path)]),
        "FE_TESTSEL_RECORD_DIR": str(record),
        "PYTHONHASHSEED": "0",
    }
    environment.update(env or {})
    subprocess.run([sys.executable, str(program)], cwd=tmp_path, env=environment,
                   check=True)
    return records.load(record)


def test_reads_writes_listings_and_imports(tmp_path):
    (tmp_path / "data.txt").write_text("input")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "helper.py").write_text("VALUE = 1\n")
    script = """
        import os, sys
        sys.path.insert(0, os.path.join(os.getcwd(), "pkg"))
        open("data.txt").read()
        with open("out.txt", "w") as out:
            out.write("output")
        os.listdir("pkg")
        import helper
    """
    for _ in range(2):  # the second run imports helper from its cached .pyc
        seen = run_recorded(script, tmp_path)
        assert str(tmp_path / "data.txt") in seen.reads
        assert str(tmp_path / "out.txt") in seen.writes
        assert str(package) in seen.listings
        assert str(package / "helper.py") in seen.reads
        assert not any(path.endswith(".pyc") for path in seen.reads)
        assert str(package) in seen.import_listings
        assert "helper" in seen.import_names
        assert seen.unrecordable == set()
        assert seen.unfinished == 0
    inputs = seen.inputs(excluded=(tmp_path / "record",))
    assert str(tmp_path / "data.txt") in inputs.files
    assert str(tmp_path / "out.txt") not in inputs.files


def test_python_children_record_and_other_programs_mark_the_run(tmp_path):
    (tmp_path / "child.txt").write_text("child input")
    seen = run_recorded("""
        import subprocess, sys
        subprocess.run([sys.executable, "-c", "open('child.txt').read()"], check=True)
        subprocess.run(["env", "A=1", sys.executable, "-c", "open('child.txt').read()"],
                       check=True)
        subprocess.run(["true"], check=True)
    """, tmp_path)
    assert str(tmp_path / "child.txt") in seen.reads
    assert len(seen.processes) == 3
    assert [entry for entry in seen.unrecordable if "true" in entry]
    assert len(seen.unrecordable) == 1


def test_a_started_program_is_noted_with_the_file_it_runs(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    tool = tools / "mytool"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    linked = tmp_path / "linked"
    linked.symlink_to(tools)
    seen = run_recorded(f"""
        import os, subprocess
        tool = {str(tool)!r}
        subprocess.run([tool], check=True)
        # By name, along the PATH the program is given, through a link.
        path = {str(linked)!r} + os.pathsep + os.environ["PATH"]
        subprocess.run(["mytool"], check=True, env={{**os.environ, "PATH": path}})
        # By a path relative to the folder the program starts in.
        subprocess.run(["./mytool"], check=True, cwd={str(tools)!r})
        # Through a program that only starts another.
        subprocess.run(["timeout", "5", tool], check=True)
        try:
            subprocess.run(["no-such-program-anywhere"])
        except FileNotFoundError:
            pass
    """, tmp_path)
    real = str(tool.resolve())
    assert seen.started == {
        f"{tool} (not Python)": {real},
        "mytool (not Python)": {real},
        "./mytool (not Python)": {real},
        "no-such-program-anywhere (not Python)": {None},
    }
    assert set(seen.started) == seen.unrecordable

    # Folders are compared as the files they really hold.
    found, others = seen.started_tools([linked])
    assert found == [real]
    assert others == ["no-such-program-anywhere (not Python)"]
    assert seen.started_tools([]) == ([], sorted(seen.unrecordable))
    assert seen.started_tools([tmp_path / "elsewhere"]) == (
        [], sorted(seen.unrecordable))


def test_files_named_in_a_started_programs_arguments_are_reads(tmp_path):
    (tmp_path / "given.txt").write_text("given")
    (tmp_path / "config.ini").write_text("config")
    (tmp_path / "written.txt").write_text("old")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "relative.txt").write_text("relative")
    seen = run_recorded("""
        import subprocess
        open("written.txt", "w").write("new")
        subprocess.run(["true", "given.txt", "--config=config.ini", "missing.txt",
                        "sub", "written.txt"], check=True)
        subprocess.run(["true", "relative.txt"], cwd="sub", check=True)
        subprocess.run(["timeout", "5", "true", "sub/relative.txt"], check=True)
    """, tmp_path)
    inputs = seen.inputs(excluded=(tmp_path / "record",))
    assert str(tmp_path / "given.txt") in inputs.files
    assert str(tmp_path / "config.ini") in inputs.files
    assert str(sub / "relative.txt") in inputs.files
    # A file the run wrote is its own state, a folder is not a file, and a
    # name that leads nowhere is nothing.
    assert str(tmp_path / "written.txt") not in inputs.files
    assert str(sub) not in inputs.files
    assert not any("missing.txt" in name for name in inputs.files)


def test_only_started_programs_can_be_accounted_for_by_a_folder(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    tool = tools / "mytool"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    seen = run_recorded(f"""
        import subprocess, sys
        subprocess.run([{str(tool)!r}], check=True)
        subprocess.run({str(tool)!r}, shell=True, check=True)
        subprocess.run([sys.executable, "-I", "-c", "pass"], check=True)
    """, tmp_path)
    found, others = seen.started_tools([tools])
    assert found == [str(tool.resolve())]
    # The shell that ran the command line is a program from another folder,
    # and a Python the recorder cannot enter is no started tool at all.
    assert len(others) == 2
    assert any(entry.startswith("/bin/sh ") for entry in others)
    assert any("skips site" in entry for entry in others)
    # A folder that holds the shell accounts for the shell, never for the
    # Python.
    _, still = seen.started_tools([tools, "/bin", "/usr/bin"])
    assert len(still) == 1 and "skips site" in still[0]


def test_isolated_python_children_cannot_be_recorded(tmp_path):
    seen = run_recorded("""
        import subprocess, sys
        subprocess.run([sys.executable, "-I", "-c", "pass"], check=True)
        subprocess.run([sys.executable, "-c", "pass"], env={}, check=True)
    """, tmp_path)
    reasons = sorted(seen.unrecordable)
    assert len(reasons) == 2
    assert any("skips site" in reason for reason in reasons)
    assert any("without the recorder" in reason for reason in reasons)


def test_network_beyond_this_machine_marks_the_run(tmp_path):
    # Raising the audit events directly keeps the test off the network.
    seen = run_recorded("""
        import sys
        sys.audit("socket.getaddrinfo", "example.invalid", 80, 0, 0, 0, 0)
        sys.audit("socket.getaddrinfo", "localhost", 80, 0, 0, 0, 0)
        sys.audit("socket.connect", None, ("127.0.0.1", 9))
        sys.audit("socket.connect", None, "/run/some.sock")
    """, tmp_path)
    assert [entry for entry in seen.unrecordable if "example.invalid" in entry]
    assert len(seen.unrecordable) == 1


def test_the_next_sitecustomize_still_runs(tmp_path):
    later = tmp_path / "later"
    later.mkdir()
    (later / "sitecustomize.py").write_text("import os\nos.environ['CHAINED'] = 'yes'\n")
    marker = tmp_path / "marker.txt"
    run_recorded("""
        import os
        open("marker.txt", "w").write(os.environ.get("CHAINED", "no"))
    """, tmp_path, extra_path=(later,))
    assert marker.read_text() == "yes"


def test_lookups_name_each_folder_an_import_searched(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "found_late.py").write_text("VALUE = 1\n")
    (first / "found_early.py").write_text("VALUE = 2\n")
    seen = run_recorded(f"""
        import importlib, sys
        sys.path[:0] = [{str(first)!r}, {str(second)!r}]
        import found_late
        importlib.import_module("found_early")
        try:
            import missing_everywhere
        except ImportError:
            pass
    """, tmp_path)
    # A name is looked for in each folder up to the one that holds it, and
    # one that is found nowhere in every folder.
    assert {"found_late", "found_early", "missing_everywhere"} <= seen.lookups[str(first)]
    assert {"found_late", "missing_everywhere"} <= seen.lookups[str(second)]
    assert "found_early" not in seen.lookups[str(second)]
    # importlib.import_module raises no import event, yet its lookups count.
    assert "found_early" not in seen.import_names
    assert str(first / "found_early.py") in seen.reads
    # Modules imported before the recorder count as looked up at startup.
    startup = os.path.dirname(os.__file__)
    assert "os" in seen.lookups[startup]


def test_a_path_entry_no_lookup_could_search_is_read(tmp_path):
    missing = tmp_path / "missing"
    seen = run_recorded(f"""
        import sys
        sys.path.insert(0, {str(missing)!r})
        import colorsys
    """, tmp_path)
    assert str(missing) in seen.reads
    assert str(missing) not in seen.lookups


def _pytest_tree(tmp_path, conftest=None):
    root = tmp_path / "proj"
    (root / "tests" / "deeper").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n")
    (root / "tests" / "test_x.py").write_text("def test_x():\n    pass\n")
    (root / "tests" / "deeper" / "test_y.py").write_text("def test_y():\n    pass\n")
    (root / "tests" / "notes.txt").write_text("")
    if conftest is not None:
        (root / "tests" / "conftest.py").write_text(textwrap.dedent(conftest))
    return root


def _recorded_pytest(root, tmp_path, *args):
    return run_recorded(f"""
        import os, sys, pytest
        os.chdir({str(root)!r})
        sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", *{list(args)!r}]))
    """, tmp_path)


def test_pytests_listings_on_the_way_to_a_test_keep_only_the_names_it_checks(tmp_path):
    root = _pytest_tree(tmp_path)
    seen = _recorded_pytest(root, tmp_path, "tests/test_x.py")
    for folder in (root, root / "tests"):
        assert "conftest.py" in seen.collections[str(folder)]
        assert "__init__.py" in seen.collections[str(folder)]
        assert str(folder) not in seen.listings
    assert "pytest.ini" in seen.collections[str(root)]

    # A folder pytest was given is collected whole, so its listing counts
    # in full, as does every folder inside it.
    seen = _recorded_pytest(root, tmp_path, "tests")
    assert str(root) in seen.collections
    assert {str(root / "tests"), str(root / "tests" / "deeper")} <= seen.listings
    assert str(root / "tests") not in seen.collections


def test_pytests_listings_count_in_full_when_a_conftest_hooks_collection(tmp_path):
    root = _pytest_tree(tmp_path, conftest="""
        def pytest_collect_file(file_path, parent):
            return None
    """)
    seen = _recorded_pytest(root, tmp_path, "tests/test_x.py")
    assert {str(root), str(root / "tests")} <= seen.listings
    assert not seen.collections


def test_files_read_then_rewritten_are_state_not_inputs(tmp_path):
    (tmp_path / "counter.txt").write_text("1")
    seen = run_recorded("""
        value = int(open("counter.txt").read())
        open("counter.txt", "w").write(str(value + 1))
    """, tmp_path)
    inputs = seen.inputs(excluded=(tmp_path / "record",))
    assert str(tmp_path / "counter.txt") not in inputs.files
    assert str(tmp_path / "counter.txt") in inputs.state
