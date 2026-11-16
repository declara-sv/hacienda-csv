"""File storage for uploads and generated artifacts (local disk or Azure Blob)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import Settings

CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class StoredFileReference:
    provider: str
    container: str
    path: str


class FileStorage(Protocol):
    provider_name: str

    def save(self, container: str, path: str, content: bytes, content_type: str) -> StoredFileReference: ...

    def read(self, file: StoredFileReference) -> bytes | None:
        """Whole file, or None when it does not exist."""
        ...

    def iter_chunks(self, file: StoredFileReference) -> Iterator[bytes] | None:
        """Streamed file, or None when it does not exist."""
        ...

    def delete(self, file: StoredFileReference) -> None: ...


class LocalFileStorage:
    provider_name = "Local"

    def __init__(self, root_path: str | Path) -> None:
        self._root = Path(root_path).resolve()

    def _full_path(self, container: str, path: str) -> Path:
        full = (self._root / container / path).resolve()
        if not full.is_relative_to(self._root):
            raise ValueError("Ruta de archivo inválida.")
        return full

    def save(self, container: str, path: str, content: bytes, content_type: str) -> StoredFileReference:
        full = self._full_path(container, path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return StoredFileReference(self.provider_name, container, path)

    def read(self, file: StoredFileReference) -> bytes | None:
        full = self._full_path(file.container, file.path)
        return full.read_bytes() if full.is_file() else None

    def iter_chunks(self, file: StoredFileReference) -> Iterator[bytes] | None:
        full = self._full_path(file.container, file.path)
        if not full.is_file():
            return None

        def generate() -> Iterator[bytes]:
            with full.open("rb") as handle:
                while chunk := handle.read(CHUNK_SIZE):
                    yield chunk

        return generate()

    def delete(self, file: StoredFileReference) -> None:
        full = self._full_path(file.container, file.path)
        full.unlink(missing_ok=True)


class AzureBlobFileStorage:
    provider_name = "AzureBlob"

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string
        self._service = None

    def _client(self):
        if not self._connection_string.strip():
            raise RuntimeError("STORAGE_AZURE_BLOB_CONNECTION_STRING no está configurado.")
        if self._service is None:
            from azure.storage.blob import BlobServiceClient

            self._service = BlobServiceClient.from_connection_string(self._connection_string)
        return self._service

    def save(self, container: str, path: str, content: bytes, content_type: str) -> StoredFileReference:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        container_client = self._client().get_container_client(container)
        with contextlib.suppress(ResourceExistsError):
            container_client.create_container()
        container_client.upload_blob(
            path, content, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return StoredFileReference(self.provider_name, container, path)

    def read(self, file: StoredFileReference) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._client().get_blob_client(file.container, file.path)
        try:
            return blob.download_blob().readall()
        except ResourceNotFoundError:
            return None

    def iter_chunks(self, file: StoredFileReference) -> Iterator[bytes] | None:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._client().get_blob_client(file.container, file.path)
        try:
            downloader = blob.download_blob()
        except ResourceNotFoundError:
            return None
        return iter(downloader.chunks())

    def delete(self, file: StoredFileReference) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._client().get_blob_client(file.container, file.path)
        with contextlib.suppress(ResourceNotFoundError):
            blob.delete_blob()


def build_storage(settings: Settings) -> FileStorage:
    if settings.storage_provider.lower() == "azureblob":
        return AzureBlobFileStorage(settings.storage_azure_blob_connection_string)
    return LocalFileStorage(settings.storage_local_root_path)
