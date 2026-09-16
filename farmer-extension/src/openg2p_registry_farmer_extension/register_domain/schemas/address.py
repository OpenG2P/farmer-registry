from typing import Optional


class G2PAddressLinesSchema:
    """address_line_1 / address_line_2 for register and intake schemas.

    The platform's G2PGeo model has both columns, but its G2PGeoSchema does
    not (only G2PGeoHistorySchema does). A change request is applied through
    the schema, so without these fields an approved edit to the address lines
    was silently dropped while the rest of the location section was written.
    """

    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
