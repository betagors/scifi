"""Theorem-Proof and Appendix Completeness Sentinel module (euclid)."""

from scifi.proofs.auditor import audit_latex_proofs
from scifi.proofs.models import (
    ProofAuditResult,
    ProofIssueCategory,
    TheoremProofRecord,
)

__all__ = [
    "audit_latex_proofs",
    "ProofAuditResult",
    "ProofIssueCategory",
    "TheoremProofRecord",
]
