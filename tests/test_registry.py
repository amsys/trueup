"""Tests for `trueup.registry`: the registry lookups, the cache, and the one network module.

Every test runs a local `http.server` on 127.0.0.1 and patches
`registry.BASE_URLS`, so no test opens a connection to a real registry.
"""

from __future__ import annotations

import ast
import json
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from trueup import registry

TRUEUP_DIR = Path(registry.__file__).resolve().parent
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class FakeRegistry:
    """A local HTTP server that answers from a table of canned routes.

    Attributes:
        routes: Request path to `(status, body, delay in seconds)`.
        requests: The path and headers of each request, in order.
        url: The base URL of the server.
    """

    def __init__(self) -> None:
        """Start the server on a free port of 127.0.0.1 in a daemon thread."""
        self.routes: dict[str, tuple[int, bytes, float]] = {}
        self.requests: list[tuple[str, dict[str, str]]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            """Answer each GET from the routes table, and 404 for any other path."""

            def do_GET(self) -> None:
                """Send the canned answer of the request path."""
                fake.requests.append((self.path, dict(self.headers)))
                status, body, delay = fake.routes.get(self.path, (404, b"", 0.0))
                if delay:
                    time.sleep(delay)
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                """Keep the test output free of access logs."""

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(
            target=self.server.serve_forever, args=(0.05,), daemon=True
        )
        self.thread.start()

    def route(
        self, path: str, body: object, status: int = 200, delay: float = 0.0
    ) -> None:
        """Add one canned answer.

        Args:
            path: The request path, with any escapes exactly as sent.
            body: A JSON value, or `bytes` to send as they are.
            status: The HTTP status.
            delay: Seconds to wait before the answer.
        """
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.routes[path] = (status, raw, delay)

    def close(self) -> None:
        """Stop the server and close its socket."""
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRegistry]:
    """Give a running fake registry that every ecosystem points at, and no cache.

    Args:
        monkeypatch: The pytest monkeypatch fixture.

    Yields:
        The fake registry.
    """
    server = FakeRegistry()
    for ecosystem in registry.BASE_URLS:
        monkeypatch.setitem(registry.BASE_URLS, ecosystem, server.url)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    yield server
    server.close()


def _deadline(seconds: float = registry.RUN_BUDGET_S) -> float:
    """Give a deadline the given number of seconds from now.

    Args:
        seconds: The budget in seconds.

    Returns:
        A `time.monotonic()` value.
    """
    return time.monotonic() + seconds


def _utc(text: str) -> datetime:
    """Parse an ISO 8601 text into an aware UTC datetime.

    Args:
        text: The time stamp.

    Returns:
        The time in UTC.
    """
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def test_pypi_gives_the_earliest_upload_of_any_release(fake: FakeRegistry) -> None:
    """PyPI gives the earliest `upload_time_iso_8601` over every file of every release.

    arch: D7.8
    """
    fake.route(
        "/pypi/demo/json",
        {
            "releases": {
                "2.0": [{"upload_time_iso_8601": "2024-05-01T00:00:00.000000Z"}],
                "1.0": [
                    {"upload_time_iso_8601": "2023-02-03T04:05:06.000000Z"},
                    {"upload_time_iso_8601": "2023-02-04T00:00:00.000000Z"},
                ],
                "0.1": [],
            }
        },
    )
    answer = registry.first_release("pypi", "demo", deadline=_deadline())
    assert answer == _utc("2023-02-03T04:05:06+00:00")


def test_pypi_with_no_file_is_unknown(fake: FakeRegistry) -> None:
    """A PyPI project that has releases but no file is `Unknown`.

    arch: D7.8
    """
    fake.route("/pypi/empty/json", {"releases": {"1.0": []}})
    assert (
        registry.first_release("pypi", "empty", deadline=_deadline())
        == registry.Unknown()
    )


@pytest.mark.parametrize(
    ("ecosystem", "name"),
    [
        ("pypi", "nothing"),
        ("npm", "nothing"),
        ("crates", "nothing"),
        ("go", "example.com/nothing"),
        ("packagist", "acme/nothing"),
    ],
)
def test_404_is_unknown_in_every_ecosystem(
    fake: FakeRegistry, ecosystem: str, name: str
) -> None:
    """HTTP 404 gives `Unknown` in each ecosystem.

    arch: D7.8
    """
    assert (
        registry.first_release(ecosystem, name, deadline=_deadline())
        == registry.Unknown()
    )
    assert fake.requests, "the lookup sent no request"


