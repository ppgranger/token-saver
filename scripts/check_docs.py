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

"""Check the rendered Jekyll site's metadata, local links, and sitemap.

Run after building docs/: python scripts/check_docs.py /path/to/_site
This checks build artifacts locally; it does not submit URLs to a search engine.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from html import parser
from urllib import parse
from xml.etree import ElementTree

SITE_URL = "https://ppgranger.github.io/token-saver/"


class Page(parser.HTMLParser):
    """Collect HTML metadata and link targets for the documentation check.

    Attributes:
        titles: Text collected from each title element in the document head.
        meta: Metadata values grouped by their name or property attribute.
        canonicals: Canonical URL values declared by link elements.
        links: Hyperlinks and linked resources found in the document.
        ids: Element identifiers that can serve as local fragment targets.
        json_ld: Raw contents of JSON-LD script elements.
        lang: Document language, or an empty string when absent.
        h1_count: Number of top-level heading elements.
    """

    def __init__(self, html: str) -> None:
        """Parse an HTML document and collect its checkable page signals.

        Args:
            html: Complete HTML source from a trusted documentation build.
        """
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.canonicals: list[str] = []
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.json_ld: list[str] = []
        self.lang = ""
        self.h1_count = 0
        self._head = False
        self._title = False
        self._json = False
        self.feed(html)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Collect relevant metadata and links from an opening HTML tag."""
        attr = dict(attrs)
        if attr.get("id"):
            self.ids.add(str(attr["id"]))
        if tag == "html":
            self.lang = attr.get("lang") or ""
        elif tag == "head":
            self._head = True
        elif tag == "title" and self._head:
            self._title = True
            self.titles.append("")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "meta":
            for key in ("name", "property"):
                if attr.get(key):
                    self.meta.setdefault(str(attr[key]), []).append(
                        attr.get("content") or ""
                    )
        elif tag == "link" and attr.get("rel") == "canonical":
            self.canonicals.append(attr.get("href") or "")
        if tag in ("a", "link") and attr.get("href"):
            self.links.append(str(attr["href"]))
        if tag in ("script", "img") and attr.get("src"):
            self.links.append(str(attr["src"]))
        if tag == "script" and attr.get("type") == "application/ld+json":
            self._json = True
            self.json_ld.append("")

    def handle_endtag(self, tag: str) -> None:
        """End title, head, or structured-data collection for a closing tag."""
        if tag == "head":
            self._head = False
        elif tag == "title":
            self._title = False
        elif tag == "script":
            self._json = False

    def handle_data(self, data: str) -> None:
        """Append text to the active title or structured-data element."""
        if self._title:
            self.titles[-1] += data
        if self._json:
            self.json_ld[-1] += data


def _json_error(payload: str) -> str | None:
    """Return a JSON parse error message, or None when the payload is valid."""
    try:
        json.loads(payload)
    except json.JSONDecodeError as exc:
        return exc.msg
    return None


def check_site(directory: pathlib.Path, site_url: str = SITE_URL) -> list[str]:
    """Check metadata, local links, and sitemap in a trusted local site build.

    Args:
        directory: Complete Jekyll build directory containing rendered HTML.
        site_url: Published project base URL used for canonical and local links.

    Returns:
        Sorted, unique descriptions of failed checks, or an empty list when all
        public pages pass. The 404 page is excluded from public page checks.

    Raises:
        OSError: A build artifact cannot be read.
        UnicodeDecodeError: A build artifact is not valid UTF-8.
        ValueError: A URL contains an invalid authority or port representation.
    """
    directory = directory.resolve()
    site_url = site_url.rstrip("/") + "/"
    errors: list[str] = []
    pages = {
        path: Page(path.read_text(encoding="utf-8"))
        for path in directory.rglob("*.html")
        if path.name != "404.html"
    }
    if not pages:
        return [f"No HTML pages found in {directory}"]
    seen_titles: set[str] = set()
    seen_descriptions: set[str] = set()
    expected_urls: set[str] = set()
    site = parse.urlsplit(site_url)
    for path, page in pages.items():
        relative = path.relative_to(directory).as_posix()
        expected = parse.urljoin(site_url, relative.removesuffix("index.html"))
        expected_urls.add(expected)
        if len(page.titles) != 1 or not page.titles[0].strip():
            errors.append(f"{relative}: expected one nonempty head title")
        elif page.titles[0] in seen_titles:
            errors.append(f"{relative}: duplicate title")
        else:
            seen_titles.add(page.titles[0])
        descriptions = page.meta.get("description", [])
        if len(descriptions) != 1 or not descriptions[0].strip():
            errors.append(f"{relative}: expected one nonempty description")
        elif descriptions[0] in seen_descriptions:
            errors.append(f"{relative}: duplicate description")
        else:
            seen_descriptions.add(descriptions[0])
        if page.canonicals != [expected]:
            errors.append(f"{relative}: canonical should be {expected}")
        if page.meta.get("og:url") != [expected]:
            errors.append(f"{relative}: og:url should match canonical")
        if not page.lang or page.h1_count != 1:
            errors.append(
                f"{relative}: expected a document language and one h1"
            )
        if any(
            "noindex" in value.lower() for value in page.meta.get("robots", [])
        ):
            errors.append(f"{relative}: public documentation is marked noindex")
        if not page.json_ld:
            errors.append(f"{relative}: missing structured data")
        for payload in page.json_ld:
            if message := _json_error(payload):
                errors.append(f"{relative}: invalid JSON-LD: {message}")
        for link in page.links:
            target = parse.urlsplit(parse.urljoin(expected, link))
            if target.netloc != site.netloc or target.scheme not in (
                "http",
                "https",
            ):
                continue
            if not target.path.startswith(site.path):
                errors.append(
                    f"{relative}: local link escapes project base URL: {link}"
                )
                continue
            local = directory / parse.unquote(
                target.path.removeprefix(site.path)
            )
            if local.is_dir():
                local /= "index.html"
            if not local.is_file():
                errors.append(f"{relative}: broken local link: {link}")
            elif (
                target.fragment
                and local in pages
                and parse.unquote(target.fragment) not in pages[local].ids
            ):
                errors.append(f"{relative}: broken anchor: {link}")
    sitemap = directory / "sitemap.xml"
    if not sitemap.is_file():
        errors.append("Missing sitemap.xml")
    else:
        try:
            root = ElementTree.fromstring(  # noqa: S314
                sitemap.read_text(encoding="utf-8")
            )
            urls = {node.text for node in root.findall("{*}url/{*}loc")}
            if urls != expected_urls:
                errors.append(
                    "sitemap.xml URLs do not match the rendered public pages"
                )
        except ElementTree.ParseError as exc:
            errors.append(f"Invalid sitemap.xml: {exc}")
    if any(path.name == "AGENTS.md" for path in directory.rglob("AGENTS.md")):
        errors.append("Maintainer AGENTS.md instructions were published")
    return sorted(set(errors))


def main() -> int:
    """Run the documentation check and return 0 on success or 1 on failure."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        "directory", type=pathlib.Path, help="Jekyll build output directory"
    )
    argument_parser.add_argument(
        "--site-url", default=SITE_URL, help="Published project URL"
    )
    args = argument_parser.parse_args()
    errors = check_site(args.directory, args.site_url)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "Documentation check passed: "
        "metadata, JSON-LD, local links, and sitemap."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
