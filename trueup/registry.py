"""Package registry lookups for the install guard: the only network code (D7.8, I-28).

`first_release` gives the date on which a package first appeared on its
registry, `Unknown` when the registry does not have the package, or
`Unreachable` when the registry did not give a usable answer in time.
There is one lookup per ecosystem: pypi, npm, crates, go and packagist.

Each call has a timeout of `min(CALL_TIMEOUT_S, deadline - now)`, where
`deadline` is a `time.monotonic()` value that the caller sets. The npm
lookup reads at most `NPM_BYTE_CAP` bytes. When `$CLAUDE_PLUGIN_DATA` is
set, answers other than `Unreachable` go into
`$CLAUDE_PLUGIN_DATA/registry-cache.json` for `CACHE_TTL_S` seconds.

No other module in `trueup/` opens a network connection (I-28). Tests
patch `BASE_URLS` to a local server; there is no setting for it.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from trueup import __version__


@dataclass(frozen=True)
class Unknown:
    """The registry does not have the package (HTTP 404, or 410 for go)."""


@dataclass(frozen=True)
class Unreachable:
    """The registry gave no usable answer.

    Attributes:
        reason: A short text that tells why, for example `time budget`.
    """

    reason: str


Answer = datetime | Unknown | Unreachable

BASE_URLS: dict[str, str] = {
    "pypi": "https://pypi.org",
    "npm": "https://registry.npmjs.org",
    "crates": "https://crates.io",
    "go": "https://proxy.golang.org",
    "packagist": "https://repo.packagist.org",
}
CALL_TIMEOUT_S = 2.0
RUN_BUDGET_S = 5.0
CACHE_TTL_S = 86400
NPM_BYTE_CAP = 1 << 20

_CHUNK = 65536
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_SEMVER = re.compile(r"v(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")


class _NoAnswer(Exception):
    """A lookup step that ends in `Unreachable`; the message is the reason."""


class _Missing(Exception):
    """A lookup step that ends in `Unknown`."""


@dataclass(frozen=True)
class _Response:
    """One HTTP answer.

    Attributes:
        status: The HTTP status code.
        body: The bytes that were read.
        capped: True when the read stopped at the byte cap.
    """

    status: int
    body: bytes
    capped: bool


def _get(
    url: str,
    deadline: float,
    *,
    cap: int | None = None,
    headers: dict[str, str] | None = None,
) -> _Response:
    """Send one GET request, and read the body inside the call timeout.

    Args:
        url: The full URL. It must use `http` or `https` and start with
            one of the current `BASE_URLS` values.
        deadline: The `time.monotonic()` value after which no call starts.
        cap: The maximum number of body bytes to read, or `None` for all.
        headers: Extra request headers.

    Returns:
        The status, the body and the cap flag. An HTTP error status gives a
        response with an empty body.

    Raises:
        _NoAnswer: The time budget is spent, the call timed out, or the
            connection failed.
    """
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise _NoAnswer("bad URL")
    if not any(url.startswith(base) for base in BASE_URLS.values()):
        raise _NoAnswer("bad URL")
    timeout = min(CALL_TIMEOUT_S, deadline - time.monotonic())
    if timeout <= 0:
        raise _NoAnswer("time budget")
    call_end = time.monotonic() + timeout
    request = urllib.request.Request(url, headers=headers or {})  # noqa: S310  # reason: url is checked above to start with a current BASE_URLS value
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # reason: url is checked above to start with a current BASE_URLS value
            chunks: list[bytes] = []
            size = 0
            while cap is None or size < cap:
                want = _CHUNK if cap is None else min(_CHUNK, cap - size)
                chunk = response.read(want)
                if not chunk:
                    return _Response(response.status, b"".join(chunks), False)
                chunks.append(chunk)
                size += len(chunk)
                if time.monotonic() > call_end:
                    raise _NoAnswer("timeout")
            return _Response(response.status, b"".join(chunks), True)
    except urllib.error.HTTPError as error:
        error.close()
        return _Response(error.code, b"", False)
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        OSError,
        ValueError,
    ) as error:
        raise _NoAnswer(f"connection failed: {type(error).__name__}") from error


def _json(
    url: str,
    deadline: float,
    missing: tuple[int, ...] = (404,),
    headers: dict[str, str] | None = None,
) -> object:
    """GET a URL and parse its JSON body.

    Args:
        url: The full URL.
        deadline: The `time.monotonic()` deadline.
        missing: The status codes that mean the package does not exist.
        headers: Extra request headers.

    Returns:
        The parsed JSON value.

    Raises:
        _Missing: The status is one of `missing`.
        _NoAnswer: Any other status that is not 200, or a body that does not parse.
    """
    response = _get(url, deadline, headers=headers)
    _status(response, missing)
    try:
        return json.loads(response.body)
    except ValueError as error:
        raise _NoAnswer("bad answer") from error


def _status(response: _Response, missing: tuple[int, ...]) -> None:
    """Map a status that is not 200 to an exception.

    Args:
        response: The HTTP answer.
        missing: The status codes that mean the package does not exist.

    Raises:
        _Missing: The status is one of `missing`.
        _NoAnswer: Any other status that is not 200.
    """
    if response.status in missing:
        raise _Missing
    if response.status != 200:
        raise _NoAnswer(f"HTTP {response.status}")


def _when(value: object) -> datetime:
    """Parse an ISO 8601 time stamp into an aware UTC datetime.

    Args:
        value: The value from the registry answer.

    Returns:
        The time in UTC. A value with no zone is read as UTC.

    Raises:
        _NoAnswer: The value is not an ISO 8601 string.
    """
    if not isinstance(value, str):
        raise _NoAnswer("bad answer")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as error:
        raise _NoAnswer("bad answer") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _pypi(name: str, deadline: float) -> datetime:
    """Give the earliest upload time of any file of any release on PyPI.

    Args:
        name: The project name.
        deadline: The `time.monotonic()` deadline.

    Returns:
        The earliest `upload_time_iso_8601`.

    Raises:
        _Missing: PyPI does not have the project, or it has no file.
        _NoAnswer: PyPI gave no usable answer.
    """
    url = f"{BASE_URLS['pypi']}/pypi/{urllib.parse.quote(name, safe='')}/json"
    data = _json(url, deadline)
    releases = data.get("releases") if isinstance(data, dict) else None
    if not isinstance(releases, dict):
        raise _NoAnswer("bad answer")
    times = [
        _when(item.get("upload_time_iso_8601"))
        for files in releases.values()
        if isinstance(files, list)
        for item in files
        if isinstance(item, dict)
    ]
    if not times:
        raise _Missing
    return min(times)


def _npm(name: str, deadline: float) -> datetime:
    """Give the `time.created` of an npm package, or the epoch for a long record.

    A young package has a short record. When the read stops at
    `NPM_BYTE_CAP`, the record is long, so the package is old, and the
    answer is the Unix epoch. A body of exactly `NPM_BYTE_CAP` bytes also
    counts as long.

    Args:
        name: The package name; a scoped name has its `/` sent as `%2f`.
        deadline: The `time.monotonic()` deadline.

    Returns:
        The creation time, or the Unix epoch.

    Raises:
        _Missing: npm does not have the package.
        _NoAnswer: npm gave no usable answer.
    """
    path = urllib.parse.quote(name, safe="@").replace("%2F", "%2f")
    response = _get(f"{BASE_URLS['npm']}/{path}", deadline, cap=NPM_BYTE_CAP)
    _status(response, (404,))
    if response.capped:
        return _EPOCH
    try:
        data = json.loads(response.body)
    except ValueError as error:
        raise _NoAnswer("bad answer") from error
    times = data.get("time") if isinstance(data, dict) else None
    if not isinstance(times, dict):
        raise _NoAnswer("bad answer")
    return _when(times.get("created"))


def _crates(name: str, deadline: float) -> datetime:
    """Give the `crate.created_at` of a crate on crates.io.

    Args:
        name: The crate name.
        deadline: The `time.monotonic()` deadline.

    Returns:
        The creation time.

    Raises:
        _Missing: crates.io does not have the crate.
        _NoAnswer: crates.io gave no usable answer.
    """
    url = f"{BASE_URLS['crates']}/api/v1/crates/{urllib.parse.quote(name, safe='')}"
    headers = {"User-Agent": f"trueup-install-guard ({__version__})"}
    data = _json(url, deadline, headers=headers)
    crate = data.get("crate") if isinstance(data, dict) else None
    if not isinstance(crate, dict):
        raise _NoAnswer("bad answer")
    return _when(crate.get("created_at"))


def go_escape(path: str) -> str:
    """Escape a module path or a version for the Go module proxy.

    Each capital letter becomes `!` and the lower-case letter.

    Args:
        path: The module path or version, for example `github.com/Foo/bar`.

    Returns:
        The escaped text, for example `github.com/!foo/bar`.
    """
    escaped = re.sub(r"[A-Z]", lambda match: "!" + match.group(0).lower(), path)
    return urllib.parse.quote(escaped, safe="/!~")


def _semver_key(version: str) -> tuple | None:
    """Give a sort key that orders Go versions by semantic version precedence.

    Args:
        version: A version such as `v1.2.3` or `v0.0.0-20190101000000-abcdef`.

    Returns:
        The key, or `None` when the text is not a semantic version.
    """
    match = _SEMVER.fullmatch(version)
    if match is None:
        return None
    major, minor, patch, pre = match.groups()
    core = (int(major), int(minor), int(patch))
    if pre is None:
        return (*core, 1, ())
    parts = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in pre.split(".")
    )
    return (*core, 0, parts)


def _go(module: str, deadline: float) -> datetime:
    """Give the time of the lowest version of a Go module on the module proxy.

    Args:
        module: The module path.
        deadline: The `time.monotonic()` deadline.

    Returns:
        The `Time` of the lowest listed version, or of `@latest` when the
        list is empty.

    Raises:
        _Missing: The proxy does not have the module (404 or 410).
        _NoAnswer: The proxy gave no usable answer.
    """
    base = f"{BASE_URLS['go']}/{go_escape(module)}/@v"
    listing = _get(f"{base}/list", deadline)
    _status(listing, (404, 410))
    try:
        lines = listing.body.decode("utf-8").split()
    except UnicodeDecodeError as error:
        raise _NoAnswer("bad answer") from error
    keyed = [(key, line) for line in lines if (key := _semver_key(line)) is not None]
    if keyed:
        lowest = min(keyed)[1]
        info = _json(f"{base}/{go_escape(lowest)}.info", deadline, missing=())
    else:
        latest = f"{BASE_URLS['go']}/{go_escape(module)}/@latest"
        info = _json(latest, deadline, missing=(404, 410))
    if not isinstance(info, dict):
        raise _NoAnswer("bad answer")
    return _when(info.get("Time"))


def _packagist(name: str, deadline: float) -> datetime:
    """Give the earliest version time of a package on Packagist.

    Args:
        name: The package name, `<vendor>/<package>`.
        deadline: The `time.monotonic()` deadline.

    Returns:
        The earliest `time` of the versions under `packages[<name>]`.

    Raises:
        _Missing: Packagist does not have the package, the name has no
            vendor part, or the package has no version.
        _NoAnswer: Packagist gave no usable answer.
    """
    name = name.lower()
    vendor, _, package = name.partition("/")
    if not vendor or not package or "/" in package:
        raise _Missing
    quoted = (
        f"{urllib.parse.quote(vendor, safe='')}/{urllib.parse.quote(package, safe='')}"
    )
    data = _json(f"{BASE_URLS['packagist']}/p2/{quoted}.json", deadline)
    packages = data.get("packages") if isinstance(data, dict) else None
    if not isinstance(packages, dict):
        raise _NoAnswer("bad answer")
    versions = packages.get(name)
    if not isinstance(versions, list):
        raise _Missing
    times = [
        _when(item["time"])
        for item in versions
        if isinstance(item, dict) and "time" in item
    ]
    if not times:
        raise _Missing
    return min(times)


_LOOKUPS: dict[str, Callable[[str, float], datetime]] = {
    "pypi": _pypi,
    "npm": _npm,
    "crates": _crates,
    "go": _go,
    "packagist": _packagist,
}


def cache_path() -> Path | None:
    """Give the cache file, or `None` when there is no cache (I-14).

    Returns:
        `$CLAUDE_PLUGIN_DATA/registry-cache.json`, or `None` when
        `$CLAUDE_PLUGIN_DATA` is not set or empty.
    """
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return None
    return Path(data) / "registry-cache.json"


def _read_cache(path: Path) -> dict:
    """Read the cache file. A file that is missing or does not parse is empty.

    Args:
        path: The cache file.

    Returns:
        The JSON object, or an empty dict.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cached(path: Path, key: str) -> datetime | Unknown | None:
    """Give the cached answer for one key when it is younger than `CACHE_TTL_S`.

    Args:
        path: The cache file.
        key: `<ecosystem>:<name>`.

    Returns:
        The cached date, `Unknown` for a cached `null`, or `None` when no
        fresh, valid entry exists.
    """
    entry = _read_cache(path).get(key)
    if not isinstance(entry, dict):
        return None
    checked = entry.get("t")
    if not isinstance(checked, (int, float)) or isinstance(checked, bool):
        return None
    if not 0 <= time.time() - checked < CACHE_TTL_S:
        return None
    if "first" not in entry:
        return None
    first = entry["first"]
    if first is None:
        return Unknown()
    try:
        return _when(first)
    except _NoAnswer:
        return None


