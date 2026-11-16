import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.storage import S3FileStorage, StoredFileReference, build_storage

BUCKET = "hacienda-test"


@pytest.fixture
def storage():
    with mock_aws():
        client = boto3.client(
            "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
        )
        client.create_bucket(Bucket=BUCKET)
        yield S3FileStorage(bucket=BUCKET, client=client), client


def test_save_read_stream_delete_roundtrip(storage):
    s3, client = storage
    content = b"%PDF-1.4 " + b"x" * 200_000

    ref = s3.save("uploads", "client/2026/10/abc_factura.pdf", content, "application/pdf")

    assert ref == StoredFileReference("S3", "uploads", "client/2026/10/abc_factura.pdf")
    head = client.head_object(Bucket=BUCKET, Key="uploads/client/2026/10/abc_factura.pdf")
    assert head["ContentType"] == "application/pdf"
    assert s3.read(ref) == content
    assert b"".join(s3.iter_chunks(ref)) == content

    s3.delete(ref)
    assert s3.read(ref) is None
    assert s3.iter_chunks(ref) is None
    s3.delete(ref)  # deleting a missing object is not an error


def test_missing_object_returns_none(storage):
    s3, _ = storage
    ref = StoredFileReference("S3", "outputs", "nope.csv")
    assert s3.read(ref) is None
    assert s3.iter_chunks(ref) is None


def test_rejects_path_traversal(storage):
    s3, _ = storage
    with pytest.raises(ValueError):
        s3.save("uploads", "../outputs/x.csv", b"x", "text/csv")


def test_missing_bucket_setting_fails_clearly():
    with pytest.raises(RuntimeError, match="STORAGE_S3_BUCKET"):
        S3FileStorage(bucket="").read(StoredFileReference("S3", "uploads", "a.pdf"))


@pytest.mark.parametrize("provider", ["S3", "s3", "Supabase"])
def test_build_storage_selects_s3(provider):
    settings = Settings(storage_provider=provider, storage_s3_bucket=BUCKET)
    assert isinstance(build_storage(settings), S3FileStorage)
