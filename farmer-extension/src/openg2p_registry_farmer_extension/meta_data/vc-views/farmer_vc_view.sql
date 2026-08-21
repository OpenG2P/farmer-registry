-- Farmer Registry — source view for verifiable credential issuance.
--
-- The Registry Platform owns the issuance machinery but deliberately owns no
-- view: the claim fields differ per registry, so each manifestation supplies its
-- own. This is the Farmer Registry's.
--
-- Contract expected by the Agent Portal API (RegistryLookupService):
--   internal_record_id  REQUIRED — the key issuance is done on. The national ID
--                       the agent types only *locates* the record; the credential
--                       is always built from this.
--   foundational_id     REQUIRED — the national ID, matched when the agent looks
--                       the farmer up, and what eSignet's authenticated subject
--                       is checked against by the registry core.
--   record_status       optional but recommended — lets the API tell the agent
--                       *why* a record cannot be issued to, instead of a bare
--                       "not found".
--   record_name         optional — shown to the agent to confirm the right person.
--   everything else     becomes a credential claim.
--
-- Deliberately NOT exposed: income, disability, education, land, livestock and
-- the rest of the farmer profile. A printed credential is a bearer document that
-- gets handed to shopkeepers and officials, so it carries identity only. Adding
-- a column here puts it on paper in someone's pocket — and into the QR.
--
-- Applied automatically by the db-seed Job (it runs every *.sql under meta_data/
-- after the model migration), so it deploys with the registry.

CREATE OR REPLACE VIEW farmer_vc_view AS
SELECT
    r.internal_record_id                                   AS "internal_record_id",
    r.foundational_id                                      AS "foundational_id",
    r.record_status                                        AS "record_status",
    r.record_name                                          AS "record_name",

    -- Claims. Aliases are quoted because Postgres lowercases unquoted
    -- identifiers, and these must match the ${...} variables in the credential
    -- template exactly.
    r.functional_record_id                                 AS "functionalRecordId",
    -- concat_ws skips NULLs outright; NULLIF maps '' to NULL so an empty
    -- middle name collapses too. Concatenating with literal spaces instead
    -- leaves "Abebe  Berhanu" (two spaces) printed on the credential.
    NULLIF(CONCAT_WS(' ',
        NULLIF(r.first_name, ''),
        NULLIF(r.middle_name, ''),
        NULLIF(r.last_name, '')
    ), '')                                                 AS "fullName",
    -- Dates as text so the credential carries clean string values rather than a
    -- driver-dependent rendering.
    TO_CHAR(r.birth_date, 'YYYY-MM-DD')                    AS "dateOfBirth",
    r.gender                                               AS "gender"
FROM g2p_register_farmers r
-- Active records only. The API also checks record_status, but filtering here
-- means an archived farmer is never even a candidate.
WHERE r.record_status = 'ACTIVE'
  AND r.foundational_id IS NOT NULL;

COMMENT ON VIEW farmer_vc_view IS
  'Identity claims for farmer verifiable credentials. Keyed on internal_record_id; looked up by foundational_id. Identity fields only — see the file header before adding columns.';
