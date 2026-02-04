import os
import sys
import uuid
import traceback

from pathlib import Path

try:
    import boto3  # type: ignore
    from botocore.exceptions import ClientError, EndpointConnectionError  # type: ignore
except ImportError as exc:  # pragma: no cover - diagnostic script
    print(f"[FATAL] Cannot import boto3: {exc}")
    sys.exit(1)


def env(name: str, default: str | None = None) -> str | None:
    """Helper to read environment variables with trim."""
    value = os.getenv(name, default)
    if isinstance(value, str):
        value = value.strip()
    return value


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _load_env_from_multisite_plugin() -> None:
    """Load S3 credentials from multi-site-location .env without restarting Connect."""
    try:
        # tools/test_s3_connection.py -> project root
        root = Path(__file__).resolve().parents[1]
        env_path = root / "ftrack_plugins" / "multi-site-location-0.2.0" / ".env"
        if not env_path.exists():
            print(f"[INFO] .env file not found at {env_path}, skipping explicit load")
            return
        print(f"[INFO] Loading S3 config from {env_path}")
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            # Do not overwrite variables that are already set in the environment.
            if os.getenv(key) is None:
                os.environ[key] = value
    except Exception:
        print("[WARN] Failed to load .env from multi-site-location-0.2.0")
        traceback.print_exc()


def main() -> int:
    print_header("S3 / MinIO connection diagnostic")

    # First, load values from the same .env that uses the S3 plugin.
    _load_env_from_multisite_plugin()

    # Support both legacy and new naming: S3_MINIO_ENDPOINT_URL and S3_MINIO_API_ENDPOINT_URL.
    endpoint_url = env("S3_MINIO_ENDPOINT_URL") or env("S3_MINIO_API_ENDPOINT_URL")
    access_key = env("AWS_ACCESS_KEY_ID") or env("S3_ACCESS_KEY") or env("MINIO_ACCESS_KEY")
    secret_key = env("AWS_SECRET_ACCESS_KEY") or env("S3_SECRET_KEY") or env("MINIO_SECRET_KEY")
    bucket_name = env("S3_BUCKET") or env("MINIO_BUCKET")

    print(f"S3_MINIO_ENDPOINT_URL = {env('S3_MINIO_ENDPOINT_URL')!r}")
    print(f"S3_MINIO_API_ENDPOINT_URL = {env('S3_MINIO_API_ENDPOINT_URL')!r}")
    print(f"Effective endpoint_url used = {endpoint_url!r}")
    print(f"AWS_ACCESS_KEY_ID / S3_ACCESS_KEY / MINIO_ACCESS_KEY set: {bool(access_key)}")
    print(f"AWS_SECRET_ACCESS_KEY / S3_SECRET_KEY / MINIO_SECRET_KEY set: {bool(secret_key)}")
    print(f"S3_BUCKET / MINIO_BUCKET = {bucket_name!r}")

    if not endpoint_url:
        print("[ERROR] S3_MINIO_ENDPOINT_URL is not set")
    if not access_key or not secret_key:
        print("[ERROR] Access or secret key is not set")
    if not bucket_name:
        print("[ERROR] Bucket name is not set")

    # Even if something is missing, we still try to continue – это поможет увидеть точную ошибку.

    print_header("1. Creating boto3 session & client")
    try:
        session = boto3.session.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        s3 = session.client(
            "s3",
            endpoint_url=endpoint_url,
            use_ssl=True,
            verify=True,
        )
        print("[OK] boto3 client created successfully")
    except Exception as exc:  # pragma: no cover - diagnostic script
        print("[FATAL] Failed to create boto3 client")
        traceback.print_exc()
        return 1

    print_header("2. Listing buckets")
    try:
        resp = s3.list_buckets()
        names = [b["Name"] for b in resp.get("Buckets", [])]
        print(f"[OK] Buckets visible from this client: {names}")
    except EndpointConnectionError as exc:  # pragma: no cover
        print("[ERROR] Endpoint connection error (network/TLS problem?)")
        traceback.print_exc()
        return 1
    except ClientError as exc:  # pragma: no cover
        print("[ERROR] ClientError while listing buckets (auth/permissions?)")
        print(exc)
        return 1
    except Exception:  # pragma: no cover
        print("[ERROR] Unexpected error while listing buckets")
        traceback.print_exc()
        return 1

    if bucket_name:
        print_header(f"3. Checking bucket existence: {bucket_name}")
        try:
            s3.head_bucket(Bucket=bucket_name)
            print(f"[OK] Bucket {bucket_name!r} exists and is accessible")
        except ClientError as exc:  # pragma: no cover
            print(f"[ERROR] Cannot access bucket {bucket_name!r}")
            print(exc)
            # продолжаем дальше, чтобы увидеть, что будет на put/get

        test_key = f"_mroya_s3_test_{uuid.uuid4().hex}.txt"
        test_body = b"mroya s3 connectivity test"

        print_header(f"4. Uploading test object: {bucket_name}/{test_key}")
        try:
            s3.put_object(Bucket=bucket_name, Key=test_key, Body=test_body)
            print("[OK] Test object uploaded")
        except ClientError as exc:  # pragma: no cover
            print("[ERROR] Failed to upload test object (permissions?)")
            print(exc)
            return 1
        except Exception:  # pragma: no cover
            print("[ERROR] Unexpected error on put_object")
            traceback.print_exc()
            return 1

        print_header(f"5. Downloading test object: {bucket_name}/{test_key}")
        try:
            resp = s3.get_object(Bucket=bucket_name, Key=test_key)
            data = resp["Body"].read()
            print(f"[OK] Test object downloaded, size={len(data)} bytes")
        except ClientError as exc:  # pragma: no cover
            print("[ERROR] Failed to download test object")
            print(exc)
            return 1
        except Exception:  # pragma: no cover
            print("[ERROR] Unexpected error on get_object")
            traceback.print_exc()
            return 1

        print_header(f"6. Cleaning up test object: {bucket_name}/{test_key}")
        try:
            s3.delete_object(Bucket=bucket_name, Key=test_key)
            print("[OK] Test object deleted")
        except Exception as exc:  # pragma: no cover
            print("[WARN] Failed to delete test object (manual cleanup may be required)")
            print(exc)

        print_header("7. Generating presigned URL for test (read)")
        try:
            # создадим новый объект, чтобы проверить presigned URL
            presign_key = f"_mroya_s3_presign_test_{uuid.uuid4().hex}.txt"
            s3.put_object(Bucket=bucket_name, Key=presign_key, Body=b"presigned url test")
            url = s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket_name, "Key": presign_key},
                ExpiresIn=600,
            )
            print(f"[OK] Presigned URL generated:\n{url}")
            # удалим объект после генерации ссылки
            try:
                s3.delete_object(Bucket=bucket_name, Key=presign_key)
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover
            print("[WARN] Failed to generate presigned URL")
            traceback.print_exc()

    print_header("Done")
    print("If some steps above show [ERROR] or [FATAL], share this log with the admin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

