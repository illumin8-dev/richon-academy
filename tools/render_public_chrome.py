"""Render/check canonical shared chrome in public source pages."""
import argparse
from pathlib import Path
import shared_chrome as chrome

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "index.html": "landing",
    "apply.html": "portal",
    "signup-guide.html": "portal",
    "privacy.html": "document",
    "terms.html": "document",
}


def rendered(path: Path, variant: str) -> str:
    page = path.read_text()
    page = chrome.replace_wrapped(page, "header", chrome.render_header(variant))
    page = chrome.replace_wrapped(page, "footer", chrome.footer())
    page = chrome.ensure_font_link(page)
    return page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.check == args.write:
        raise SystemExit("choose exactly one of --check or --write")
    drift = []
    for name, variant in PAGES.items():
        path = ROOT / name
        expected = rendered(path, variant)
        if args.check:
            if path.read_text() != expected:
                drift.append(name)
        else:
            path.write_text(expected)
    if drift:
        raise SystemExit("Public shared chrome drift: " + ", ".join(drift))
    if args.check:
        print("PASS: public pages use canonical shared header/footer renderer")
    else:
        print("Rendered canonical public site chrome")


if __name__ == "__main__":
    main()
