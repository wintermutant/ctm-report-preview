"""ctm-report — build a trial match report (PDF or live preview).

Usage:
  ctm-report --pt normalized.json --matches matches.json --engine mm [--preview] [--out PATH]
"""
import argparse
import os
import platform
from pathlib import Path

_KNOWN_ENGINES = ("mm",)


def _fix_macos_weasyprint_path() -> None:
    if platform.system() == "Darwin":
        homebrew_lib = "/opt/homebrew/lib"
        if os.path.isdir(homebrew_lib):
            os.environ["DYLD_LIBRARY_PATH"] = (
                homebrew_lib + os.pathsep + os.environ.get("DYLD_LIBRARY_PATH", "")
            )


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


def main() -> None:
    _fix_macos_weasyprint_path()

    from ctm.reports.builder import BASE_DIR, render_html_from_pt_and_matches

    parser = argparse.ArgumentParser(prog="ctm-report")
    parser.add_argument("--out", metavar="PATH", default=None,
                        help="Output PDF path (default: output/report.pdf)")
    parser.add_argument("--pt", dest="pt_path", metavar="PATH", required=True,
                        help="Normalized patient JSON from ctm-mm patients")
    parser.add_argument("--matches", metavar="PATH", required=True,
                        help="Match results JSON from the match engine")
    parser.add_argument("--engine", metavar="ENGINE", required=True,
                        help=f"Match engine that produced --matches (one of: {', '.join(_KNOWN_ENGINES)})")
    parser.add_argument("--preview", action="store_true",
                        help="Spin up livereload server instead of building PDF")
    args = parser.parse_args()

    if args.engine not in _KNOWN_ENGINES:
        parser.error(f"--engine must be one of: {', '.join(_KNOWN_ENGINES)}")

    if args.preview:
        _run_preview(args.pt_path, args.matches, args.engine)
        return

    from weasyprint import HTML

    html = render_html_from_pt_and_matches(args.pt_path, args.matches, args.engine)
    output_path = Path(args.out) if args.out else BASE_DIR / "output" / "report.pdf"
    output_path.parent.mkdir(exist_ok=True, parents=True)
    HTML(string=html).write_pdf(str(output_path))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
