from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib import error, parse, request


@dataclass(frozen=True)
class UploadPaths:
    server_dir: Path
    checkpoint_file: Path
    env_file: Path


@dataclass(frozen=True)
class DatabricksConfig:
    host: str
    token: str
    volume_path_direct: str
    volume_path_kafka: str


@dataclass(frozen=True)
class UploadSource:
    source_id: str
    local_root: Path
    checkpoint_prefix: str
    remote_base_path: str
    recursive: bool


@dataclass(frozen=True)
class PendingUpload:
    source: UploadSource
    relative_path: str
    checkpoint_key: str
    local_file: Path
    remote_path: str


class UploadError(Exception):
    pass


def _resolve_paths() -> UploadPaths:
    server_dir = Path(__file__).resolve().parents[1]
    return UploadPaths(
        server_dir=server_dir,
        checkpoint_file=server_dir / "data" / "checkpoints" / "bronze_upload_state.json",
        env_file=server_dir / ".env",
    )


def _normalize_host(host: str) -> str:
    cleaned = host.strip().rstrip("/")
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        raise UploadError("DATABRICKS_HOST must start with http:// or https://")
    return cleaned


def _normalize_volume_path(path: str, env_name: str) -> str:
    cleaned = path.strip().rstrip("/")
    if not cleaned.startswith("/Volumes/"):
        raise UploadError(f"{env_name} must start with /Volumes/")
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

            if key not in os.environ:
                os.environ[key] = value


def _load_config_from_env(env_file: Path) -> DatabricksConfig:
    _load_dotenv_if_exists(env_file)

    host = os.getenv("DATABRICKS_HOST", "")
    token = os.getenv("DATABRICKS_TOKEN", "")
    legacy_base = os.getenv("DATABRICKS_VOLUME_PATH", "")
    volume_direct = os.getenv("DATABRICKS_VOLUME_PATH_DIRECT", "")
    volume_kafka = os.getenv("DATABRICKS_VOLUME_PATH_KAFKA", "")

    if legacy_base and not volume_direct:
        volume_direct = f"{legacy_base.rstrip('/')}/direct"
    if legacy_base and not volume_kafka:
        volume_kafka = f"{legacy_base.rstrip('/')}/kafka"

    missing: list[str] = []
    if not host:
        missing.append("DATABRICKS_HOST")
    if not token:
        missing.append("DATABRICKS_TOKEN")
    if not volume_direct:
        missing.append("DATABRICKS_VOLUME_PATH_DIRECT")
    if not volume_kafka:
        missing.append("DATABRICKS_VOLUME_PATH_KAFKA")

    if missing:
        raise UploadError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return DatabricksConfig(
        host=_normalize_host(host),
        token=token.strip(),
        volume_path_direct=_normalize_volume_path(
            volume_direct, "DATABRICKS_VOLUME_PATH_DIRECT"
        ),
        volume_path_kafka=_normalize_volume_path(
            volume_kafka, "DATABRICKS_VOLUME_PATH_KAFKA"
        ),
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


def _discover_source_files(source: UploadSource) -> list[str]:
    source.local_root.mkdir(parents=True, exist_ok=True)
    if source.recursive:
        files = [p for p in source.local_root.rglob("*.jsonl") if p.is_file()]
    else:
        files = [p for p in source.local_root.glob("*.jsonl") if p.is_file()]

    relatives = [p.relative_to(source.local_root).as_posix() for p in files]
    relatives.sort()
    return relatives


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


def _ensure_volume_directory(*, host: str, token: str, directory_path: str) -> None:
    dir_path = f"{directory_path.rstrip('/')}/"
    url = f"{host}/api/2.0/fs/directories{_quoted_path(dir_path)}"
    try:
        _request(method="PUT", url=url, token=token)
    except UploadError as exc:
        message = str(exc)
        if "HTTP 409" in message:
            return
        raise


def _upload_file_to_volume(
    *,
    host: str,
    token: str,
    local_file: Path,
    remote_path: str,
) -> None:
    url = (
        f"{host}/api/2.0/fs/files{_quoted_path(remote_path)}"
        f"?overwrite=true"
    )
    data = local_file.read_bytes()
    _request(
        method="PUT",
        url=url,
        token=token,
        data=data,
        content_type="application/octet-stream",
    )


def _build_sources(paths: UploadPaths, config: DatabricksConfig) -> list[UploadSource]:
    return [
        UploadSource(
            source_id="direct",
            local_root=paths.server_dir / "out" / "bronze_batches",
            checkpoint_prefix="out/bronze_batches",
            remote_base_path=config.volume_path_direct,
            recursive=False,
        ),
        UploadSource(
            source_id="kafka",
            local_root=paths.server_dir / "data" / "bronze_batches_kafka",
            checkpoint_prefix="data/bronze_batches_kafka",
            remote_base_path=config.volume_path_kafka,
            recursive=True,
        ),
    ]


def _build_pending_uploads(
    sources: list[UploadSource], uploaded_files: set[str]
) -> list[PendingUpload]:
    pending: list[PendingUpload] = []

    for source in sources:
        discovered = _discover_source_files(source)
        for relative in discovered:
            checkpoint_key = f"{source.checkpoint_prefix}/{relative}"
            basename_uploaded = source.source_id == "direct" and Path(relative).name in uploaded_files
            if checkpoint_key in uploaded_files or basename_uploaded:
                continue

            local_file = source.local_root / Path(relative)
            remote_path = f"{source.remote_base_path}/{relative}".replace("//", "/")
            pending.append(
                PendingUpload(
                    source=source,
                    relative_path=relative,
                    checkpoint_key=checkpoint_key,
                    local_file=local_file,
                    remote_path=remote_path,
                )
            )

    pending.sort(key=lambda item: (item.source.source_id, item.relative_path))
    return pending


def upload_bronze_batches() -> int:
    paths = _resolve_paths()
    config = _load_config_from_env(paths.env_file)
    sources = _build_sources(paths, config)

    uploaded = _load_checkpoint(paths.checkpoint_file)
    pending_uploads = _build_pending_uploads(sources, uploaded)

    if not pending_uploads:
        print("No new batch files to upload.")
        return 0

    ensured_directories: set[str] = set()

    for item in pending_uploads:
        remote_parent = str(Path(item.remote_path).parent).replace("\\", "/")
        if remote_parent not in ensured_directories:
            _ensure_volume_directory(
                host=config.host, token=config.token, directory_path=remote_parent
            )
            ensured_directories.add(remote_parent)

        try:
            _upload_file_to_volume(
                host=config.host,
                token=config.token,
                local_file=item.local_file,
                remote_path=item.remote_path,
            )
        except UploadError as exc:
            print(
                "Failed upload "
                f"source={item.source.source_id} file={item.relative_path} "
                f"remote={item.remote_path}: {exc}"
            )
            return 1

        uploaded.add(item.checkpoint_key)
        _save_checkpoint(paths.checkpoint_file, uploaded)
        print(
            "Uploaded "
            f"source={item.source.source_id} "
            f"file={item.relative_path} "
            f"remote={item.remote_path}"
        )

    return 0


def main() -> int:
    try:
        return upload_bronze_batches()
    except UploadError as exc:
        print(f"Upload configuration error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
