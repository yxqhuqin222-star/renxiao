"""Export the current dashboard homepage as a GitHub Pages static snapshot."""

from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from app import app


OUTPUT_DIR = PROJECT_DIR / "docs"
OUTPUT_PATH = OUTPUT_DIR / "index.html"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with app.test_client() as client:
        response = client.get("/")
        response.raise_for_status = lambda: None
        if response.status_code != 200:
            raise SystemExit(f"GET / failed: {response.status_code}")
        html = response.get_data(as_text=True)
    banner = (
        "<!-- Static GitHub Pages snapshot generated from Flask. "
        "Upload and download actions require the live Flask app. -->\n"
    )
    OUTPUT_PATH.write_text(banner + html, encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
