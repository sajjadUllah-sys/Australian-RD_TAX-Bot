"""
abn_validator.py
────────────────
Phase 2 — Two-tier ABN validation.

  Tier 1: validate_abn_modulo89()   — local Modulo-89 checksum (ATO spec)
  Tier 2: mock_abr_api_call()       — async mock of the ABR XML Search API

Both functions are pure Python with no Streamlit dependency so they can be
imported and tested independently (e.g. by the Django backend test suite).
"""

import asyncio
import os
import re
from difflib import SequenceMatcher

from config import ABN_WEIGHTS


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — Modulo-89 checksum
# ─────────────────────────────────────────────────────────────────────────────

def validate_abn_modulo89(abn: str) -> tuple[bool, str]:
    """
    Validate an ABN using the ATO Modulo-89 algorithm.

    Algorithm:
      1. Strip whitespace; string must be exactly 11 digits.
      2. Subtract 1 from the first (leftmost) digit.
      3. Multiply each of the 11 resulting digits by its weighting factor
         (ABN_WEIGHTS = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]).
      4. Sum the 11 products.
      5. If  total_sum % 89 == 0  →  ABN is structurally valid.

    Args:
        abn: Raw ABN string (spaces allowed, e.g. "51 824 753 556").

    Returns:
        (is_valid: bool, message: str)
    """
    abn_clean = re.sub(r"\s", "", abn)

    if not abn_clean.isdigit() or len(abn_clean) != 11:
        return False, "ABN must be exactly 11 numeric digits."

    digits = [int(d) for d in abn_clean]
    digits[0] -= 1  # Step 2

    weighted_sum = sum(d * w for d, w in zip(digits, ABN_WEIGHTS))

    if weighted_sum % 89 == 0:
        return True, "ABN structure is mathematically valid (Modulo-89 passed)."
    else:
        return (
            False,
            f"ABN failed Modulo-89 checksum "
            f"(weighted_sum={weighted_sum}, remainder={weighted_sum % 89}).",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — ABR API (mock)
# ─────────────────────────────────────────────────────────────────────────────

async def mock_abr_api_call(abn: str, company_name: str) -> dict:
    """
    Simulate a call to the Australian Business Register XML Search API.

    Real endpoint:
        GET https://abr.business.gov.au/abrxmlsearch/
                AbrXmlSearch.asmx/SearchByABNv202001
            ?searchString=<ABN>
            &includeHistoricalDetails=N
            &authenticationGuid=<GUID>

    Production notes for the Django backend developer:
        - Store authenticationGuid in the environment (never hardcode).
        - The real response is XML; parse <entityName> or <mainName> for the
          legal business name.
        - Use string-similarity ≥ 0.60 as a soft match threshold, but always
          store the raw similarity score for auditing.
        - Wrap in try/except aiohttp.ClientError for network resilience.

    Args:
        abn:          11-digit ABN string (no spaces).
        company_name: Name as entered by the user in the intake form.

    Returns:
        dict with keys:
            api_name        — legal name returned by the (mock) API
            similarity_score — SequenceMatcher ratio  [0.0 – 1.0]
            match           — True if similarity_score >= 0.60
            payload_sent    — exact query parameters that would be sent
    """
    # Simulate ~500 ms network latency
    await asyncio.sleep(0.5)

    # ── Real aiohttp call (uncomment when live ABR access is available) ───────
    # import aiohttp
    # ABR_GUID = os.getenv("ABR_AUTH_GUID")
    # url = (
    #     "https://abr.business.gov.au/abrxmlsearch/"
    #     "AbrXmlSearch.asmx/SearchByABNv202001"
    # )
    # params = {
    #     "searchString":           abn,
    #     "includeHistoricalDetails": "N",
    #     "authenticationGuid":     ABR_GUID,
    # }
    # async with aiohttp.ClientSession() as session:
    #     async with session.get(url, params=params, timeout=10) as resp:
    #         xml_text = await resp.text()
    # # Parse XML → extract legal name:
    # #   import xml.etree.ElementTree as ET
    # #   root = ET.fromstring(xml_text)
    # #   ns   = {"abr": "http://abr.business.gov.au/ABRXMLSearch/"}
    # #   name = root.findtext(".//abr:entityName", namespaces=ns) or ""
    # ─────────────────────────────────────────────────────────────────────────

    # Mock: append "PTY LTD" to simulate a registered legal name
    mock_legal_name = (
        company_name.upper() + " PTY LTD"
        if "PTY" not in company_name.upper()
        else company_name.upper()
    )

    similarity = SequenceMatcher(
        None,
        company_name.lower().strip(),
        mock_legal_name.lower().strip(),
    ).ratio()

    payload_sent = {
        "searchString":             abn,
        "includeHistoricalDetails": "N",
        "authenticationGuid":       "<<ABR_AUTH_GUID — load from env>>",
    }

    return {
        "api_name":        mock_legal_name,
        "similarity_score": round(similarity, 4),
        "match":           similarity >= 0.60,
        "payload_sent":    payload_sent,
    }
