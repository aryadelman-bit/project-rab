from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from urllib import error, parse, request


@dataclass(frozen=True)
class GitHubBackupConfig:
    token: str
    repo: str
    path: str = "rab-state/rab.db"
    branch: str = "main"


class CloudBackupError(RuntimeError):
    pass


def _contents_url(config: GitHubBackupConfig) -> str:
    encoded_path = parse.quote(config.path.strip("/"), safe="/")
    return f"https://api.github.com/repos/{config.repo}/contents/{encoded_path}"


def _github_request(config: GitHubBackupConfig, method: str, url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(config.path) from exc
        message = exc.read().decode("utf-8", errors="replace")
        raise CloudBackupError(f"GitHub API error {exc.code}: {message}") from exc
    except error.URLError as exc:
        raise CloudBackupError(f"Gagal menghubungi GitHub API: {exc.reason}") from exc


def download_database(config: GitHubBackupConfig, target_path: Path) -> bool:
    url = f"{_contents_url(config)}?ref={parse.quote(config.branch)}"
    try:
        metadata = _github_request(config, "GET", url)
    except FileNotFoundError:
        return False

    encoded_content = metadata.get("content")
    if not encoded_content:
        raise CloudBackupError("File backup GitHub tidak berisi content.")

    database_bytes = base64.b64decode(encoded_content)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_suffix(f"{target_path.suffix}.download")
    temporary_path.write_bytes(database_bytes)
    temporary_path.replace(target_path)
    return True


def upload_database(config: GitHubBackupConfig, source_path: Path, message: str) -> None:
    if not source_path.exists():
        raise CloudBackupError(f"Database lokal tidak ditemukan: {source_path}")

    current_sha: str | None = None
    url = f"{_contents_url(config)}?ref={parse.quote(config.branch)}"
    try:
        metadata = _github_request(config, "GET", url)
        current_sha = metadata.get("sha")
    except FileNotFoundError:
        current_sha = None

    payload = {
        "message": message,
        "content": base64.b64encode(source_path.read_bytes()).decode("ascii"),
        "branch": config.branch,
    }
    if current_sha:
        payload["sha"] = current_sha

    _github_request(config, "PUT", _contents_url(config), payload)
