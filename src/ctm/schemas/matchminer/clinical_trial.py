"""MatchMiner CTML (Clinical Trial Markup Language) schema.

One document per clinical trial in the MatchMiner `trial` collection.
The `match` field holds the nested CTML genomic/clinical criteria tree;
it is left empty here and populated downstream (manually or by an extractor).

Reference: https://matchminer.gitbook.io
"""
from typing import Any
from pydantic import BaseModel, Field


class CtmlEligibility(BaseModel):
    inclusion: list[str] = Field(default_factory=list)
    exclusion: list[str] = Field(default_factory=list)


class MatchMinerClinicalTrial(BaseModel):
    protocol_no: str | None = None
    nct_id: str | None = None
    title: str | None = None            # full title
    short_title: str | None = None      # abbreviated title
    status: str | None = None           # e.g. "Open to Accrual"
    phase: str | None = None            # e.g. "Phase II"
    sponsor: str | None = None
    principal_investigator: str | None = None
    age_group: str | None = None        # Adult | Pediatric | Both
    gender: str | None = None           # All | Male | Female
    disease_site: list[str] = Field(default_factory=list)
    summary: str | None = None
    oncology_group: str | None = None
    management_group: str | None = None
    eligibility: CtmlEligibility = Field(default_factory=CtmlEligibility)
    drug_list: list[str] = Field(default_factory=list)
    match: list[Any] = Field(default_factory=list)  # CTML match criteria tree