def _store(path: Path, key: str, answer: datetime | Unknown) -> None:
    """Write one answer into the cache file through a temporary file and `os.replace`.

    A write that fails leaves the cache as it was; the cache is only a
    speed-up.

    Args:
        path: The cache file.
        key: `<ecosystem>:<name>`.
        answer: The answer to keep; `Unknown` is kept as `null`.
    """
    data = _read_cache(path)
    first = None if isinstance(answer, Unknown) else answer.isoformat()
    data[key] = {"t": time.time(), "first": first}
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".registry-cache.",
            delete=False,
        ) as handle:
            json.dump(data, handle, sort_keys=True)
            temporary = handle.name
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def first_release(ecosystem: str, name: str, *, deadline: float) -> Answer:
    """Give the date on which a package first appeared on its registry (arch: D7.8).

    A fresh cache entry is the answer and needs no network. Otherwise the
    lookup runs; a name whose turn comes after `deadline` is
    `Unreachable("time budget")`. `Unreachable` is never cached.

    Args:
        ecosystem: One of the keys of `BASE_URLS`.
        name: The package name, with no version.
        deadline: The `time.monotonic()` value after which no call starts.
            The hook sets it to its start plus `RUN_BUDGET_S`.

    Returns:
        An aware UTC datetime, `Unknown`, or `Unreachable`.

    Raises:
        ValueError: `ecosystem` is not a known ecosystem.
    """
    lookup = _LOOKUPS.get(ecosystem)
    if lookup is None:
        raise ValueError(f"unknown ecosystem: {ecosystem}")
    key = f"{ecosystem}:{name}"
    path = cache_path()
    if path is not None:
        hit = _cached(path, key)
        if hit is not None:
            return hit
    if deadline - time.monotonic() <= 0:
        return Unreachable("time budget")
    answer: datetime | Unknown
    try:
        answer = lookup(name, deadline)
    except _Missing:
        answer = Unknown()
    except _NoAnswer as error:
        return Unreachable(str(error))
    if path is not None:
        _store(path, key, answer)
    return answer
