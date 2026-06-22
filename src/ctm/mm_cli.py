"""ctm-mm — MatchMiner import tooling CLI.

Usage:
  ctm-mm raw-to-mm PATH/TO/patient_data_template.xlsx [options]

Options:
  --pt-uuid N    Process only patient with this pt_uuid (default: all patients)
  --dry-run      Print generated documents as JSON, do not write to MongoDB
  --out PATH     Save JSON output to file (implies --dry-run)
  --mongo-uri    Override CTM_MONGO_URI env var
  --db NAME      MongoDB database name (default: matchminer)
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="ctm-mm",
        description="CTM → MatchMiner import tooling",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "raw-to-mm",
        help="Read Excel template → upsert MatchMiner clinical + genomic docs in MongoDB",
    )
    p.add_argument("excel", metavar="EXCEL", help="Path to patient_data_template.xlsx")
    p.add_argument("--pt-uuid", type=int, dest="pt_uuid", metavar="N",
                   help="Filter to one patient by pt_uuid")
    p.add_argument("--dry-run", action="store_true",
                   help="Print output JSON without writing to MongoDB")
    p.add_argument("--out", metavar="PATH",
                   help="Save output JSON to this file (implies --dry-run)")
    p.add_argument("--mongo-uri", dest="mongo_uri", metavar="URI",
                   help="Override CTM_MONGO_URI env var")
    p.add_argument("--db", dest="db_name", default="matchminer", metavar="NAME",
                   help="MongoDB database name (default: matchminer)")

    args = parser.parse_args()

    if args.command == "raw-to-mm":
        _cmd_raw_to_mm(args)


def _cmd_raw_to_mm(args) -> None:
    from ctm.transformers.excel_reader import read_and_normalize
    from ctm.transformers.to_matchminer import to_clinical, to_genomic_docs

    excel_path = Path(args.excel)
    if not excel_path.exists():
        print(f"Error: file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {excel_path} ...")
    patients, metadata, findings = read_and_normalize(excel_path, pt_uuid_filter=args.pt_uuid)

    if not patients:
        print("No patients found (check --pt-uuid or pt_general sheet).", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(patients)} patient(s)  {len(metadata)} report(s)  {len(findings)} finding(s)")

    # Group by patient
    findings_by_pt: dict[int, list] = defaultdict(list)
    for f in findings:
        findings_by_pt[f.pt_uuid].append(f)

    metadata_by_pt: dict[int, list] = defaultdict(list)
    for m in metadata:
        metadata_by_pt[m.pt_uuid].append(m)

    all_clinical: list[dict] = []
    all_genomic: list[dict] = []

    for patient in patients:
        pt_findings = findings_by_pt[patient.pt_uuid]
        pt_meta = metadata_by_pt[patient.pt_uuid]

        dates = [m.date_completed for m in pt_meta if m.date_completed]
        report_date = max(dates).isoformat() if dates else None

        clinical = to_clinical(patient, pt_findings, report_date=report_date)
        genomic = to_genomic_docs(patient, pt_findings, clinical_id=None)

        all_clinical.append(clinical)
        all_genomic.extend(genomic)

        print(f"  pt_uuid={patient.pt_uuid}  mrn={patient.mrn}  "
              f"→ {len(genomic)} genomic doc(s)")

    dry_run = args.dry_run or args.out is not None

    if dry_run:
        output = {
            "clinical": all_clinical,
            "genomic": all_genomic,
        }
        json_str = json.dumps(output, indent=2, default=str)
        if args.out:
            Path(args.out).write_text(json_str)
            print(f"Saved → {args.out}")
        else:
            print(json_str)
        return

    # ── Write to MongoDB ───────────────────────────────────────────────────────
    try:
        from pymongo import MongoClient
    except ImportError:
        print("Error: pymongo not installed.", file=sys.stderr)
        sys.exit(1)

    uri = args.mongo_uri or os.getenv("CTM_MONGO_URI", "mongodb://localhost:27017")
    db_name = args.db_name or os.getenv("MM_MONGO_DB", "matchminer")
    db = MongoClient(uri)[db_name]

    n_clinical = 0
    n_genomic = 0

    for clinical_doc in all_clinical:
        sample_id = clinical_doc["SAMPLE_ID"]

        # Upsert clinical (replace entire doc if exists)
        db["clinical"].replace_one({"SAMPLE_ID": sample_id}, clinical_doc, upsert=True)
        inserted = db["clinical"].find_one({"SAMPLE_ID": sample_id}, {"_id": 1})
        clinical_id = inserted["_id"]

        # Replace all genomic docs for this patient
        pt_genomic = [g for g in all_genomic if g["SAMPLE_ID"] == sample_id]
        if pt_genomic:
            db["genomic"].delete_many({"SAMPLE_ID": sample_id})
            for g in pt_genomic:
                g["CLINICAL_ID"] = clinical_id
            db["genomic"].insert_many(pt_genomic)
            n_genomic += len(pt_genomic)

        n_clinical += 1

    print(f"\nUpserted {n_clinical} clinical doc(s)  {n_genomic} genomic doc(s)")
    print(f"  → {uri}/{db_name}  (collections: clinical, genomic)")


if __name__ == "__main__":
    main()