def test_go_410_is_unknown(fake: FakeRegistry) -> None:
    """HTTP 410 from the Go module proxy gives `Unknown`.

    arch: D7.8
    """
    fake.route("/example.com/gone/@v/list", b"gone", status=410)
    assert (
        registry.first_release("go", "example.com/gone", deadline=_deadline())
        == registry.Unknown()
    )


@pytest.mark.parametrize("status", [500, 503])
def test_5xx_is_unreachable(fake: FakeRegistry, status: int) -> None:
    """A 5xx answer gives `Unreachable`.

    arch: D7.8
    """
    fake.route("/pypi/demo/json", b"", status=status)
    answer = registry.first_release("pypi", "demo", deadline=_deadline())
    assert isinstance(answer, registry.Unreachable)
    assert str(status) in answer.reason


def test_body_that_does_not_parse_is_unreachable(fake: FakeRegistry) -> None:
    """A body that is not JSON, or JSON of the wrong shape, gives `Unreachable`.

    arch: D7.8
    """
    fake.route("/api/v1/crates/broken", b"<html>not json</html>")
    fake.route("/api/v1/crates/shape", {"crate": "not an object"})
    for name in ("broken", "shape"):
        answer = registry.first_release("crates", name, deadline=_deadline())
        assert isinstance(answer, registry.Unreachable), name


