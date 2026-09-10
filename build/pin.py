#!/usr/bin/env python3
"""Create a Pinterest Pin from a source post using watermarked images.

Usage: python pin.py build/posts/alan

Reads credentials from build/notes/PINTEREST (simple key=value lines). Expects at least
`access_token` and board mappings for the logical boards the script selects.

Behaviour:
- Parse the source post file in `build/posts/<slug>` for header fields (`title`, `type`,
    `media`, `tags`) and the markdown body for additional images.
- Choose `board_id` according to the post `type` and `media` following the mapping rules
    in build/notes/pinterest.txt.
- Use the watermarked image URLs (https://thomasguest.art/images/watermarked/<name>) as
    the media source. If the post contains multiple images, create a carousel pin using
    `multiple_image_urls`.
"""
from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("pin")


BUILD_DIR = Path(__file__).resolve().parent
ROOT = BUILD_DIR.parent
CONFIG_FILE = BUILD_DIR / "notes" / "PINTEREST"

API_URL = "https://api.pinterest.com/v5/pins"
SANDBOX_API_URL = "https://api-sandbox.pinterest.com/v5/pins"
SITE_URL = "https://thomasguest.art"
SITE_NAME = "thomasguest.art"

SEPARATOR_RE = re.compile(r"^-{5,}\s*$", re.MULTILINE)
INLINE_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(/images/([^)]+)\)")


def read_config(path: Path) -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


class HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_head = False
        self.meta: Dict[str, str] = {}
        self.title: Optional[str] = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "head":
            self.in_head = True
            return
        if not self.in_head:
            return
        if tag.lower() == "meta":
            attrd = dict(attrs)
            key = attrd.get("property") or attrd.get("name")
            value = attrd.get("content")
            if key and value:
                self.meta[key] = value
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "head":
            self.in_head = False
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            text = data.strip()
            if text:
                self.title = (self.title or "") + text


def parse_head_from_file(path: Path) -> HeadParser:
    raw = path.read_text(encoding="utf-8")
    parser = HeadParser()
    parser.feed(raw)
    return parser


