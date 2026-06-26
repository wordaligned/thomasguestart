#!/usr/bin/env python3
"""Build thomasguest.art static site from posts and images."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Iterable
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import markdown
from PIL import Image

from spellchecker import SpellChecker

BUILD_DIR = Path(__file__).resolve().parent
ROOT = BUILD_DIR.parent
POSTS_DIR = BUILD_DIR / "posts"
IMAGES_DIR = ROOT / "images"
PAGES_DIR = BUILD_DIR / "pages"
STATIC_DIR = ROOT / "static"
STATE_FILE = ROOT / ".build-state.json"

SITE_NAME = "thomasguest.art"
SITE_URL = "https://thomasguest.art"
AUTHOR_NAME = "Thomas Guest"
AUTHOR_EMAIL = "thomas.guest@gmail.com"
INSTAGRAM_URL = "https://www.instagram.com/thosguest"
ETSY_URL = "https://thomasguestart.etsy.com"

HEADER_IMAGE_SOURCE = BUILD_DIR / "images" / "me.jpg"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEPARATOR_RE = re.compile(r"^-{5,}\s*$")
EM_DASH_RE = re.compile(r"(?<![-])--(?![-])")
WORD_RE = re.compile(r"[A-Za-z']+")
INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(/images/([^)]+)\)")
PROSE_IMG_RE = re.compile(r'<img([^>]*?\s)src="/images/([^"]+)"([^>]*)>', re.IGNORECASE)

THUMB_MAX = 420
DETAIL_MAX = 1400
DETAIL_MOBILE_MAX = 900
AVATAR_SIZE = 128
AVATAR_RETINA = 256

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("build")


@dataclass
class Post:
    slug: str
    title: str
    medium: str
    size: str
    date: str
    tags: list[str]
    pinned: int | None
    body_md: str
    body_html: str
    source_path: Path
    content_hash: str


@dataclass
class Page:
    slug: str
    title: str
    menu_title: str | None
    description: str | None
    body_md: str
    body_html: str
    source_path: Path
    content_hash: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(read_text(path))
    return {}


def write_json(path: Path, data: dict) -> None:
    write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_image_source(filename: str) -> Path:
    """Return source image path, bootstrapping from build staging if needed."""
    target = IMAGES_DIR / filename
    if target.exists():
        return target

    staged = BUILD_DIR / "images" / filename
    if staged.exists():
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged, target)
        log.info("Copied staged image %s -> %s", staged, target)
        return target

    raise FileNotFoundError(
        f"Missing image '{filename}': expected {target} (or staged copy at {staged})"
    )


def ensure_source_image(slug: str) -> Path:
    return ensure_image_source(f"{slug}.jpg")


def extract_markdown_images(body_md: str) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for filename in INLINE_IMAGE_RE.findall(body_md):
        if filename not in seen:
            seen.add(filename)
            names.append(filename)
    return names


def enhance_prose_images(body_html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        before, filename, after = match.groups()
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        if stem.endswith("-mobile"):
            return match.group(0)
        mobile = f"{stem}-mobile{suffix}"
        return (
            f'<picture>'
            f'<source media="(max-width: 768px)" srcset="/images/{mobile}">'
            f'<img{before}src="/images/{filename}"{after}>'
            f"</picture>"
        )

    return PROSE_IMG_RE.sub(replace, body_html)


def transform_text(text: str, context: str) -> str:
    updated = text
    if "'" in updated:
        count = updated.count("'")
        updated = updated.replace("'", "\u2019")
        log.info("%s: converted %d straight apostrophe(s) to typographic quotes", context, count)

    def replace_em_dash(match: re.Match[str]) -> str:
        return "\u2014"

    new_text, replacements = EM_DASH_RE.subn(replace_em_dash, updated)
    if replacements:
        log.info("%s: converted %d double hyphen(s) to em dashes", context, replacements)
        updated = new_text

    return updated


def parse_page(path: Path) -> Page:
    slug = path.name
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid page slug '{slug}' (use lowercase letters, digits, hyphens)")

    raw = read_text(path)
    lines = raw.splitlines()
    header: dict[str, str] = {}
    separator_index = None

    for index, line in enumerate(lines):
        if SEPARATOR_RE.match(line):
            separator_index = index
            break
        if ":" in line:
            key, value = line.split(":", 1)
            header[re.sub(r"\s+", "_", key.strip().lower())] = value.strip()

    if separator_index is None:
        raise ValueError(f"Page '{slug}' is missing a header separator (five or more hyphens)")

    title = header.get("title")
    if not title:
        raise ValueError(f"Page '{slug}' is missing a title")

    body_md = "\n".join(lines[separator_index + 1 :]).strip("\n")
    body_md = transform_text(body_md, f"page '{slug}' body")

    body_html = markdown.markdown(
        body_md,
        extensions=["extra", "smarty"],
        output_format="html5",
    )
    body_html = enhance_prose_images(body_html)

    for image_name in extract_markdown_images(body_md):
        ensure_image_source(image_name)

    return Page(
        slug=slug,
        title=title,
        menu_title=header.get("menu_title") or header.get("menu-title"),
        description=header.get("description"),
        body_md=body_md,
        body_html=body_html,
        source_path=path,
        content_hash=content_hash(raw),
    )


def load_pages() -> list[Page]:
    pages: list[Page] = []
    if not PAGES_DIR.exists():
        return pages

    for path in sorted(PAGES_DIR.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if not SLUG_RE.fullmatch(path.name):
            log.debug("Skipping non-page file %s", path.name)
            continue
        pages.append(parse_page(path))
    return pages


def parse_post(path: Path) -> Post:
    slug = path.name
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"Invalid post slug '{slug}' (use lowercase letters, digits, hyphens)")

    raw = read_text(path)
    lines = raw.splitlines()
    header: dict[str, str] = {}
    separator_index = None

    for index, line in enumerate(lines):
        if SEPARATOR_RE.match(line):
            separator_index = index
            break
        if ":" in line:
            key, value = line.split(":", 1)
            header[key.strip().lower()] = value.strip()

    if separator_index is None:
        raise ValueError(f"Post '{slug}' is missing a header separator (five or more hyphens)")

    required = ("title", "medium", "size", "date", "tags")
    missing = [key for key in required if key not in header]
    if missing:
        raise ValueError(f"Post '{slug}' is missing header field(s): {', '.join(missing)}")

    body_md = "\n".join(lines[separator_index + 1 :]).strip("\n")
    body_md = transform_text(body_md, f"post '{slug}' body")

    pinned = None
    if "pinned" in header:
        pinned = int(header["pinned"])

    tags = [tag.strip() for tag in header["tags"].split(",") if tag.strip()]
    if not tags:
        raise ValueError(f"Post '{slug}' must include at least one tag")

    body_html = markdown.markdown(
        body_md,
        extensions=["extra", "smarty"],
        output_format="html5",
    )
    body_html = enhance_prose_images(body_html)

    for image_name in extract_markdown_images(body_md):
        ensure_image_source(image_name)

    return Post(
        slug=slug,
        title=header["title"],
        medium=header["medium"],
        size=header["size"],
        date=header["date"],
        tags=tags,
        pinned=pinned,
        body_md=body_md,
        body_html=body_html,
        source_path=path,
        content_hash=content_hash(raw),
    )


def load_posts() -> list[Post]:
    posts: list[Post] = []
    if not POSTS_DIR.exists():
        return posts

    for path in sorted(POSTS_DIR.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if not SLUG_RE.fullmatch(path.name):
            log.debug("Skipping non-post file %s", path.name)
            continue
        posts.append(parse_post(path))
        ensure_source_image(path.name)
    return posts


def spell_check_post(post: Post, spell: SpellChecker) -> None:
    words = WORD_RE.findall(post.body_md)
    unknown = sorted({word.lower() for word in words if word.lower() not in spell})
    if unknown:
        log.warning(
            "Spell check for new post '%s': possible misspellings: %s",
            post.slug,
            ", ".join(unknown),
        )
    else:
        log.info("Spell check for new post '%s': no issues found", post.slug)


def update_spell_check_state(posts: Iterable[Post]) -> None:
    state = read_json(STATE_FILE)
    known = state.setdefault("posts", {})
    spell = SpellChecker()

    for post in posts:
        previous = known.get(post.slug)
        if previous and previous.get("content_hash") == post.content_hash:
            continue
        spell_check_post(post, spell)
        known[post.slug] = {
            "content_hash": post.content_hash,
            "spell_checked": True,
        }

    write_json(STATE_FILE, state)


def save_jpeg(image: Image.Image, path: Path, *, quality: int = 85) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    rgb.save(path, format="JPEG", quality=quality, optimize=True)


def resize_image(source: Path, destination: Path, max_edge: int, *, quality: int = 85) -> None:
    with Image.open(source) as image:
        copy = image.copy()
        copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        save_jpeg(copy, destination, quality=quality)


def build_avatar() -> None:
    if not HEADER_IMAGE_SOURCE.exists():
        raise FileNotFoundError(f"Header image not found: {HEADER_IMAGE_SOURCE}")

    with Image.open(HEADER_IMAGE_SOURCE) as image:
        for size, name in ((AVATAR_SIZE, "me.jpg"), (AVATAR_RETINA, "me@2x.jpg")):
            copy = image.copy()
            copy.thumbnail((size, size), Image.Resampling.LANCZOS)
            width, height = copy.size
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            cropped = copy.crop((left, top, left + side, top + side))
            save_jpeg(cropped, ROOT / "images" / name, quality=88)


def deploy_image_variants(filename: str) -> None:
    source = ensure_image_source(filename)
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    resize_image(source, ROOT / "images" / filename, DETAIL_MAX)
    resize_image(source, ROOT / "images" / f"{stem}-mobile{suffix}", DETAIL_MOBILE_MAX)


def build_post_images(post: Post) -> None:
    deploy_image_variants(f"{post.slug}.jpg")
    resize_image(
        ensure_source_image(post.slug),
        ROOT / "images" / "thumbnails" / f"{post.slug}.jpg",
        THUMB_MAX,
    )

    for image_name in extract_markdown_images(post.body_md):
        if image_name != f"{post.slug}.jpg":
            deploy_image_variants(image_name)


def build_page_images(page: Page) -> None:
    for image_name in extract_markdown_images(page.body_md):
        deploy_image_variants(image_name)


def site_href(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return path


def canonical_url(path: str) -> str:
    if not path or path == "/":
        return SITE_URL + "/"
    return f"{SITE_URL}/{path.lstrip('/')}"


def format_tag_label(tag: str) -> str:
    return tag.replace("-", " ")


def collect_tags(posts: Iterable[Post]) -> list[str]:
    tags = {tag for post in posts for tag in post.tags}
    return sorted(tags, key=str.lower)


def sort_for_home(posts: Iterable[Post]) -> list[Post]:
    pinned = [post for post in posts if post.pinned is not None]
    unpinned = [post for post in posts if post.pinned is None]
    pinned.sort(key=lambda post: (post.pinned, post.date), reverse=False)
    unpinned.sort(key=lambda post: post.date, reverse=True)
    return pinned + unpinned


def sort_for_index(posts: Iterable[Post]) -> list[Post]:
    return sorted(posts, key=lambda post: post.date, reverse=True)


def nav_items(tags: list[str], current: str | None, pages: Iterable[Page] | None = None) -> str:
    items = [("Home", site_href("/"), "home")]
    for tag in tags:
        label = format_tag_label(tag)
        href = site_href(f"/tags/{quote(tag)}")
        items.append((label, href, f"tag:{tag}"))
    for page in pages or []:
        label = page.menu_title or page.slug
        href = site_href(f"/{page.slug}")
        items.append((label, href, f"page:{page.slug}"))

    parts: list[str] = []
    for label, href, key in items:
        current_attr = ' aria-current="page"' if current == key else ""
        parts.append(
            f'<li class="site-nav__item"><a href="{href}"{current_attr}>{escape(label)}</a></li>'
        )
    return "\n          ".join(parts)


def page_shell(
    *,
    title: str,
    description: str,
    body: str,
    tags: list[str],
    current_nav: str | None,
    canonical_path: str,
    pages: Iterable[Page] | None = None,
) -> str:
    css_href = site_href("/css/style.css")
    js_href = site_href("/js/site.js")
    avatar = site_href("/images/me.jpg")
    avatar_2x = site_href("/images/me@2x.jpg")
    home_href = site_href("/")
    canonical = canonical_url(canonical_path)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <link rel="canonical" href="{escape(canonical)}">
  <link rel="alternate" type="application/rss+xml" title="{escape(SITE_NAME)} feed" href="{escape(site_href('/feed.rss'))}">
  <link rel="stylesheet" href="{css_href}">
  <script src="{js_href}" defer></script>
</head>
<body>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="site-brand" href="{home_href}">
        <img class="site-brand__avatar" src="{avatar}" srcset="{avatar} 1x, {avatar_2x} 2x" width="{AVATAR_SIZE}" height="{AVATAR_SIZE}" alt="Portrait of {escape(AUTHOR_NAME)}">
        <span class="site-brand__name">{escape(SITE_NAME)}</span>
      </a>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
      <nav class="site-nav" id="site-nav" aria-label="Primary">
        <ul class="site-nav__list">
          {nav_items(tags, current_nav, pages)}
        </ul>
      </nav>
    </div>
  </header>
  <main class="site-main">
{body}
  </main>
  <footer class="site-footer">
    <div class="site-footer__inner">
      <div class="site-footer__identity">
        <span class="site-footer__name">{escape(AUTHOR_NAME)}</span>
        <a href="mailto:{escape(AUTHOR_EMAIL)}">{escape(AUTHOR_EMAIL)}</a>
      </div>
      <div>
        <a href="{escape(INSTAGRAM_URL)}" target="_blank" rel="noopener noreferrer" class="instagram-link">
        <svg xmlns="http://w3.org" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect width="20" height="20" x="2" y="2" rx="5" ry="5"/>
        <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/>
        <line x1="17.5" x2="17.51" y1="6.5" y2="6.5"/>
        </svg>
        @thosguest
        </a>
        <a href="{escape(ETSY_URL)}" rel="noopener noreferrer" target="_blank">Etsy</a>
      </div>
    </div>
  </footer>
</body>
</html>
"""


