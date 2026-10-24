# data/sample

Intentionally empty of data. No synthetic or demo dataset ships with this project.

Unit tests generate synthetic data **in memory** (see `tests/conftest.py`); every
such row is labelled `value_type = "synthetic"`, is never written to disk and is
excluded from every real-data result by `src.analysis.descriptive.real_only`.
