"""Isolated Celery backlog cases.

Work does not start in Redis. Each beat producer polls one status column and
enqueues at most REGISTRY_CELERY_BEAT_NO_OF_TASKS_TO_PROCESS rows per tick
(Helm default 4) onto the shared queue registry_worker_queue.

`eligible_sql` matches the producer filter. `extra_sql` counts rows a sibling
producer would also enqueue during the same run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    name: str
    description: str
    table: str
    status_column: str
    pending: str
    in_progress: str
    done: str
    failed: str
    # Rows the beat producer will claim. Must be the whole experiment cohort.
    eligible_sql: str
    status_counts_sql: str
    # extra_role:
    #   sibling    — another producer will enqueue if this count is non-zero
    #   follow_on  — sibling work this worker creates; non-zero at t0 is leftover
    #   reject     — eligible rows the worker will fail closed
    extra_name: str | None
    extra_sql: str | None
    extra_role: str | None
    # Helm / code default when the matching env var is unset.
    frequency_s: int
    frequency_env: str
    # Producer claims the row before send_task. Intake ingest does not.
    producer_claims_row: bool
    notes: str


def _status_sql(table: str, column: str) -> str:
    return (
        f"SELECT {column} AS status, COUNT(*)::bigint AS n "
        f"FROM {table} GROUP BY 1"
    )


CASES: dict[str, Case] = {
    "functional_id_allocation": Case(
        name="functional_id_allocation",
        description="Functional ID allocation (id generation)",
        table="g2p_functional_id_generation_queue",
        status_column="id_allocation_status",
        pending="PENDING",
        in_progress="PROCESSING",
        done="COMPLETED",
        failed="FAILED",
        eligible_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_functional_id_generation_queue "
            "WHERE id_allocation_status = 'PENDING'"
        ),
        status_counts_sql=_status_sql(
            "g2p_functional_id_generation_queue", "id_allocation_status"
        ),
        extra_name="id_updation_pending",
        extra_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_functional_id_generation_queue "
            "WHERE id_updation_status = 'PENDING'"
        ),
        extra_role="follow_on",
        frequency_s=20,
        frequency_env="REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_ALLOCATION_BEAT_PRODUCER_FREQUENCY",
        producer_claims_row=True,
        notes=(
            "The allocation worker sets id_updation_status to PENDING, so "
            "functional_id_updation_beat_producer starts enqueueing follow-on "
            "work onto the same queue. Allocation completion is still the "
            "id_allocation_status delta; id_updation_pending shows the leak."
        ),
    ),
    "dedup_register": Case(
        name="dedup_register",
        description="Change-request dedup against the register",
        table="g2p_register_change_requests",
        status_column="deduplication_register_status",
        pending="PENDING",
        in_progress="INPROGRESS",
        done="COMPLETED",
        failed="FAILED",
        eligible_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_register_change_requests "
            "WHERE deduplication_register_status = 'PENDING'"
        ),
        status_counts_sql=_status_sql(
            "g2p_register_change_requests", "deduplication_register_status"
        ),
        extra_name="dedup_change_request_pending",
        extra_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_register_change_requests "
            "WHERE deduplication_change_request_status = 'PENDING'"
        ),
        extra_role="sibling",
        frequency_s=30,
        frequency_env="REGISTRY_CELERY_BEAT_DEDUPLICATION_BEAT_PRODUCER_FREQUENCY",
        producer_claims_row=True,
        notes=(
            "New change requests default both dedup statuses to PENDING, so "
            "deduplication_change_request_beat_producer will share the workers "
            "unless that sibling column is not PENDING on this cohort."
        ),
    ),
    "dedup_change_request": Case(
        name="dedup_change_request",
        description="Change-request dedup against other change requests",
        table="g2p_register_change_requests",
        status_column="deduplication_change_request_status",
        pending="PENDING",
        in_progress="INPROGRESS",
        done="COMPLETED",
        failed="FAILED",
        eligible_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_register_change_requests "
            "WHERE deduplication_change_request_status = 'PENDING'"
        ),
        status_counts_sql=_status_sql(
            "g2p_register_change_requests", "deduplication_change_request_status"
        ),
        extra_name="dedup_register_pending",
        extra_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_register_change_requests "
            "WHERE deduplication_register_status = 'PENDING'"
        ),
        extra_role="sibling",
        frequency_s=30,
        frequency_env="REGISTRY_CELERY_BEAT_DEDUPLICATION_BEAT_PRODUCER_FREQUENCY",
        producer_claims_row=True,
        notes=(
            "Isolate from dedup_register by leaving deduplication_register_status "
            "off PENDING for this cohort. Both producers share one beat tick size."
        ),
    ),
    "dedup_intake_vs_register": Case(
        name="dedup_intake_vs_register",
        description="Intake submission dedup against the register",
        table="g2p_intake_form_submissions",
        status_column="deduplication_status_vs_register",
        pending="PENDING",
        in_progress="INPROGRESS",
        done="COMPLETED",
        failed="FAILED",
        eligible_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_intake_form_submissions "
            "WHERE deduplication_status_vs_register = 'PENDING' "
            "AND draft_status = 'FINAL'"
        ),
        status_counts_sql=_status_sql(
            "g2p_intake_form_submissions", "deduplication_status_vs_register"
        ),
        extra_name="dedup_intake_vs_intake_pending",
        extra_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_intake_form_submissions "
            "WHERE deduplication_status_vs_intake_forms = 'PENDING' "
            "AND draft_status = 'FINAL'"
        ),
        extra_role="sibling",
        frequency_s=30,
        frequency_env="REGISTRY_CELERY_BEAT_DEDUPLICATION_BEAT_PRODUCER_FREQUENCY",
        producer_claims_row=True,
        notes=(
            "Producer also requires draft_status FINAL. The sibling intake-vs-intake "
            "producer uses the same FINAL filter on a different column."
        ),
    ),
    "dedup_intake_vs_intake": Case(
        name="dedup_intake_vs_intake",
        description="Intake submission dedup against other intake submissions",
        table="g2p_intake_form_submissions",
        status_column="deduplication_status_vs_intake_forms",
        pending="PENDING",
        in_progress="INPROGRESS",
        done="COMPLETED",
        failed="FAILED",
        eligible_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_intake_form_submissions "
            "WHERE deduplication_status_vs_intake_forms = 'PENDING' "
            "AND draft_status = 'FINAL'"
        ),
        status_counts_sql=_status_sql(
            "g2p_intake_form_submissions", "deduplication_status_vs_intake_forms"
        ),
        extra_name="dedup_intake_vs_register_pending",
        extra_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_intake_form_submissions "
            "WHERE deduplication_status_vs_register = 'PENDING' "
            "AND draft_status = 'FINAL'"
        ),
        extra_role="sibling",
        frequency_s=30,
        frequency_env="REGISTRY_CELERY_BEAT_DEDUPLICATION_BEAT_PRODUCER_FREQUENCY",
        producer_claims_row=True,
        notes=(
            "Keep deduplication_status_vs_register off PENDING on this cohort "
            "so the other intake dedup producer stays idle."
        ),
    ),
    "intake_register_ingest": Case(
        name="intake_register_ingest",
        description="Approved intake submission ingest into the register",
        table="g2p_intake_form_submissions",
        status_column="register_ingest_process_status",
        pending="PENDING",
        in_progress="PROCESSING",
        done="PROCESSED",
        failed="FAILED",
        eligible_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_intake_form_submissions "
            "WHERE approval_status = 'APPROVED' "
            "AND register_ingest_process_status = 'PENDING'"
        ),
        status_counts_sql=_status_sql(
            "g2p_intake_form_submissions", "register_ingest_process_status"
        ),
        extra_name="ingest_rows_worker_will_reject",
        extra_sql=(
            "SELECT COUNT(*)::bigint FROM g2p_intake_form_submissions "
            "WHERE approval_status = 'APPROVED' "
            "AND register_ingest_process_status = 'PENDING' "
            "AND draft_status <> 'FINAL'"
        ),
        extra_role="reject",
        frequency_s=20,
        frequency_env="REGISTRY_CELERY_BEAT_INTAKE_FORM_REGISTER_INGEST_BEAT_PRODUCER_FREQUENCY",
        producer_claims_row=False,
        notes=(
            "The ingest producer does not mark the row PROCESSING before "
            "send_task. The worker does, and it also requires draft_status "
            "FINAL. A faster beat re-enqueues the same submissions until that "
            "mark lands, so failed duplicate tasks show up in the worker logs. "
            "Processed submissions also fan out score and outgest work."
        ),
    ),
}


def _queue_case(
    name: str,
    description: str,
    table: str,
    column: str,
    where: str,
    done: str,
    frequency_s: int,
    frequency_env: str,
    notes: str,
) -> None:
    CASES[name] = Case(
        name=name,
        description=description,
        table=table,
        status_column=column,
        pending="PENDING",
        in_progress="PROCESSING",
        done=done,
        failed="FAILED",
        eligible_sql=(
            f"SELECT COUNT(*)::bigint FROM {table} "
            f"WHERE {column} = 'PENDING' AND ({where})"
        ),
        status_counts_sql=(
            f"SELECT {column} AS status, COUNT(*)::bigint AS n FROM {table} "
            f"WHERE {where} GROUP BY 1"
        ),
        extra_name=None,
        extra_sql=None,
        extra_role=None,
        frequency_s=frequency_s,
        frequency_env=frequency_env,
        producer_claims_row=True,
        notes=notes,
    )


_queue_case(
    "ingest_data_classification",
    "Partner ingest classification",
    "incoming_raw_data",
    "classification_status",
    "TRUE",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_INGEST_DATA_CLASSIFICATION_BEAT_PRODUCER_FREQUENCY",
    "Beat claims classification_status before enqueue.",
)
_queue_case(
    "ingest_data_transformation",
    "Partner ingest transformation",
    "incoming_classified_data",
    "transformation_status",
    "TRUE",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_DATA_TRANSFORMATION_BEAT_PRODUCER_FREQUENCY",
    "Shares the transformation frequency with outgest transformation.",
)
_queue_case(
    "ingest_data",
    "Partner ingest into the register (pipeline_action ADD)",
    "incoming_classified_data",
    "ingestion_status",
    "pipeline_action IS DISTINCT FROM 'UPDATE'",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_INGEST_DATA_BEAT_PRODUCER_FREQUENCY",
    "The ingest beat producer sends UPDATE rows to change_request_ingest_worker instead.",
)
_queue_case(
    "change_request_ingest",
    "Partner ingest that updates an existing record",
    "incoming_classified_data",
    "ingestion_status",
    "pipeline_action = 'UPDATE'",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_INGEST_DATA_BEAT_PRODUCER_FREQUENCY",
    "Same beat producer as ingest_data. Isolation is pipeline_action = UPDATE.",
)
_queue_case(
    "outgest_data_transformation",
    "Outgest payload transformation",
    "outgoing_raw_data",
    "transformation_status",
    "TRUE",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_DATA_TRANSFORMATION_BEAT_PRODUCER_FREQUENCY",
    "Shares the transformation frequency with ingest transformation.",
)
_queue_case(
    "outgest_data_publish",
    "Outgest publish",
    "outgoing_raw_data",
    "publish_status",
    "TRUE",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_OUTGEST_DATA_PUBLISH_BEAT_PRODUCER_FREQUENCY",
    "Beat claims publish_status before enqueue.",
)
_queue_case(
    "outgest_topic_register",
    "WebSub topic registration",
    "outgoing_topics",
    "websub_register_status",
    "TRUE",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_OUTGEST_TOPIC_REGISTER_BEAT_PRODUCER_FREQUENCY",
    "Beat claims websub_register_status before enqueue.",
)
_queue_case(
    "functional_id_updation",
    "Functional ID updation after allocation",
    "g2p_functional_id_generation_queue",
    "id_updation_status",
    "TRUE",
    "COMPLETED",
    20,
    "REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_UPDATION_BEAT_PRODUCER_FREQUENCY",
    "Allocation sets this column to PENDING as it completes, so an allocation run wakes this producer.",
)
_queue_case(
    "score_compute",
    "Score computation queue",
    "g2p_score_compute_queue",
    "compute_status",
    "TRUE",
    "COMPLETED",
    20,
    "REGISTRY_CELERY_BEAT_SCORE_COMPUTE_BEAT_PRODUCER_FREQUENCY",
    "Done status on this queue is COMPLETED.",
)
_queue_case(
    "completion_score",
    "Completion-score computation queue",
    "g2p_completion_score_computation_queue",
    "compute_status",
    "TRUE",
    "COMPLETED",
    20,
    "REGISTRY_CELERY_BEAT_COMPLETION_SCORE_BEAT_PRODUCER_FREQUENCY",
    "Done status on this queue is COMPLETED.",
)
_queue_case(
    "import_file_process",
    "Import-file intake ingestion",
    "import_file_process_queue",
    "intake_form_ingestion_status",
    "TRUE",
    "PROCESSED",
    20,
    "REGISTRY_CELERY_BEAT_IMPORT_FILE_PROCESS_BEAT_PRODUCER_FREQUENCY",
    "Beat claims intake_form_ingestion_status before enqueue.",
)


def get_case(name: str) -> Case:
    try:
        return CASES[name]
    except KeyError as exc:
        known = ", ".join(CASES)
        raise SystemExit(f"Unknown case {name!r}. Known cases: {known}") from exc