def thumbnail_grid(posts: Iterable[Post]) -> str:
    cards: list[str] = []
    for post in posts:
        href = site_href(f"/posts/{post.slug}")
        thumb = site_href(f"/images/thumbnails/{post.slug}.jpg")
        cards.append(
            f"""    <a class="thumb-grid__link" href="{href}">
      <img class="thumb-grid__image" src="{thumb}" alt="{escape(post.title)}" loading="lazy" width="{THUMB_MAX}" height="{THUMB_MAX}">
    </a>"""
        )
    if not cards:
        return '    <p>No work published yet.</p>'
    return "    <div class=\"thumb-grid\">\n" + "\n".join(cards) + "\n    </div>"


def build_index_page(
    posts: list[Post],
    tags: list[str],
    *,
    home: bool,
    pages: list[Page] | None = None,
) -> str:
    ordered = sort_for_home(posts) if home else sort_for_index(posts)
    title = SITE_NAME if home else "Archive"
    description = "Selected artwork by Thomas Guest." if home else "Artwork archive by Thomas Guest."
    heading = "" if home else '<h1 class="page-title">All work</h1>\n'
    body = f"{heading}{thumbnail_grid(ordered)}"
    return page_shell(
        title=title,
        description=description,
        body=body,
        tags=tags,
        current_nav="home" if home else None,
        canonical_path="/",
        pages=pages or [],
    )


