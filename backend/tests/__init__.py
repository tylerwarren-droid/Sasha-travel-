"""Sasha 424 · the test package: every test module is imported as tests.<name> (CI: `python -m unittest discover -s tests -t .`), so this
runs before ANY test, whatever the order. The fixture that names the founder and installs person_access's test resolver
(tests/founder_fixture.py) is therefore never forgotten by a file: before this, 7 group tests passed only when an earlier module happened
to import it, and failed alone by falling through to person_access's network read."""
import tests.founder_fixture  # noqa: F401
