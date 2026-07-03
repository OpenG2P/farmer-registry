#!/usr/bin/env python3
"""Upload sample profile images to MinIO and link them to g2p_register_farmers.

Images live at openg2p-data/demography/images/IND-XXXX.jpg. Each is uploaded
under its filename to a MinIO bucket and the matching farmer row is updated with
record_image_storage_id = filename. Farmers reuse the individual record id (i####), so we match on internal_record_id
derived from the image's numeric suffix.
"""

import os
import sys
from pathlib import Path

import psycopg2
from minio import Minio

INDIVIDUAL_ID_PREFIX = "i"


def env(name: str, default=None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        print(f"[upload-images] Missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def individual_uuid_from_stem(stem: str) -> str | None:
    """IND-0001 -> i0001."""
    try:
        seq = int(stem.split("-")[1])
    except (IndexError, ValueError):
        return None
    return f"{INDIVIDUAL_ID_PREFIX}{seq:04d}"


def main() -> None:
    images_dir = Path(os.environ.get("IMAGES_DIR", "/openg2p-data/demography/images"))
    bucket_name = env("IMAGE_BUCKET_NAME", "registrant-photos")
    endpoint = env("MINIO_ENDPOINT")
    access_key = env("MINIO_ACCESS_KEY")
    secret_key = env("MINIO_SECRET_KEY")
    secure = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")

    if not images_dir.is_dir():
        print(f"[upload-images] Images directory not found: {images_dir}", file=sys.stderr)
        sys.exit(1)

    image_files = sorted(images_dir.glob("*.jpg"))
    if not image_files:
        print(f"[upload-images] No .jpg files found in {images_dir}", file=sys.stderr)
        sys.exit(1)

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"[upload-images] Created MinIO bucket: {bucket_name}")

    print(f"[upload-images] Uploading {len(image_files)} image(s) to s3://{bucket_name}/ …")
    updates: list = []
    for path in image_files:
        rid = individual_uuid_from_stem(path.stem)
        if rid is None:
            print(f"[upload-images] Skipping unrecognised filename: {path.name}")
            continue
        client.fput_object(bucket_name, path.name, str(path), content_type="image/jpeg")
        updates.append((path.name, rid))
    print(f"[upload-images] Uploaded {len(updates)} images.")

    conn = psycopg2.connect(
        host=env("PGHOST"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=env("PGDATABASE"),
        user=env("PGUSER"),
        password=env("PGPASSWORD"),
    )
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.executemany(
            'UPDATE "public"."g2p_register_farmers" '
            "SET record_image_storage_id = %s "
            "WHERE internal_record_id = %s",
            updates,
        )
        conn.commit()
        print(f"[upload-images] Updated {cur.rowcount} rows in g2p_register_farmers.")
    except Exception as exc:
        conn.rollback()
        print(f"[upload-images] DB update FAILED: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