def build_tag_page(tag: str, posts: list[Post], tags: list[str], pages: list[Page] | None = None) -> str:
    matching = sort_for_index(post for post in posts if tag in post.tags)
    label = format_tag_label(tag)
    body = f'    <h1 class="page-title">#{escape(tag)}</h1>\n{thumbnail_grid(matching)}'
    return page_shell(
        title=f"{label} · {SITE_NAME}",
        description=f"Artwork tagged “{label}” by Thomas Guest.",
        body=body,
        tags=tags,
        current_nav=f"tag:{tag}",
        canonical_path=f"tags/{quote(tag)}",
        pages=pages or [],
    )


def build_post_page(post: Post, tags: list[str], pages: list[Page] | None = None) -> str:
    image = site_href(f"/images/{post.slug}.jpg")
    image_mobile = site_href(f"/images/{post.slug}-mobile.jpg")
    tag_links = "\n          ".join(
        f'<li><a href="{site_href(f"/tags/{quote(tag)}")}">{escape(format_tag_label(tag))}</a></li>'
        for tag in post.tags
    )
    body = f"""    <article class="artwork">
      <figure class="artwork__media">
        <picture>
          <source media="(max-width: 768px)" srcset="{image_mobile}">
          <img src="{image}" alt="{escape(post.title)}" width="{DETAIL_MAX}" height="{DETAIL_MAX}">
        </picture>
      </figure>
      <aside class="artwork__aside">
        <h1 class="artwork__title">{escape(post.title)}</h1>
        <dl class="artwork__facts">
          <dt>Medium</dt>
          <dd>{escape(post.medium)}</dd>
          <dt>Size</dt>
          <dd>{escape(post.size)}</dd>
          <dt>Date</dt>
          <dd>{escape(post.date)}</dd>
        </dl>
        <ul class="artwork__tags">
          {tag_links}
        </ul>
      </aside>
      <div class="artwork__body prose">
        {post.body_html}
      </div>
    </article>"""
    return page_shell(
        title=f"{post.title} · {SITE_NAME}",
        description=f"{post.title} — {post.medium}. Artwork by Thomas Guest.",
        body=body,
        tags=tags,
        current_nav=None,
        canonical_path=f"posts/{post.slug}",
        pages=pages or [],
    )


