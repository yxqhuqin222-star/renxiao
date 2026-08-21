"""Export a read-only public snapshot of the dashboard to docs/index.html.

Strips every management surface (upload form, download link, filter forms)
so the published GitHub Pages page is safe to expose without a backend.
Viewing-only: trend chart + result table + summary are rendered at export time.
"""

from pathlib import Path
import re
import shutil
import sys

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from app import app  # noqa: E402

OUTPUT_DIR = PROJECT_DIR / "docs"
OUTPUT_PATH = OUTPUT_DIR / "index.html"
FAVICON_SRC = PROJECT_DIR / "favicon_io"

FAVICON_FILES = [
    "apple-touch-icon.png",
    "favicon-32x32.png",
    "favicon-16x16.png",
    "favicon.ico",
    "site.webmanifest",
]


def strip_management(html: str) -> str:
    # Filter card (contains the table filter form + reset links).
    html = re.sub(
        r'<section class="card" aria-labelledby="filter-title">.*?</section>',
        "",
        html,
        flags=re.S,
    )
    # Chart range/control form (requires Flask backend).
    html = re.sub(
        r'<form class="controls chart-controls js-range-form"[^>]*>.*?</form>',
        "",
        html,
        flags=re.S,
    )
    # Upload form (writes to the database).
    html = re.sub(r'<form action="/upload"[^>]*>.*?</form>', "", html, flags=re.S)
    # Download link (serves result.xlsx).
    html = re.sub(
        r'<a class="btn btn-secondary" href="/download[^"]*">.*?</a>',
        "",
        html,
        flags=re.S,
    )
    return html


def fix_favicons(html: str) -> str:
    for fname in FAVICON_FILES:
        src = FAVICON_SRC / fname
        if src.exists():
            shutil.copy(src, OUTPUT_DIR / fname)
        html = html.replace(f"/favicon_io/{fname}", fname)
    return html


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with app.test_client() as client:
        response = client.get("/")
        if response.status_code != 200:
            raise SystemExit(f"GET / failed: {response.status_code}")
        html = response.get_data(as_text=True)

    html = strip_management(html)
    html = fix_favicons(html)

    banner = (
        "<!-- Read-only public snapshot generated from Flask. "
        "Upload, download, and filtering require the live Flask app. -->\n"
    )
    OUTPUT_PATH.write_text(banner + html, encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
