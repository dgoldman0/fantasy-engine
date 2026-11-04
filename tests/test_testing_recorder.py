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


def test_files_read_then_rewritten_are_state_not_inputs(tmp_path):
    (tmp_path / "counter.txt").write_text("1")
    seen = run_recorded("""
        value = int(open("counter.txt").read())
        open("counter.txt", "w").write(str(value + 1))
    """, tmp_path)
    inputs = seen.inputs(excluded=(tmp_path / "record",))
    assert str(tmp_path / "counter.txt") not in inputs.files
    assert str(tmp_path / "counter.txt") in inputs.state