def test_connection_error_is_unreachable(
    fake: FakeRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A port with no server gives `Unreachable`.

    arch: D7.8
    """
    closed = FakeRegistry()
    closed_url = closed.url
    closed.close()
    monkeypatch.setitem(registry.BASE_URLS, "npm", closed_url)
    answer = registry.first_release("npm", "left-pad", deadline=_deadline())
    assert isinstance(answer, registry.Unreachable)


def test_slow_answer_is_unreachable_inside_the_deadline(fake: FakeRegistry) -> None:
    """The call timeout is `min(CALL_TIMEOUT_S, deadline - now)`: a slow server gives `Unreachable`.

    arch: D7.8
    """
    fake.route("/pypi/slow/json", {"releases": {}}, delay=1.5)
    start = time.monotonic()
    answer = registry.first_release("pypi", "slow", deadline=_deadline(0.3))
    assert isinstance(answer, registry.Unreachable)
    assert time.monotonic() - start < 1.2


def test_name_after_the_deadline_is_time_budget(fake: FakeRegistry) -> None:
    """A name whose turn comes after the deadline is `Unreachable("time budget")`, with no request.

    arch: D7.8
    """
    answer = registry.first_release("pypi", "late", deadline=time.monotonic() - 0.01)
    assert answer == registry.Unreachable("time budget")
    assert fake.requests == []


def test_npm_scoped_name_sends_encoded_slash(fake: FakeRegistry) -> None:
    """The npm lookup gives `time.created`; a scoped name has its `/` sent as `%2f`.

    arch: D7.8
    """
    fake.route(
        "/@scope%2fpkg",
        {
            "time": {
                "created": "2021-06-07T08:09:10.123Z",
                "modified": "2025-01-01T00:00:00Z",
            }
        },
    )
    answer = registry.first_release("npm", "@scope/pkg", deadline=_deadline())
    assert answer == _utc("2021-06-07T08:09:10.123+00:00")
    assert fake.requests[0][0] == "/@scope%2fpkg"


def test_npm_long_record_hits_the_cap_and_is_old(
    fake: FakeRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record longer than `NPM_BYTE_CAP` is old: the answer is the Unix epoch.

    The body here is not even valid JSON after the cap, so a parse of the
    truncated body would give `Unreachable`; only the cap rule gives the
    epoch.

    arch: D7.8
    """
    monkeypatch.setattr(registry, "NPM_BYTE_CAP", 256)
    record = {
        "time": {"created": "2026-10-01T00:00:00Z"},
        "versions": {f"1.0.{n}": {} for n in range(200)},
    }
    fake.route("/big", record)
    fake.route("/small", {"time": {"created": "2026-10-01T00:00:00Z"}})
    assert registry.first_release("npm", "big", deadline=_deadline()) == EPOCH
    assert registry.first_release("npm", "small", deadline=_deadline()) == _utc(
        "2026-10-01T00:00:00+00:00"
    )


def test_crates_sends_the_user_agent(fake: FakeRegistry) -> None:
    """crates.io gives `crate.created_at`, and the call sends the trueup `User-Agent`.

    arch: D7.8
    """
    fake.route(
        "/api/v1/crates/serde",
        {"crate": {"created_at": "2014-12-05T20:20:39.487502+00:00"}},
    )
    answer = registry.first_release("crates", "serde", deadline=_deadline())
    assert answer == _utc("2014-12-05T20:20:39.487502+00:00")
    headers = {key.lower(): value for key, value in fake.requests[0][1].items()}
    assert headers["user-agent"] == f"trueup-install-guard ({registry.__version__})"


def test_go_escape_and_lowest_version(fake: FakeRegistry) -> None:
    """Go escapes capitals as `!` + lower case and takes the `.info` of the lowest semantic version.

    arch: D7.8
    """
    assert (
        registry.go_escape("github.com/BurntSushi/toml")
        == "github.com/!burnt!sushi/toml"
    )
    base = "/github.com/!burnt!sushi/toml/@v"
    fake.route(
        f"{base}/list", b"v1.2.0\nv0.10.0\nv0.9.0\nv0.9.0-rc.1\nv1.0.0\nnot-a-version\n"
    )
    fake.route(
        f"{base}/v0.9.0-rc.1.info",
        {"Version": "v0.9.0-rc.1", "Time": "2013-02-27T19:11:15Z"},
    )
    answer = registry.first_release(
        "go", "github.com/BurntSushi/toml", deadline=_deadline()
    )
    assert answer == _utc("2013-02-27T19:11:15+00:00")
    assert [path for path, _ in fake.requests] == [
        f"{base}/list",
        f"{base}/v0.9.0-rc.1.info",
    ]


def test_go_empty_list_uses_latest(fake: FakeRegistry) -> None:
    """An empty Go version list gives the `Time` of `@latest`.

    arch: D7.8
    """
    fake.route("/example.com/pseudo/@v/list", b"")
    fake.route(
        "/example.com/pseudo/@latest",
        {"Version": "v0.0.0-20260101-abc", "Time": "2026-01-01T00:00:00Z"},
    )
    answer = registry.first_release("go", "example.com/pseudo", deadline=_deadline())
    assert answer == _utc("2026-01-01T00:00:00+00:00")


def test_packagist_gives_the_earliest_version_time(fake: FakeRegistry) -> None:
    """Packagist gives the earliest `time` of the versions under `packages[<name>]`.

    arch: D7.8
    """
    fake.route(
        "/p2/acme/tool.json",
        {
            "packages": {
                "acme/tool": [
                    {"version": "2.0.0", "time": "2022-01-01T00:00:00+00:00"},
                    {"version": "1.0.0", "time": "2019-03-04T05:06:07+00:00"},
                ]
            }
        },
    )
    answer = registry.first_release("packagist", "acme/tool", deadline=_deadline())
    assert answer == _utc("2019-03-04T05:06:07+00:00")


def test_cache_hit_needs_no_request(
    fake: FakeRegistry, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second lookup inside the TTL is a cache hit; `Unknown` is cached as `null`.

    arch: D7.8
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    fake.route(
        "/api/v1/crates/serde", {"crate": {"created_at": "2014-12-05T20:20:39+00:00"}}
    )
    first = registry.first_release("crates", "serde", deadline=_deadline())
    missing = registry.first_release("crates", "nothing", deadline=_deadline())
    assert len(fake.requests) == 2
    cache = json.loads((tmp_path / "registry-cache.json").read_text(encoding="utf-8"))
    assert cache["crates:nothing"]["first"] is None
    assert _utc(cache["crates:serde"]["first"]) == first
    assert registry.first_release("crates", "serde", deadline=_deadline()) == first
    assert (
        registry.first_release("crates", "nothing", deadline=_deadline())
        == missing
        == registry.Unknown()
    )
    assert len(fake.requests) == 2
    assert sorted(path.name for path in tmp_path.iterdir()) == ["registry-cache.json"]


def test_cache_entry_older_than_ttl_is_looked_up_again(
    fake: FakeRegistry, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An entry older than `CACHE_TTL_S` is not the answer; the lookup runs and replaces it.

    arch: D7.8
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    stale = {
        "crates:serde": {
            "t": time.time() - registry.CACHE_TTL_S - 10,
            "first": "2000-01-01T00:00:00+00:00",
        }
    }
    (tmp_path / "registry-cache.json").write_text(json.dumps(stale), encoding="utf-8")
    fake.route(
        "/api/v1/crates/serde", {"crate": {"created_at": "2014-12-05T20:20:39+00:00"}}
    )
    answer = registry.first_release("crates", "serde", deadline=_deadline())
    assert answer == _utc("2014-12-05T20:20:39+00:00")
    assert len(fake.requests) == 1
    cache = json.loads((tmp_path / "registry-cache.json").read_text(encoding="utf-8"))
    assert time.time() - cache["crates:serde"]["t"] < 60


def test_unreachable_is_not_cached(
    fake: FakeRegistry, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`Unreachable` never goes into the cache; the next call asks again.

    arch: D7.8
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    fake.route("/pypi/demo/json", b"", status=502)
    assert isinstance(
        registry.first_release("pypi", "demo", deadline=_deadline()),
        registry.Unreachable,
    )
    assert isinstance(
        registry.first_release("pypi", "demo", deadline=_deadline()),
        registry.Unreachable,
    )
    assert len(fake.requests) == 2
    assert not (tmp_path / "registry-cache.json").exists()


def test_corrupt_cache_file_is_treated_as_empty(
    fake: FakeRegistry, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cache file that does not parse is empty: the lookup runs and writes a good file.

    arch: D7.8
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    (tmp_path / "registry-cache.json").write_text("{not json", encoding="utf-8")
    fake.route("/@scope%2fpkg", {"time": {"created": "2021-06-07T08:09:10Z"}})
    answer = registry.first_release("npm", "@scope/pkg", deadline=_deadline())
    assert answer == _utc("2021-06-07T08:09:10+00:00")
    cache = json.loads((tmp_path / "registry-cache.json").read_text(encoding="utf-8"))
    assert set(cache) == {"npm:@scope/pkg"}


@pytest.mark.parametrize("value", [None, ""])
def test_no_cache_without_plugin_data(
    fake: FakeRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    value: str | None,
) -> None:
    """With `$CLAUDE_PLUGIN_DATA` unset or empty there is no cache: no file, and every call asks.

    arch: D7.8
    """
    if value is None:
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", value)
    monkeypatch.chdir(tmp_path)
    fake.route(
        "/pypi/demo/json",
        {"releases": {"1.0": [{"upload_time_iso_8601": "2020-01-01T00:00:00Z"}]}},
    )
    assert registry.cache_path() is None
    registry.first_release("pypi", "demo", deadline=_deadline())
    registry.first_release("pypi", "demo", deadline=_deadline())
    assert len(fake.requests) == 2
    assert list(tmp_path.iterdir()) == []


def _network_imports(source: str) -> set[str]:
    """Give the network modules that one Python source imports.

    Args:
        source: The Python source text.

    Returns:
        The names among `urllib.request`, `http.client` and `socket` that
        the source imports, in any import form.
    """
    banned = {"urllib.request", "http.client", "socket"}
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found |= {
                    name
                    for name in banned
                    if alias.name == name or alias.name.startswith(name + ".")
                }
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module = node.module
            found |= {
                name
                for name in banned
                if module == name or module.startswith(name + ".")
            }
            for alias in node.names:
                found |= {name for name in banned if f"{module}.{alias.name}" == name}
    return found


def test_only_registry_imports_network_modules() -> None:
    """Only `trueup/registry.py` imports `urllib.request`, `http.client` or `socket`.

    The check also proves it finds the imports in `registry.py`, so an
    empty result elsewhere is not a blind scan.

    arch: I-28
    """
    offenders = {}
    for path in sorted(TRUEUP_DIR.rglob("*.py")):
        found = _network_imports(path.read_text(encoding="utf-8"))
        if path.name == "registry.py" and path.parent == TRUEUP_DIR:
            assert "urllib.request" in found
            continue
        if found:
            offenders[str(path.relative_to(TRUEUP_DIR))] = sorted(found)
    assert offenders == {}


@pytest.mark.parametrize(
    "source",
    [
        "import socket",
        "from urllib import request",
        "from http import client",
        "import urllib.request as u",
    ],
)
def test_network_import_scan_sees_every_form(source: str) -> None:
    """The I-28 scan finds each import form of a network module.

    arch: I-28
    """
    assert _network_imports(source)
