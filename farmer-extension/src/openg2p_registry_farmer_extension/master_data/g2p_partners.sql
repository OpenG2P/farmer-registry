-- ---------------------------------------------------------------------------
-- Incoming partners for connector-fed sources (MASTER DATA database).
--
-- Partner API resolves $.body.header.sender_id against
-- g2p_partners.partner_mnemonic and rejects unknown senders with
-- PARTNER_NOT_REGISTERED. Seeded into the shared master_data DB by
-- docker/db-seed (step 1b), not the registry DB.
-- ---------------------------------------------------------------------------
INSERT INTO
    "public"."g2p_partners" (
        "partner_id",
        "partner_mnemonic",
        "keymanager_reference_id",
        "is_active"
    )
VALUES
    (
        'f0a1b2c3-d4e5-4f67-8901-23456789abd1',
        'odk-farmer',
        'odk-farmer-keyref',
        TRUE
    )
ON CONFLICT DO NOTHING;
