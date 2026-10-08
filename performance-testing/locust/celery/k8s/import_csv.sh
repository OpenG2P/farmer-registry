#!/usr/bin/env bash
# Upload play-format farmer CSVs. Count is the number of records in each file,
# from 1 to 50000. Files is how many separate CSVs to upload. One CSV is one
# Celery task. Object keys are perf-import-00000001.csv and so on.

set -euo pipefail

NS="${CELERY_NAMESPACE:-perftest}"
COUNT="${1:?count}"
FILES="${2:-1}"
POD=celery-import-csv

[[ "$COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "Count must be a positive integer" >&2; exit 2; }
[[ "$FILES" =~ ^[1-9][0-9]*$ ]] || { echo "Files must be a positive integer" >&2; exit 2; }
if (( COUNT > 50000 )); then
  echo "import_file_process supports at most 50000 records in the CSV" >&2
  exit 2
fi
if (( FILES > 20 )); then
  echo "import_file_process supports at most 20 CSV files" >&2
  exit 2
fi

kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  kubectl -n "$NS" get pod "$POD" >/dev/null 2>&1 || break
  sleep 1
done

kubectl -n "$NS" apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  namespace: ${NS}
spec:
  restartPolicy: Never
  containers:
    - name: upload
      image: vin0dkhichar/ofr-staff-celery:performance-test
      env:
        - name: COUNT
          value: "${COUNT}"
        - name: FILES
          value: "${FILES}"
        - name: MINIO_ACCESS
          valueFrom:
            secretKeyRef:
              name: commons-minio
              key: root-user
        - name: MINIO_SECRET
          valueFrom:
            secretKeyRef:
              name: commons-minio
              key: root-password
      command: ["sleep", "600"]
EOF

ready=""
for _ in $(seq 1 40); do
  phase="$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  deleting="$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.metadata.deletionTimestamp}' 2>/dev/null || true)"
  if [[ "$phase" == "Running" && -z "$deleting" ]]; then
    ready=1
    break
  fi
  sleep 2
done
[[ -n "$ready" ]] || { echo "Pod ${POD} did not start" >&2; exit 1; }

kubectl -n "$NS" exec "$POD" -- python -c '
import io, os
from minio import Minio
from minio.deleteobjects import DeleteObject

count = int(os.environ["COUNT"])
files = int(os.environ["FILES"])
client = Minio(
    "commons-minio:9000",
    access_key=os.environ["MINIO_ACCESS"],
    secret_key=os.environ["MINIO_SECRET"],
    secure=False,
)
bucket = "documents"
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)
stale = (
    DeleteObject(obj.object_name)
    for obj in client.list_objects(bucket, prefix="perf-import-", recursive=True)
)
for error in client.remove_objects(bucket, stale):
    raise SystemExit(error)
header = (
    "first_name,middle_name,last_name,gender,marital_status,birth_date,"
    "estimated_age,foundational_id,education_level,has_personal_phone,disabled,"
    "disability_type,disability_severity,source_of_income,source_of_income_other,"
    "language_spoken,national_id_masked,address_line_1,address_line_2,locality,"
    "postal_code,country_code,latitude,longitude,registration_date\n"
)
for file_no in range(1, files + 1):
    buf = io.BytesIO()
    buf.write(header.encode())
    for i in range(1, count + 1):
        fid = f"3361{file_no:02d}{i:08d}"
        buf.write(
            (
                f"Adam,,Woods,MALE,MARRIED,1990-05-12,,{fid},BASIC,true,false,,,"
                f"SOI_CROP_PRODUCTION,,ENGLISH,{fid},12 Farm Road,,Sikar,332001,IN,null,null,2026-09-20\n"
            ).encode()
        )
    data = buf.getvalue()
    key = f"perf-import-{file_no:08d}.csv"
    client.put_object(bucket, key, io.BytesIO(data), len(data), content_type="text/csv")
    print("uploaded", key, "bytes", len(data), "records", count)
'

kubectl -n "$NS" delete pod "$POD" --wait=false >/dev/null

PARTNER=celery-import-partner
kubectl -n "$NS" delete pod "$PARTNER" --ignore-not-found --wait=false >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  kubectl -n "$NS" get pod "$PARTNER" >/dev/null 2>&1 || break
  sleep 1
done
kubectl -n "$NS" apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${PARTNER}
  namespace: ${NS}
spec:
  restartPolicy: Never
  containers:
    - name: psql
      image: postgres:16-alpine
      env:
        - name: PGHOST
          value: "172.29.2.191"
        - name: PGPORT
          value: "5432"
        - name: PGDATABASE
          value: master_data
        - name: PGUSER
          value: master_data_user
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: master-data
              key: master-data-db-user
      command: ["sleep", "120"]
EOF
ready=""
for _ in $(seq 1 30); do
  phase="$(kubectl -n "$NS" get pod "$PARTNER" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  deleting="$(kubectl -n "$NS" get pod "$PARTNER" -o jsonpath='{.metadata.deletionTimestamp}' 2>/dev/null || true)"
  if [[ "$phase" == "Running" && -z "$deleting" ]]; then
    ready=1
    break
  fi
  sleep 2
done
[[ -n "$ready" ]] || { echo "Pod ${PARTNER} did not start" >&2; exit 1; }
kubectl -n "$NS" exec -i "$PARTNER" -- psql -v ON_ERROR_STOP=1 << 'SQL'
INSERT INTO g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
VALUES ('perf-import-partner', 'Staff Portal', 'perf-import-partner-km', true)
ON CONFLICT (partner_mnemonic) DO NOTHING;
SQL
kubectl -n "$NS" delete pod "$PARTNER" --wait=false >/dev/null
