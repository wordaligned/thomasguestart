import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "build" / "build.py"

spec = importlib.util.spec_from_file_location("build_script", MODULE_PATH)
assert spec and spec.loader
build_script = importlib.util.module_from_spec(spec)
import sys

sys.modules[spec.name] = build_script
spec.loader.exec_module(build_script)


class BuildPagesTests(unittest.TestCase):
    def test_about_page_is_parsed_from_build_pages(self) -> None:
        page = build_script.parse_page(ROOT / "build" / "pages" / "about")

        self.assertEqual(page.slug, "about")
        self.assertEqual(page.title, "About Me")
        self.assertEqual(page.menu_title, "About")
        self.assertIn("Thomas Guest", page.body_html)

    def test_nav_items_include_generated_pages(self) -> None:
        page = build_script.Page(
            slug="about",
            title="About Me",
            menu_title="About",
            description="About Thomas Guest",
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "pages" / "about",
            content_hash="abc",
        )

        html = build_script.nav_items([], "page:about", [page], [build_script.Post(
            slug="example",
            title="Example",
            post_type="Print",
            media=["Linocut"],
            size="10x10",
            date="2026",
            tags=["print"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )])

        self.assertIn('/about', html)
        self.assertIn('about', html)
        self.assertNotIn('About Me', html)

    def test_home_page_navbar_includes_generated_pages(self) -> None:
        page = build_script.Page(
            slug="about",
            title="About Me",
            menu_title="About",
            description="About Thomas Guest",
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "pages" / "about",
            content_hash="abc",
        )

        html = build_script.build_index_page([
            build_script.Post(
                slug="example",
                title="Example",
                post_type="Print",
                media=["Linocut"],
                size="10x10",
                date="2026",
                tags=["print"],
                pinned=None,
                body_md="",
                body_html="",
                source_path=ROOT / "build" / "posts" / "example",
                content_hash="abc",
            )
        ], [], home=True, pages=[page])

        self.assertIn('/about', html)
        self.assertIn('About', html)

    def test_nav_items_include_post_types(self) -> None:
        html = build_script.nav_items([], "home", [], [
            build_script.Post(
                slug="print-example",
                title="Print Example",
                post_type="Print",
                media=["Linocut"],
                size="10x10",
                date="2026",
                tags=["print"],
                pinned=None,
                body_md="",
                body_html="",
                source_path=ROOT / "build" / "posts" / "print-example",
                content_hash="abc",
            ),
            build_script.Post(
                slug="ceramic-example",
                title="Ceramic Example",
                post_type="Ceramic",
                media=["Terracotta"],
                size="10x10",
                date="2026",
                tags=["ceramic"],
                pinned=None,
                body_md="",
                body_html="",
                source_path=ROOT / "build" / "posts" / "ceramic-example",
                content_hash="abc",
            ),
        ])

        self.assertIn('Print', html)
        self.assertIn('Ceramic', html)
        self.assertIn('/tags/print', html)
        self.assertIn('/tags/ceramic', html)

    def test_post_detail_navbar_matches_index_navbar(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="Print",
            media=["Linocut"],
            size="10x10",
            date="2026",
            tags=["print"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        html = build_script.build_post_page(
            post,
            [],
            pages=[],
            posts=[post],
        )

        self.assertIn('Print', html)
        self.assertIn('Linocut', html)

    def test_post_detail_page_has_no_shared_header_switcher(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="Print",
            media=["Linocut"],
            size="10x10",
            date="2026",
            tags=["print"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )
        other = build_script.Post(
            slug="other",
            title="Other",
            post_type="Ceramic",
            media=["Terracotta"],
            size="10x10",
            date="2026",
            tags=["ceramic"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "other",
            content_hash="abc",
        )

        html = build_script.build_post_page(post, [], pages=[], posts=[post, other])

        self.assertNotIn('index-switcher', html)
        self.assertIn('artwork__tags', html)

    def test_parse_post_supports_type_and_media_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "example-post"
            path.write_text(
                "Title: Example\n"
                "Type: Print\n"
                "Media: Linocut, woodcut\n"
                "Size: 10x10\n"
                "Date: 2026\n"
                "Tags: print, woodcut\n"
                "-----\n\n"
                "Body",
                encoding="utf-8",
            )

            post = build_script.parse_post(path)

        self.assertEqual(post.post_type, "Print")
        self.assertEqual(post.media, ["Linocut", "woodcut"])

    def test_source_posts_use_type_and_media_headers(self) -> None:
        post_paths = sorted((ROOT / "build" / "posts").iterdir())
        for path in post_paths:
            if not path.is_file() or path.name.startswith(".") or path.name.endswith("~"):
                continue
            raw = path.read_text(encoding="utf-8")
            self.assertIn("Type:", raw)
            self.assertIn("Media:", raw)
            self.assertNotIn("Medium:", raw)

    def test_switcher_does_not_repeat_identical_labels(self) -> None:
        html = build_script.build_index_switcher(
            [
                build_script.Post(
                    slug="cyanotype-example",
                    title="Cyanotype Example",
                    post_type="Cyanotype",
                    media=["Cyanotype"],
                    size="10x10",
                    date="2026",
                    tags=["cyanotype"],
                    pinned=None,
                    body_md="",
                    body_html="",
                    source_path=ROOT / "build" / "posts" / "cyanotype-example",
                    content_hash="abc",
                )
            ],
            current_tag=None,
        )

        self.assertEqual(html.count('/tags/cyanotype'), 1)

    def test_spaced_values_use_slugified_links(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="life drawing",
            media=["brown paper"],
            size="10x10",
            date="2026",
            tags=["brown paper"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        html = build_script.build_index_switcher([post], current_tag=None)
        self.assertIn('/tags/brown-paper', html)
        self.assertNotIn('/type/life-drawing', html)
        self.assertNotIn('/media/brown-paper', html)

    def test_tag_links_and_filenames_use_slugified_paths(self) -> None:
        self.assertEqual(build_script.tag_slug("life drawing"), "life-drawing")
        self.assertEqual(build_script.tag_page_path("life drawing"), "tags/life-drawing.html")

        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="Print",
            media=["Linocut"],
            size="10x10",
            date="2026",
            tags=["life drawing"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        html = build_script.build_post_page(post, [], pages=[], posts=[post])
        self.assertIn('/tags/life-drawing', html)
        self.assertNotIn('/tags/life%20drawing', html)

    def test_type_values_create_tag_pages(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="life drawing",
            media=["Linocut"],
            size="10x10",
            date="2026",
            tags=["other"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        tag_html = build_script.build_tag_page("life drawing", [post], ["life drawing"], pages=[])
        self.assertIn('Example', tag_html)
        self.assertIn('/posts/example', tag_html)

    def test_collect_tags_includes_types_and_media(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="life drawing",
            media=["brown paper", "pastel"],
            size="10x10",
            date="2026",
            tags=["pose"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        facets = build_script.collect_tags([post])
        self.assertIn("life drawing", facets)
        self.assertIn("brown paper", facets)
        self.assertIn("pastel", facets)

    def test_post_detail_page_includes_type_and_media_buttons(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="life drawing",
            media=["brown paper", "pastel"],
            size="10x10",
            date="2026",
            tags=["pose"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        html = build_script.build_post_page(post, [], pages=[], posts=[post])
        self.assertIn('/tags/life-drawing', html)
        self.assertIn('/tags/brown-paper', html)
        self.assertIn('/tags/pastel', html)

    def test_post_detail_page_deduplicates_facet_buttons(self) -> None:
        post = build_script.Post(
            slug="example",
            title="Example",
            post_type="cyanotype",
            media=["cyanotype"],
            size="10x10",
            date="2026",
            tags=["cyanotype"],
            pinned=None,
            body_md="",
            body_html="",
            source_path=ROOT / "build" / "posts" / "example",
            content_hash="abc",
        )

        html = build_script.build_post_page(post, [], pages=[], posts=[post])
        self.assertEqual(html.split('artwork__tags', 1)[1].count('/tags/cyanotype'), 1)

    def test_page_images_are_processed_like_post_images(self) -> None:
        page = build_script.Page(
            slug="about",
            title="About Me",
            menu_title=None,
            description="About Thomas Guest",
            body_md="![hello](/images/about.jpg)",
            body_html="",
            source_path=ROOT / "build" / "pages" / "about",
            content_hash="abc",
        )

        with patch.object(build_script, "deploy_image_variants") as deploy_mock:
            build_script.build_page_images(page)

        deploy_mock.assert_called_once_with("about.jpg")


if __name__ == "__main__":
    unittest.main()
