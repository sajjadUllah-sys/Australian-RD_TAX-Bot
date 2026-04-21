"""
backend_client.py
─────────────────
Phase 4 — Django backend integration.

  post_to_django_backend() — packages the final report and POSTs it to the
                             Django REST API endpoint for permanent storage.

The real requests.post() call is written out and commented in-place so the
Django developer can see the exact payload structure without any ambiguity.
"""

import datetime
import os

import requests


def post_to_django_backend(
    intake: dict,
    report_text: str,
    pdf_bytes: bytes,
) -> dict:
    """
    POST the completed RDTI submission to the Django backend.

    Django endpoint (expected):
        POST /api/rdti/submissions/
        Authorization: Bearer <DJANGO_API_TOKEN>
        Content-Type:  multipart/form-data

    Payload fields:
        company_name   (str)
        abn            (str)
        contact_person (str)
        industry       (str)
        project_year   (int)
        project_type   (str)
        report_text    (str)
        report_pdf     (file — application/pdf)

    Environment variables required:
        DJANGO_API_URL    — e.g. https://yourdomain.com/api/rdti/submissions/
        DJANGO_API_TOKEN  — Django REST Framework token or JWT

    Args:
        intake:      Phase 1 intake dict.
        report_text: Plain-text report string.
        pdf_bytes:   Raw PDF bytes from generate_pdf().

    Returns:
        dict — API response JSON (or mock response if real call is commented out).
    """
    django_api_url   = os.getenv("DJANGO_API_URL",   "http://localhost:8000/api/rdti/submissions/")
    django_api_token = os.getenv("DJANGO_API_TOKEN", "<<DJANGO_API_TOKEN>>")

    # ── Real POST — uncomment once the Django endpoint is live ───────────────
    # try:
    #     response = requests.post(
    #         django_api_url,
    #         headers={"Authorization": f"Bearer {django_api_token}"},
    #         data={
    #             "company_name":   intake["company_name"],
    #             "abn":            intake["abn"],
    #             "contact_person": intake["contact_person"],
    #             "industry":       intake["industry"],
    #             "project_year":   intake["project_year"],
    #             "project_type":   intake["project_type"],
    #             "report_text":    report_text,
    #         },
    #         files={
    #             "report_pdf": ("rdti_report.pdf", pdf_bytes, "application/pdf")
    #         },
    #         timeout=15,
    #     )
    #     response.raise_for_status()
    #     return response.json()
    # except requests.RequestException as exc:
    #     return {"status": "error", "detail": str(exc)}
    # ─────────────────────────────────────────────────────────────────────────

    # Mock response (remove once real POST is enabled above)
    submission_id = (
        f"RDTI-{intake['abn'][-4:]}-"
        f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    return {
        "status":         "success",
        "submission_id":  submission_id,
        "endpoint_called": django_api_url,
        "payload_keys":   [
            "company_name", "abn", "contact_person", "industry",
            "project_year", "project_type", "report_text", "report_pdf",
        ],
        "message": "Submission received and queued for administrative review.",
    }
