INSERT INTO "public"."approval_stage" (
    "id",
    "policy_id",
    "stage_order",
    "name",
    "mode",
    "mode_value",
    "sla_hours",
    "parallel_group",
    "skip_if",
    "on_empty",
    "on_breach",
    "escalation_rules_json",
    "created_at",
    "updated_at"
) VALUES
    ('531b633a-faea-4d1a-ac1a-6e76016e8457', '576a69ba-a2ca-4c34-80b7-952e8c5a86f8', 1, 'Stage 1 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('6aea22f1-fe79-4aaa-9adb-5ccd9fe89b92', '576a69ba-a2ca-4c34-80b7-952e8c5a86f8', 2, 'Stage 2 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('8da27858-c065-43f9-95d7-310eb326743b', '57f40743-266c-4e25-9a16-fd45483f904c', 1, 'Stage 1 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('bbfc19f4-feb2-46cf-a101-2933b065b456', '57f40743-266c-4e25-9a16-fd45483f904c', 2, 'Stage 2 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('255f31be-f14c-40a5-a3fb-fd155ea79e54', 'e725a02c-6120-4e33-b4ec-294a38b07b18', 1, 'Stage 1 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('da640587-ffc0-432a-a6a9-82adeb8c5f42', 'e725a02c-6120-4e33-b4ec-294a38b07b18', 2, 'Stage 2 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('4b608b44-fe22-4b9c-acff-673a50db55bd', 'fb51a862-d2ed-460d-8e1f-929cbeabdd01', 1, 'Stage 1 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW()),
    ('32c48f1c-20b9-4a28-883b-bc5949ddda5b', 'fb51a862-d2ed-460d-8e1f-929cbeabdd01', 2, 'Stage 2 Officers', 'all', NULL, NULL, NULL, 'null', 'block', NULL, 'null', NOW(), NOW())
ON CONFLICT ("id") DO NOTHING;
