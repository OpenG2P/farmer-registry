#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from minio import Minio


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        print(f"[db-seed] Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    templates_dir = Path(os.environ.get("TEMPLATES_DIR", "/seed/templates"))
    bucket_name = env("TEMPLATE_BUCKET_NAME", "template")
    endpoint = env("MINIO_ENDPOINT")
    access_key = env("MINIO_ACCESS_KEY")
    secret_key = env("MINIO_SECRET_KEY")
    secure = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")

    if not templates_dir.is_dir():
        print(f"[db-seed] Templates directory not found: {templates_dir}", file=sys.stderr)
        sys.exit(1)

    template_files = sorted(templates_dir.glob("*.j2"))
    if not template_files:
        print(f"[db-seed] No .j2 template files found in {templates_dir}", file=sys.stderr)
        sys.exit(1)

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"[db-seed] Created MinIO bucket: {bucket_name}")

    print(f"[db-seed] Uploading {len(template_files)} template(s) to s3://{bucket_name}/ ...")
    for path in template_files:
        client.fput_object(bucket_name, path.name, str(path))
        print(f"[db-seed]   -> {path.name}")

    print("[db-seed] Template upload completed.")


if __name__ == "__main__":
    main()
