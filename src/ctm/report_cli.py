"""ctm-report — build a trial match report (PDF or live preview).

Usage:
  ctm-report --pt normalized.json --matches matches.json --engine mm [--preview] [--db NAME] [output]
  ctm-report --mock [--preview]
"""
import argparse
import json
import os
import platform
import sys
from pathlib import Path

_KNOWN_ENGINES = ("mm",)


def _fix_macos_weasyprint_path() -> None:
    if platform.system() == "Darwin":
        homebrew_lib = "/opt/homebrew/lib"
        if os.path.isdir(homebrew_lib):
            os.environ["DYLD_LIBRARY_PATH"] = (
                homebrew_lib + os.pathsep + os.environ.get("DYLD_LIBRARY_PATH", "")
            )


def _write_to_mongo(pt_path: str, matches_path: str, db_name: str) -> None:
    try:
        from pymongo import MongoClient
    except ImportError:
        print("Error: pymongo not installed.", file=sys.stderr)
        sys.exit(1)

    pt_data = json.loads(Path(pt_path).read_text())
    matches_data = json.loads(Path(matches_path).read_text())
    uri = os.getenv("CTM_MONGO_URI", "mongodb://localhost:27017")
    db = MongoClient(uri)[db_name]

    clinical = pt_data.get("clinical", {})
    clinical_id = None
    if clinical:
        sample_id = clinical.get("SAMPLE_ID")
        db["clinical"].replace_one({"SAMPLE_ID": sample_id}, clinical, upsert=True)
        doc = db["clinical"].find_one({"SAMPLE_ID": sample_id}, {"_id": 1})
        clinical_id = doc["_id"] if doc else None
        print(f"  clinical: upserted SAMPLE_ID={sample_id}")

    genomic = pt_data.get("genomic", [])
    if genomic and clinical:
        sample_id = clinical.get("SAMPLE_ID")
        db["genomic"].delete_many({"SAMPLE_ID": sample_id})
        if clinical_id:
            for g in genomic:
                g["CLINICAL_ID"] = clinical_id
        db["genomic"].insert_many(genomic)
        print(f"  genomic: inserted {len(genomic)} docs")

    trial_matches = matches_data.get("trial_match", [])
    if trial_matches and clinical:
        sample_id = clinical.get("SAMPLE_ID")
        db["trial_match"].delete_many({"sample_id": sample_id})
        db["trial_match"].insert_many(trial_matches)
        print(f"  trial_match: inserted {len(trial_matches)} docs")

    print(f"  → {uri}/{db_name}")


def _run_preview(pt_path: str, matches_path: str, engine: str) -> None:
    from livereload import Server
    from ctm.reports.builder import BASE_DIR, render_html_from_pt_and_matches

    output_dir = BASE_DIR / "output"
    output_file = output_dir / "report.html"

    def build():
        output_dir.mkdir(exist_ok=True)
        output_file.write_text(render_html_from_pt_and_matches(pt_path, matches_path, engine))

    build()
    server = Server()
    server.watch(str(BASE_DIR / "templates" / "*.html"), build)
    server.watch(str(BASE_DIR / "static" / "*.css"), build)
    server.watch(pt_path, build)
    server.watch(matches_path, build)
    server.serve(root=str(output_dir), port=5500, open_url_delay=1,
                 default_filename="report.html")


def _run_mock_preview() -> None:
    from livereload import Server
    from ctm.reports.builder import BASE_DIR, render_html

    output_dir = BASE_DIR / "output"
    output_file = output_dir / "report.html"

    def build():
        output_dir.mkdir(exist_ok=True)
        output_file.write_text(render_html(use_real=False))

    build()
    server = Server()
    server.watch(str(BASE_DIR / "templates" / "*.html"), build)
    server.watch(str(BASE_DIR / "static" / "*.css"), build)
    server.watch(str(BASE_DIR / "data" / "mock" / "*.json"), build)
    server.serve(root=str(output_dir), port=5500, open_url_delay=1,
                 default_filename="report.html")


def main() -> None:
    _fix_macos_weasyprint_path()

    from ctm.reports.builder import BASE_DIR, render_html, render_html_from_pt_and_matches

    parser = argparse.ArgumentParser(prog="ctm-report")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output PDF path (default: output/report.pdf)")
    parser.add_argument("--mock", action="store_true", help="Use data/mock/ data")
    parser.add_argument("--pt", dest="pt_path", metavar="PATH",
                        help="Normalized patient JSON from ctm-mm raw-to-mm")
    parser.add_argument("--matches", metavar="PATH",
                        help="Match results JSON from the match engine")
    parser.add_argument("--engine", metavar="ENGINE",
                        help=f"Match engine that produced --matches (one of: {', '.join(_KNOWN_ENGINES)})")
    parser.add_argument("--preview", action="store_true",
                        help="Spin up livereload server instead of building PDF")
    parser.add_argument("--db", metavar="NAME",
                        help="Also write patient + match data to MongoDB database NAME")
    args = parser.parse_args()

    use_mock = args.mock or (not args.pt_path and not args.matches)

    if not use_mock:
        missing = [f for flag, f in [
            (args.pt_path, "--pt"),
            (args.matches, "--matches"),
            (args.engine, "--engine"),
        ] if not flag]
        if missing:
            parser.error(f"required: {', '.join(missing)}")
        if args.engine not in _KNOWN_ENGINES:
            parser.error(f"--engine must be one of: {', '.join(_KNOWN_ENGINES)}")

    if args.db and not use_mock:
        print(f"Writing to MongoDB ({args.db}) ...")
        _write_to_mongo(args.pt_path, args.matches, args.db)

    if args.preview:
        if use_mock:
            _run_mock_preview()
        else:
            _run_preview(args.pt_path, args.matches, args.engine)
        return

    from weasyprint import HTML

    if use_mock:
        html = render_html(use_real=False)
    else:
        html = render_html_from_pt_and_matches(args.pt_path, args.matches, args.engine)

    output_path = Path(args.output) if args.output else BASE_DIR / "output" / "report.pdf"
    output_path.parent.mkdir(exist_ok=True, parents=True)
    HTML(string=html).write_pdf(str(output_path))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