def build_page_page(page: Page, tags: list[str], pages: list[Page]) -> str:
    body = f"""    <article class=\"page\">
      <h1 class=\"page-title\">{escape(page.title)}</h1>
      <div class=\"page-content prose\">
        {page.body_html}
      </div>
    </article>"""
    return page_shell(
        title=f"{page.title} · {SITE_NAME}",
        description=page.description or f"{page.title} by Thomas Guest.",
        body=body,
        tags=tags,
        current_nav=f"page:{page.slug}",
        canonical_path=page.slug,
        pages=pages,
    )


def rss_description_html(post: Post) -> str:
    html = post.body_html
    html = html.replace('src="/images/', f'src="{SITE_URL}/images/')
    html = html.replace('srcset="/images/', f'srcset="{SITE_URL}/images/')
    hero = (
        f'<p><img src="{SITE_URL}/images/{post.slug}.jpg" '
        f'alt="{xml_escape(post.title)}"></p>'
    )
    return hero + html


def build_rss(posts: list[Post]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        f"<title>{xml_escape(SITE_NAME)}</title>",
        f"<link>{xml_escape(SITE_URL)}</link>",
        "<description>Selected artwork by Thomas Guest.</description>",
        "<language>en-gb</language>",
        f"<lastBuildDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>",
    ]

    for post in sort_for_index(posts):
        post_url = f"{SITE_URL}/posts/{post.slug}"
        description = rss_description_html(post)
        lines.extend(
            [
                "<item>",
                f"<title>{xml_escape(post.title)}</title>",
                f"<link>{xml_escape(post_url)}</link>",
                f'<guid isPermaLink="true">{xml_escape(post_url)}</guid>',
                f"<description><![CDATA[{description}]]></description>",
            ]
        )
        if post.tags:
            lines.append(f"<category>{xml_escape(post.tags[0])}</category>")
        lines.append("</item>")

    lines.extend(["</channel>", "</rss>", ""])
    return "\n".join(lines)


