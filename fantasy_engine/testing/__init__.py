"""Test selection across the system's repositories (decision 36, Part 1h).

A test unit runs again only when something it read has changed.  The
recorder in ``recorder/`` notes what each Python process of a run reads,
``records`` turns those notes into the run's inputs, ``store`` keeps the
inputs of passing runs with their digests, ``suites`` knows how each
repository's units are found and launched, and ``runner`` decides, runs and
reports.  ``python -m fantasy_engine.testing`` is the command line.
"""