def parse_post_source(path: Path) -> Tuple[Dict[str, str], str]:
    """Parse a source post file in `build/posts/<slug>` returning header dict and body_md."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    header: Dict[str, str] = {}
    separator_index = None
    for index, line in enumerate(lines):
        if SEPARATOR_RE.match(line):
            separator_index = index
            break
        if ":" in line:
            key, value = line.split(":", 1)
            header[key.strip().lower()] = value.strip()
    if separator_index is None:
        raise ValueError(f"Post source '{path}' is missing a header separator")
    body_md = "\n".join(lines[separator_index + 1 :]).strip("\n")
    return header, body_md


def watermarked_url(original: str) -> str:
    # Replace the first occurrence of "/images/" with "/images/watermarked/"
    if "/images/" in original:
        return original.replace("/images/", "/images/watermarked/", 1)
    return original


def choose_board_id(cfg: Dict[str, str], post_type: str, tags: List[str]) -> Optional[str]:
    """Choose a board id from cfg based on post_type and tags.

    Tries a set of candidate keys for each logical board. The `cfg` may contain keys
    like `board_cyanotype`, `board_ceramic`, `board_tetrapak`, `board_linocut` or
    human-readable keys matching the display names.
    """
    t = post_type.lower()
    tags_l = [t.lower() for t in tags]

    def find(keys: List[str]) -> Optional[str]:
        for k in keys:
            if k in cfg:
                return cfg[k]
        return None

    if t == "cyanotype":
        return find(["board_cyanotype", "cyanotype_board", "Cyanotypes and Botanical Prints", "cyanotypes"]) 
    if t == "ceramic":
        return find(["board_ceramic", "ceramic_board", "Handmade ceramics", "ceramics"]) 
    if t == "print":
        if any("tetrapak" in t for t in tags_l):
            return find(["board_tetrapak", "tetrapak_board", "Tetrapak and Intaglio Prints", "tetrapak"]) 
        if any(t in ("woodcut", "linocut") for t in tags_l):
            return find(["board_linocut", "linocut_board", "Linocut and Woodcut relief prints", "linocut", "woodcut"]) 
    return None


def create_pin(payload: dict, access_token: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = Request(API_URL, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req) as resp:
            resp_text = resp.read().decode("utf-8")
            return json.loads(resp_text)
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = "<no body>"
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {body}") from e
    except URLError as e:
        raise RuntimeError(f"Network error: {e}") from e


def main(argv: list[str]) -> int:
    # support optional --sandbox and --dry-run flags
    sandbox = False
    dry_run = False
    args = list(argv[1:])
    if "--sandbox" in args:
        sandbox = True
        args.remove("--sandbox")
    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")

    if len(args) != 1:
        print("Usage: python pin.py [--sandbox] [--dry-run] <path-to-build-post>\nExample: python pin.py --dry-run build/posts/alan")
        return 2

    src = Path(args[0])
    # derive slug and source path under build/posts
    slug = src.stem
    source_path = src if src.is_absolute() and src.exists() else BUILD_DIR / "posts" / slug
    if not source_path.exists():
        print(f"Post source not found: {source_path}")
        return 3

    try:
        cfg = read_config(Path(CONFIG_FILE))
    except FileNotFoundError as e:
        log.exception("Credentials file missing: %s", CONFIG_FILE)
        raise

    # select API endpoint and access token
    if sandbox:
        globals()["API_URL"] = SANDBOX_API_URL
        access_token = cfg.get("access_token_sandbox") or cfg.get("sandbox_access_token") or cfg.get("access_token")
        print("Using sandbox Pinterest API")
    else:
        access_token = cfg.get("access_token")

    if not access_token:
        print("PINTEREST credentials missing `access_token` (or sandbox token when --sandbox) in build/notes/PINTEREST")
        return 5

    try:
        header, body_md = parse_post_source(source_path)
    except Exception:
        log.exception("Failed to parse post source %s", source_path)
        raise

    post_title = header.get("title") or slug
    post_type = header.get("type") or header.get("post_type") or ""
    tags = [t.strip() for t in (header.get("tags") or "").split(",") if t.strip()]
    date = header.get("date") or ""

    # choose board id based on type/tags
    board_id = choose_board_id(cfg, post_type, tags)
    if not board_id:
        # fallback to a generic board_id if provided
        board_id = cfg.get("board_id") or cfg.get("default_board")
        if board_id:
            print("Warning: no specific board mapping found; using fallback board_id from notes file.")
        else:
            print("Unable to select a board_id for this post. Check build/notes/PINTEREST for board mappings.")
            print("Available keys in notes file:", ", ".join(sorted(cfg.keys())))
            return 7

    # construct title/description/link like build.py
    title = f"{post_title} · {SITE_NAME}"
    description = f"{post_title} — {post_type}. Artwork by Thomas Guest."
    link = f"{SITE_URL}/posts/{slug}"

    # collect images: hero is <slug>.jpg; additional images from markdown
    hero = f"{slug}.jpg"
    matches: List[Tuple[str, str]] = INLINE_IMAGE_RE.findall(body_md)
    # matches are list of (alt, filename)
    images: List[Tuple[str, str]] = []
    # ensure hero is first
    images.append((post_title, hero))
    for alt, filename in matches:
        if filename == hero:
            # replace hero alt if provided
            images[0] = (alt or post_title, filename)
        else:
            images.append((alt or post_title, filename))

    if not images:
        print("No images found for post; cannot create pin.")
        return 8

    # build media_source
    if len(images) == 1:
        media_url = f"{SITE_URL}/images/watermarked/{images[0][1]}"
        payload = {
            "board_id": board_id,
            "title": title,
            "alt_text": description,
            "link": link,
            "media_source": {"source_type": "image_url", "url": media_url},
        }
    else:
        items = []
        for alt, filename in images:
            items.append({"source_type": "image_url", "url": f"{SITE_URL}/images/watermarked/{filename}", "alt_text": alt})
        payload = {
            "board_id": board_id,
            "title": title,
            "alt_text": description,
            "link": link,
            "media_source": {"source_type": "multiple_image_urls", "items": items},
        }

    images_list = [p['url'] for p in (payload['media_source'].get('items') or [payload['media_source']])]
    print(f"Creating pin:\n  title: {title}\n  link: {link}\n  images: {images_list}")

    if dry_run:
        print("\nDry run payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    try:
        resp = create_pin(payload, access_token)
    except Exception:
        log.exception("Pin creation failed for post %s", slug)
        raise

    print("Pin created successfully:")
    print(json.dumps(resp, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
