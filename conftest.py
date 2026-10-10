# Command-line options must live in the root conftest: pytest parses the command line before it
# reads tests/conftest.py, so `--corpus PATH` defined there was rejected as an unknown argument.


def pytest_addoption(parser):
    parser.addoption("--update-snapshots", action="store_true",
                     help="corpus: accept current results as the new snapshots (only after David reviews the diff)")
    parser.addoption("--corpus", default=None,
                     help="corpus: folder of real decks (else $SLIDETISTIC_CORPUS, else .corpus-path)")
