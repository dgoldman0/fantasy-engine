"""Record each test that passes, and leave out those an interrupted run passed.

Test selection loads this pytest plugin into every pytest unit it runs.  Each
test whose call passes appends its node id to the file FE_TESTSEL_PASSED
names as soon as it finishes, so the list outlives an interrupted run.  When
FE_TESTSEL_RESUME names such a list, the tests on it are deselected: the
interrupted attempt passed them, and nothing it read has changed since.
"""

import os

PASSED_ENV = "FE_TESTSEL_PASSED"
RESUME_ENV = "FE_TESTSEL_RESUME"


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


def pytest_runtest_logreport(report):
    path = os.environ.get(PASSED_ENV)
    if path and report.when == "call" and report.passed:
        with open(path, "a", encoding="utf-8") as passed:
            passed.write(report.nodeid + "\n")
