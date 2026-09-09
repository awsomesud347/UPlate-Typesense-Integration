"""Provenance gate.

"We have no verified data about this item" and "this item verifiably contains no
peanuts" are completely different claims. When ANY hard exclusion is active,
unverified items are withheld — even if their allergen list looks clean.
Do not optimize this down to checking the allergens array. Ever.
"""

PROVENANCE_TIERS = ["OFFICIAL_FEED", "CHAIN_PUBLISHED", "CROWD_VERIFIED", "ESTIMATED"]

# Appended to the explicit filter_by whenever a hard exclusion is active.
VERIFICATION_GATE = "allergen_verified:true"
