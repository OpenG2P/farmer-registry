INSERT INTO "public"."callback_secret" (
    "id",
    "caller_service",
    "secret_hash",
    "status",
    "rotated_at",
    "created_at",
    "updated_at"
) VALUES (
    'registry',
    'openg2p.registry',
    '${AWE_CALLBACK_HMAC_SECRET}',
    'active',
    NOW(),
    NOW(),
    NOW()
)
ON CONFLICT ("id") DO NOTHING;
