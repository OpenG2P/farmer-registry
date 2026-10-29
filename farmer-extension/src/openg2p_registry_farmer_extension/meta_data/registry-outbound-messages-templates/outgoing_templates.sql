INSERT INTO "public"."outgoing_templates" ("template_id","data_model_id","register_id","template_document_id","created_at","updated_at") VALUES
('OUT-TMPL-1','c331ba96-ac35-4014-9d13-4ef327f6b79b','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','2a8b3c4d-5e6f-7890-abcd-ef1234567890','2026-05-07 04:31:27.828397',NULL),
('OUT-TMPL-2','c331ba96-ac35-4014-9d13-4ef327f6b79b','9055ab43-c85d-4833-bd00-ca657bb72644','3c9e5a71-4b28-4e0a-9c11-8f6d2a7b01e4','2026-10-08 00:00:00',NULL)
ON CONFLICT ("template_id") DO UPDATE SET "data_model_id" = EXCLUDED."data_model_id", "register_id" = EXCLUDED."register_id", "template_document_id" = EXCLUDED."template_document_id", "created_at" = EXCLUDED."created_at", "updated_at" = EXCLUDED."updated_at";

-- DCI Farmer: openg2p_farmer_to_dci.json.j2 (OUT-TMPL-1)
-- DCI Household: openg2p_household_to_dci.json.j2 (OUT-TMPL-2)
