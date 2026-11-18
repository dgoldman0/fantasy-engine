"""Record each test that passes or skips, and leave out those an interrupted
run passed.

Test selection loads this pytest plugin into every pytest unit it runs.  Each
test whose call passes appends its node id to the file FE_TESTSEL_PASSED
names as soon as it finishes, so the list outlives an interrupted run.  Each
test that skips, and each module that skips itself while pytest collects it,
appends its node id to the file FE_TESTSEL_SKIPPED names, so that a unit
which passed no test because every one skipped can be told from a pass.
When FE_TESTSEL_RESUME names a list of passed tests, the tests on it are
deselected: the interrupted attempt passed them, and nothing it read has
changed since.
"""

import os

PASSED_ENV = "FE_TESTSEL_PASSED"
SKIPPED_ENV = "FE_TESTSEL_SKIPPED"
RESUME_ENV = "FE_TESTSEL_RESUME"


def _note(variable, nodeid):
    path = os.environ.get(variable)
    if path:
        with open(path, "a", encoding="utf-8") as listed:
            listed.write(nodeid + "\n")


def pytest_collection_modifyitems(config, items):
    path = os.environ.get(RESUME_ENV)
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as listed:
            done = {line.rstrip("\n") for line in listed if line.strip()}
    except FileNotFoundError:
        return
    kept = [item for item in items if item.nodeid not in done]
    dropped = [item for item in items if item.nodeid in done]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = kept


def pytest_collectreport(report):
    # A module that skips itself, as pytest.importorskip does when a library
    # is missing, collects no test, and pytest ends with the status a file
    # without tests gives.
    if report.skipped:
        _note(SKIPPED_ENV, report.nodeid)


def pytest_runtest_logreport(report):
    if report.when == "call" and report.passed:
        _note(PASSED_ENV, report.nodeid)
    elif report.skipped and not hasattr(report, "wasxfail"):
        # An expected failure reports as skipped too, but its test ran.
        _note(SKIPPED_ENV, report.nodeid)
