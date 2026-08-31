-- Default values for this registry's code lists.
--
-- Generated from the option arrays that used to live inside the widgets. They
-- are DEFAULTS, not a definition: load_attributes_from_mds replaces any list the
-- country pack also defines, and an admin can edit them in the staff portal.
-- Before this the same values were compiled into g2p_register_sections, where
-- neither route could reach them.
--
-- Values are unchanged from what the widgets carried, so a deployment with no
-- country pack behaves exactly as it did.

INSERT INTO "public"."g2p_attributes" ("attribute_id","attribute_code","attribute_display","is_hierarchical") VALUES 
('DISABILITY_DOMAIN','DISABILITY_DOMAIN','Disability Domain','FALSE'),
('DISABILITY_SEVERITY','DISABILITY_SEVERITY','Disability Severity','FALSE'),
('EDUCATION_LEVEL','EDUCATION_LEVEL','Education Level','FALSE'),
('FARMER_CLUSTER_ROLE','FARMER_CLUSTER_ROLE','Farmer Cluster Role','FALSE'),
('GENDER','GENDER','Gender','FALSE'),
('MARITAL_STATUS','MARITAL_STATUS','Marital Status','FALSE'),
('SOURCE_OF_INCOME','SOURCE_OF_INCOME','Source Of Income','FALSE'),
('PREFIX','PREFIX','Prefix','FALSE'),
('RELATIONSHIP_TO_THE_HEAD','RELATIONSHIP_TO_THE_HEAD','Relationship To The Head','FALSE')
ON CONFLICT (attribute_id) DO NOTHING;