def clean_stale_pages(active_slugs: set[str], active_tags: set[str]) -> None:
    stale_flat = ROOT / "about.html"
    if stale_flat.is_file():
        stale_flat.unlink()
        log.info("Removed stale page %s", stale_flat)

    posts_dir = ROOT / "posts"
    if posts_dir.exists():
        for path in posts_dir.iterdir():
            if path.is_file() and path.suffix == ".html":
                path.unlink()
                log.info("Removed stale page %s", path)
            elif path.is_dir() and path.name not in active_slugs:
                shutil.rmtree(path)
                log.info("Removed stale post directory %s", path)

    tags_dir = ROOT / "tags"
    if tags_dir.exists():
        for path in tags_dir.iterdir():
            if path.is_file() and path.suffix == ".html":
                path.unlink()
                log.info("Removed stale page %s", path)
            elif path.is_dir() and path.name not in active_tags:
                shutil.rmtree(path)
                log.info("Removed stale tag directory %s", path)


def main() -> None:
    posts = load_posts()
    tags = collect_tags(posts)
    pages = load_pages()

    update_spell_check_state(posts)
    build_avatar()

    for post in posts:
        build_post_images(post)

    for page in pages:
        build_page_images(page)

    write_text(ROOT / "index.html", build_index_page(posts, tags, home=True, pages=pages))
    write_text(ROOT / "feed.rss", build_rss(posts))

    active_slugs = {post.slug for post in posts}
    active_tags = set(tags)
    clean_stale_pages(active_slugs, active_tags)

    for page in pages:
        write_text(ROOT / f"{page.slug}.html", build_page_page(page, tags, pages))

    for post in posts:
        write_text(ROOT / "posts" / f"{post.slug}.html", build_post_page(post, tags, pages=pages))

    for tag in tags:
        write_text(ROOT / "tags" / f"{tag}.html", build_tag_page(tag, posts, tags, pages=pages))

    log.info("Built %d post(s), %d tag page(s), %d content page(s)", len(posts), len(tags), len(pages))


if __name__ == "__main__":
    main()
