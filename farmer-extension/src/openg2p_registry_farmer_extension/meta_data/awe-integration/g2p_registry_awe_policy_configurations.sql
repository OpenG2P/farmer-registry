INSERT INTO "public"."g2p_registry_awe_policy_configurations" (
    "awe_policy_config_id",
    "policy_scope",
    "register_id",
    "intake_form_id",
    "section_id",
    "policy_type",
    "policy_key",
    "context_field_names"
) VALUES
    ('42bd3bee-990c-43bf-9255-658f37ed14fb', 'REGISTER', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '', '', 'registry.change_request', 'registry.change_request.farmer', 'null'),
    ('ac2587c4-7505-43b7-9f5d-70eefc34b906', 'INTAKE_FORM', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-8782382649', '', 'registry.intake_form', 'registry.intake_form.farmer', 'null'),
    ('b4d9d72c-cdf8-45c9-a37c-f7f86da1df34', 'REGISTER', '9055ab43-c85d-4833-bd00-ca657bb72644', '', '', 'registry.change_request', 'registry.change_request.household', 'null'),
    ('d8e9f0a1-b2c3-4567-8901-234567890abc', 'INTAKE_FORM', '9055ab43-c85d-4833-bd00-ca657bb72644', '9055ab43-c85d-4833-bd00-ca657bb72650', '', 'registry.intake_form', 'registry.intake_form.household', 'null')
ON CONFLICT ("awe_policy_config_id") DO NOTHING;
