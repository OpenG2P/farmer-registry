INSERT INTO "public"."incoming_templates" ("template_id","register_id","data_model_id","template_document_id","jsonld_expansion_required","created_at","updated_at") VALUES
('IN-TMPL-1','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','c331ba96-ac35-4014-9d13-4ef327f6b79b','1f997c2f-f768-4224-96a9-f60938224dda','FALSE','2026-05-07 04:31:27.828397',NULL),
('FARMER-ODK-V1-TMPL','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','f0a1b2c3-d4e5-4f67-8901-23456789abcd','f0a1b2c3-d4e5-4f67-8901-23456789abd0','FALSE','2026-11-23 00:00:00',NULL)
ON CONFLICT ("template_id") DO UPDATE SET "register_id" = EXCLUDED."register_id", "data_model_id" = EXCLUDED."data_model_id", "template_document_id" = EXCLUDED."template_document_id", "jsonld_expansion_required" = EXCLUDED."jsonld_expansion_required", "created_at" = EXCLUDED."created_at", "updated_at" = EXCLUDED."updated_at";

-- DCI: dci_to_openg2p_farmer.json.j2
-- ODK: openg2p_odk_to_registry.json.j2
