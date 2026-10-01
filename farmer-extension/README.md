# OpenG2P Registry Farmer Extension

Extension package for the [OpenG2P Registry Platform](https://github.com/OpenG2P/openg2p-registry-gen2-core) that implements the domain of a **Farmer Registry** — a registry of farmers, their households, lands, livestock, farm inputs and membership details, used to target, enrol and deliver agricultural and social-protection programmes.

Follows the same layout as [`openg2p-registry-nsr-extension`](https://github.com/OpenG2P/national-social-registry/tree/develop/nsr-extension).

## Registers

| Mnemonic | Table | Extends |
|---|---|---|
| `Farmer` | `g2p_register_farmers` | `G2PRegister`, `G2PPerson`, `G2PGeo` |
| `Household` | `g2p_register_households` | `G2PRegister`, `G2PGeo` |
| `HouseholdMember` | `g2p_register_household_members` | `G2PRegister`, `G2PPerson` |

## Supporting Tables

| Mnemonic | Table | Parent (via `link_internal_record_id`) |
|---|---|---|
| `PovertyScore` | `g2p_register_poverty_scores` | Household |
| `MembershipDetails` | `g2p_register_membership_details` | Farmer |
| `Land` | `g2p_register_lands` | Farmer |
| `FarmInputs` | `g2p_register_farm_inputs` | Farmer |
| `Livestock` | `g2p_register_livestocks` | Farmer |

Every register and supporting table has a `*_history` twin for version snapshots.

### Main crops, not crop records

The Farmer Registry holds no crop records. What a farmer sows each season, and
where, belongs to the Crop Sown Registry. The farmer record carries only
`main_crops`: the crops the farmer mainly grows, as declared at registration — a
JSONB list of Master Data `CROP_COMMODITY` codes (e.g. `["CROP_TEFF",
"CROP_WHEAT"]`), entered with a multi-select bound to that code list in the
farmer's socio-economic section. No dates, areas or seasons.

An install that predates this keeps its `g2p_register_crops` tables and rows;
nothing in the Farmer Registry reads them. On upgrade the migration adds the
`main_crops` column to the existing farmer tables, and
`meta_data/zz-upgrades/retire_crop_register_add_main_crops.sql` removes the Crop
register's tab, sections and definition and adds the Main crops widget.

> Verification / audit trail is provided by the registry-core platform itself (`g2p_register_verifications`); we do not duplicate it here.

## Install (from source)

```bash
pip install farmer-extension/
```
