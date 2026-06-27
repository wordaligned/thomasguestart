import importlib.util
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
            medium="Print",
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
        self.assertIn('/media/print', html)
        self.assertIn('Print', html)
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
                medium="Print",
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

    def test_collection_switcher_lists_tags_and_media(self) -> None:
        html = build_script.build_index_switcher(
            [
                build_script.Post(
                    slug="print-example",
                    title="Print Example",
                    medium="Print",
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
                    medium="Ceramic",
                    size="10x10",
                    date="2026",
                    tags=["ceramic"],
                    pinned=None,
                    body_md="",
                    body_html="",
                    source_path=ROOT / "build" / "posts" / "ceramic-example",
                    content_hash="abc",
                ),
            ],
            ["print", "ceramic"],
            current_key="tag:print",
        )

        self.assertIn('/tags/print', html)
        self.assertIn('/media/ceramic', html)
        self.assertIn('aria-current="page"', html)

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
