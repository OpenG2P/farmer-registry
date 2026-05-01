# OpenG2P Registry Farmer Extension

Extension package for the [OpenG2P Registry Platform](https://github.com/OpenG2P/openg2p-registry-gen2-core) that implements the domain of a **Farmer Registry** — a registry of farmers, their households, lands, crops, livestock, farm inputs and membership details, used to target, enrol and deliver agricultural and social-protection programmes.

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
| `Crop` | `g2p_register_crops` | Land |
| `FarmInputs` | `g2p_register_farm_inputs` | Farmer |
| `Livestock` | `g2p_register_livestocks` | Farmer |

Every register and supporting table has a `*_history` twin for version snapshots.

> Verification / audit trail is provided by the registry-core platform itself (`g2p_register_verifications`); we do not duplicate it here.

## Install (from source)

```bash
pip install farmer-extension/
```
