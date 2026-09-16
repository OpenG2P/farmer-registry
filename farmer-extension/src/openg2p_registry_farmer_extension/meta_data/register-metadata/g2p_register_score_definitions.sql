INSERT INTO "public"."g2p_register_score_definitions" (
    "score_definition_id",
    "register_mnemonic",
    "score_type",
    "is_enabled"
) VALUES (
    'e7269b21-f234-411a-bb4d-16ca8b5f3cd3',
    'Household',
    'POVERTY',
    'TRUE'
)
ON CONFLICT ("score_definition_id") DO UPDATE SET "register_mnemonic" = EXCLUDED."register_mnemonic", "score_type" = EXCLUDED."score_type", "is_enabled" = EXCLUDED."is_enabled";
