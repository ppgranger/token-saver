# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Guard documentation coverage and detect broken rendered SEO contracts."""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

import scripts.check_docs

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def test_llms_catalog_matches_the_published_copy():
    assert (ROOT / "llms.txt").read_text(encoding="utf-8") == (
        DOCS / "llms.txt"
    ).read_text(encoding="utf-8")


def _metadata(path: pathlib.Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: missing front matter"
    front = text.split("---", 2)[1]
    return dict(
        re.findall(
            r"^(title|description|permalink): (.+)$", front, re.MULTILINE
        )
    )


def test_every_builtin_processor_has_a_reference_and_llms_link():
    llms = (DOCS / "llms.txt").read_text(encoding="utf-8")
    for source in (ROOT / "src" / "processors").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        is_processor = any(
            isinstance(node, ast.ClassDef)
            and any(
                isinstance(base, ast.Attribute) and base.attr == "Processor"
                for base in node.bases
            )
            for node in tree.body
        )
        if is_processor:
            page = DOCS / "processors" / f"{source.stem}.md"
            assert page.is_file(), f"Processor reference missing: {source.stem}"
            permalink = _metadata(page)["permalink"]
            assert scripts.check_docs.SITE_URL.rstrip("/") + permalink in llms


def test_public_pages_have_distinct_titles_descriptions_and_permalinks():
    values: dict[str, set[str]] = {
        key: set() for key in ("title", "description", "permalink")
    }
    for page in DOCS.rglob("*.md"):
        if page.name in ("AGENTS.md", "seo-audit.md"):
            continue
        meta = _metadata(page)
        for key, existing in values.items():
            assert meta.get(key), f"{page}: missing {key}"
            assert meta[key] not in existing, f"{page}: duplicate {key}"
            existing.add(meta[key])
        assert meta["permalink"].startswith("/")
        assert meta["permalink"].endswith("/")


def _build_fixture(directory: pathlib.Path) -> None:
    (directory / "index.html").write_text(
        '<html lang="en-US"><head><title>Token-Saver</title>'
        '<meta name="description" content="Local output compression">'
        f'<link rel="canonical" href="{scripts.check_docs.SITE_URL}">'
        f'<meta property="og:url" content="{scripts.check_docs.SITE_URL}">'
        '<script type="application/ld+json">{"@type":"WebSite"}</script>'
        '</head><body><h1 id="start">Token-Saver</h1>'
        '<a href="#start">Start</a></body></html>',
        encoding="utf-8",
    )
    (directory / "sitemap.xml").write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{scripts.check_docs.SITE_URL}</loc></url></urlset>",
        encoding="utf-8",
    )


def test_rendered_checker_accepts_valid_site(tmp_path):
    _build_fixture(tmp_path)
    assert scripts.check_docs.check_site(tmp_path) == []


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('rel="canonical"', 'rel="alternate"', "canonical should be"),
        ('{"@type":"WebSite"}', '{"@type":}', "invalid JSON-LD"),
        ('href="#start"', 'href="#missing"', "broken anchor"),
        ('href="#start"', 'href="missing.md"', "broken local link"),
        ('<html lang="en-US">', "<html>", "document language"),
    ],
)
def test_rendered_checker_rejects_broken_metadata_and_links(
    tmp_path, old, new, message
):
    _build_fixture(tmp_path)
    page = tmp_path / "index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )
    assert any(
        message in error for error in scripts.check_docs.check_site(tmp_path)
    )


def test_rendered_checker_detects_missing_sitemap_and_published_instructions(
    tmp_path,
):
    _build_fixture(tmp_path)
    (tmp_path / "sitemap.xml").unlink()
    instructions = tmp_path / "processors" / "AGENTS.md"
    instructions.parent.mkdir()
    instructions.write_text("Maintainer instructions", encoding="utf-8")
    errors = scripts.check_docs.check_site(tmp_path)
    assert "Missing sitemap.xml" in errors
    assert "Maintainer AGENTS.md instructions were published" in errors
