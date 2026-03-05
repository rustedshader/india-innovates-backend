"""Read-only API routes for serving generated domain reports."""

import json
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from models.database import SessionLocal
from models.domain_report import DomainReport
from agents.report import DOMAIN_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/reports")
def list_reports():
    """List all available domains and their latest report timestamps."""
    db = SessionLocal()
    try:
        # Get latest report per domain
        subquery = (
            select(
                DomainReport.domain,
                func.max(DomainReport.generated_at).label("latest"),
            )
            .group_by(DomainReport.domain)
            .subquery()
        )

        results = db.execute(
            select(subquery.c.domain, subquery.c.latest)
        ).all()

        domain_status = {}
        for row in results:
            domain_status[row.domain] = {
                "domain": row.domain,
                "generated_at": row.latest.isoformat() if row.latest else None,
            }

        # Include all configured domains, even if no report exists yet
        all_domains = []
        for domain in DOMAIN_CONFIG:
            if domain in domain_status:
                all_domains.append(domain_status[domain])
            else:
                all_domains.append({
                    "domain": domain,
                    "generated_at": None,
                })

        return {"domains": all_domains}
    finally:
        db.close()


@router.get("/reports/{domain}")
def get_report(domain: str):
    """Get the latest report for a specific domain."""
    if domain not in DOMAIN_CONFIG:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown domain: {domain}. Must be one of {list(DOMAIN_CONFIG.keys())}",
        )

    db = SessionLocal()
    try:
        report = db.execute(
            select(DomainReport)
            .where(DomainReport.domain == domain)
            .order_by(DomainReport.generated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not report:
            raise HTTPException(
                status_code=404,
                detail=f"No report generated yet for domain: {domain}",
            )

        return {
            "domain": report.domain,
            "date_range": report.date_range,
            "generated_at": report.generated_at.isoformat(),
            "report": json.loads(report.content),
        }
    finally:
        db.close()
