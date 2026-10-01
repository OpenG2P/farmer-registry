-- Farmer poverty score. Household already has size_of_group and number_of_children.
-- These attributes are columns on g2p_register_farmers. Weights sum to 1.
-- Categorical fields carry a lookup so a stored enum becomes a number.

BEGIN;

INSERT INTO g2p_register_score_definitions (
  score_definition_id, register_mnemonic, score_type, is_enabled
) VALUES (
  'f4a0c0de-7b11-4c3a-9e01-000000000f01',
  'Farmer',
  'POVERTY',
  true
)
ON CONFLICT (register_mnemonic, score_type) DO UPDATE
SET is_enabled = EXCLUDED.is_enabled;

INSERT INTO g2p_register_score_contributing_attributes (
  contributing_attribute_id, register_mnemonic, score_type, attribute_name,
  attribute_computation_required, attribute_computation_value, attribute_weightage
) VALUES
  (
    'f4a0c0de-7b11-4c3a-9e01-000000000f11',
    'Farmer', 'POVERTY', 'estimated_age',
    false, NULL, 0.25
  ),
  (
    'f4a0c0de-7b11-4c3a-9e01-000000000f12',
    'Farmer', 'POVERTY', 'education_level',
    true,
    '{"ILLITERATE": 1.0, "CAN_READ_AND_WRITE": 0.6, "BASIC": 0.4, "INTERMEDIARY": 0.2, "HIGHER_EDUCATION": 0.0}'::json,
    0.35
  ),
  (
    'f4a0c0de-7b11-4c3a-9e01-000000000f13',
    'Farmer', 'POVERTY', 'source_of_income',
    true,
    '{"GOVERNMENT_NGO_SUPPORT": 1.0, "OTHERS": 0.7, "LIVESTOCK_PRODUCTION": 0.4, "CROP_PRODUCTION": 0.2}'::json,
    0.25
  ),
  (
    'f4a0c0de-7b11-4c3a-9e01-000000000f14',
    'Farmer', 'POVERTY', 'disability_severity',
    true,
    '{"CANNOT_DO_AT_ALL": 1.0, "A_LOT_OF_DIFFICULTY": 0.75, "SOME_DIFFICULTY": 0.4, "NO_DIFFICULTY": 0.0}'::json,
    0.15
  )
ON CONFLICT (register_mnemonic, score_type, attribute_name) DO UPDATE
SET attribute_computation_required = EXCLUDED.attribute_computation_required,
    attribute_computation_value = EXCLUDED.attribute_computation_value,
    attribute_weightage = EXCLUDED.attribute_weightage;

COMMIT;
