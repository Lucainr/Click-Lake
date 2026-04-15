from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib import error, parse, request


@dataclass(frozen=True)
class UploadPaths:
    batch_dir: Path
    checkpoint_file: Path
    env_file: Path


@dataclass(frozen=True)
class DatabricksConfig:
    host: str
    token: str
    volume_path: str


class UploadError(Exception):
    pass


def _resolve_paths() -> UploadPaths:
    server_dir = Path(__file__).resolve().parents[1]
    return UploadPaths(
        batch_dir=server_dir / "out" / "bronze_batches",
        checkpoint_file=server_dir / "data" / "checkpoints" / "bronze_upload_state.json",
        env_file=server_dir / ".env",
    )


def _normalize_host(host: str) -> str:
    cleaned = host.strip().rstrip("/")
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        raise UploadError("DATABRICKS_HOST must start with http:// or https://")
    return cleaned


def _normalize_volume_path(path: str) -> str:
    cleaned = path.strip().rstrip("/")
    if not cleaned.startswith("/Volumes/"):
        raise UploadError("DATABRICKS_VOLUME_PATH must start with /Volumes/")
    return cleaned


def _load_dotenv_if_exists(env_file: Path) -> None:
    if not env_file.exists():
        return

    with env_file.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            if not key:
                continue

            # Keep shell-exported env values as higher priority.
            if key not in os.environ:
                os.environ[key] = value


def _load_config_from_env(env_file: Path) -> DatabricksConfig:
    _load_dotenv_if_exists(env_file)

    host = os.getenv("DATABRICKS_HOST", "")
    token = os.getenv("DATABRICKS_TOKEN", "")
    volume_path = os.getenv("DATABRICKS_VOLUME_PATH", "")

    missing: list[str] = []
    if not host:
        missing.append("DATABRICKS_HOST")
    if not token:
        missing.append("DATABRICKS_TOKEN")
    if not volume_path:
        missing.append("DATABRICKS_VOLUME_PATH")

    if missing:
        raise UploadError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return DatabricksConfig(
        host=_normalize_host(host),
        token=token.strip(),
        volume_path=_normalize_volume_path(volume_path),
    )


def _load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    uploaded_files = data.get("uploaded_files", [])
    if not isinstance(uploaded_files, list):
        raise UploadError("checkpoint uploaded_files must be a list")

    normalized: set[str] = set()
    for item in uploaded_files:
        if not isinstance(item, str):
            raise UploadError("checkpoint uploaded_files items must be strings")
        normalized.add(item)
    return normalized


def _save_checkpoint(path: Path, uploaded_files: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"uploaded_files": sorted(uploaded_files)}

    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    temp.replace(path)


def _discover_batch_files(batch_dir: Path) -> list[Path]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        [p for p in batch_dir.glob("*.jsonl") if p.is_file()],
        key=lambda p: p.name,
    )


def _quoted_path(path: str) -> str:
    return parse.quote(path, safe="/")


def _request(
    *,
    method: str,
    url: str,
    token: str,
    data: bytes | None = None,
    content_type: str | None = None,
) -> None:
    req = request.Request(url=url, method=method, data=data)
    req.add_header("Authorization", f"Bearer {token}")
    if content_type:
        req.add_header("Content-Type", content_type)

    try:
        with request.urlopen(req, timeout=30) as _:
            return
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise UploadError(f"HTTP {exc.code} for {url}: {body}") from exc
    except error.URLError as exc:
        raise UploadError(f"Failed request to {url}: {exc.reason}") from exc


def _ensure_volume_directory(config: DatabricksConfig) -> None:
    # Databricks Files API for Volumes directories
    dir_path = f"{config.volume_path}/"
    url = f"{config.host}/api/2.0/fs/directories{_quoted_path(dir_path)}"
    try:
        _request(method="PUT", url=url, token=config.token)
    except UploadError as exc:
        message = str(exc)
        if "HTTP 409" in message:
            return
        raise


def _upload_file_to_volume(config: DatabricksConfig, local_file: Path) -> None:
    remote_path = f"{config.volume_path}/{local_file.name}"
    url = (
        f"{config.host}/api/2.0/fs/files{_quoted_path(remote_path)}"
        f"?overwrite=true"
    )
    data = local_file.read_bytes()
    _request(
        method="PUT",
        url=url,
        token=config.token,
        data=data,
        content_type="application/octet-stream",
    )


def upload_bronze_batches() -> int:
    paths = _resolve_paths()
    config = _load_config_from_env(paths.env_file)

    uploaded = _load_checkpoint(paths.checkpoint_file)
    all_batch_files = _discover_batch_files(paths.batch_dir)
    pending_files = [p for p in all_batch_files if p.name not in uploaded]

    if not pending_files:
        print("No new batch files to upload.")
        return 0

    _ensure_volume_directory(config)

    for batch_file in pending_files:
        try:
            _upload_file_to_volume(config, batch_file)
        except UploadError as exc:
            print(f"Failed to upload {batch_file.name}: {exc}")
            return 1

        uploaded.add(batch_file.name)
        _save_checkpoint(paths.checkpoint_file, uploaded)
        print(f"Uploaded {batch_file.name}")

    return 0


def main() -> int:
    try:
        return upload_bronze_batches()
    except UploadError as exc:
        print(f"Upload configuration error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
