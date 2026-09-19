# SEO audit — 2026-09-19

This maintainer note is excluded from the published documentation.

## Observed on the live site

The homepage returned HTTP 200 with a correct self-canonical URL, `en-US`
language, and crawlable HTML navigation. Its title was `Home | Token-Saver`,
the footer incorrectly said MIT, and `/token-saver/sitemap.xml` returned 404.
The domain-root `/robots.txt` also returned 404; that does not block crawling.

## Changes in this branch

- Descriptive homepage title and consistent Apache-2.0 licensing.
- Automatic sitemap through the GitHub Pages-supported `jekyll-sitemap` plugin.
- JSON serialization for structured-data strings and consistent absolute URLs.
- All 36 built-in processors have reference pages and links in `llms.txt`.
- Processor index links render as ordinary HTML; Markdown links point to source
  pages so Jekyll resolves the published permalinks.
- Claims distinguish estimated output-token reduction from billing savings,
  local compression from the optional release check, and fixture-tested error
  preservation from guarantees about arbitrary output.
- Competitor descriptions link to current primary sources; unsupported latency
  and blanket compatibility claims were removed.
- Maintainer `AGENTS.md` files are excluded from the published site.

## Verification

The CI documentation job builds with the locked Ruby dependencies and checks
the rendered output. To reproduce from the repository root:

```bash
export BUNDLE_GEMFILE=docs/Gemfile
bundle install
bundle exec jekyll build --source docs --destination docs/_site --trace
python3 scripts/check_docs.py docs/_site
python3 -m pytest tests/test_docs.py tests/test_processor_count_consistency.py -q
```

The artifact check validates unique titles and descriptions, canonical and Open
Graph URLs, JSON-LD syntax, document language, one main heading per page, local
links and anchors, asset existence, sitemap page coverage, and excluded agent
instructions. Source tests ensure new processors receive reference pages.

A local build does not validate Google's indexing, actual search appearance,
Core Web Vitals, or ranking. No deployment or Search Console submission was
performed as part of this audit. After deployment, inspect the sitemap and key
URLs in Search Console using the site owner's account.

The sitemap plugin also emits a project-level `robots.txt`. Crawlers consult
`https://ppgranger.github.io/robots.txt`, not `/token-saver/robots.txt`; changing
that domain-level file requires the account's root Pages site. Submit the
project sitemap directly in Search Console, or reference it from the domain
root when that site is under your control. `llms.txt` is a documentation index,
not a Google indexing or ranking requirement.

## Primary references

- [Google: descriptive titles](https://developers.google.com/search/docs/appearance/title-link)
- [Google: build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google: robots.txt location and default crawling](https://developers.google.com/crawling/docs/robots-txt/create-robots-txt)
- [GitHub Pages: supported dependency versions](https://pages.github.com/versions/)
