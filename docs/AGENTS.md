# Documentation site

- Python snippets follow the root Google Python style policy, including absolute
  module imports, 80-column code, and Google-style contract documentation where
  useful. Style documentation must explain tooling limits and justified local
  exceptions; preserve attribution for copied licensed material.
- The site is Jekyll with the pinned Just the Docs remote theme. Preserve the
  repository's `baseurl`; use Jekyll URL filters for assets/links in templates
  and verify internal links under `/token-saver/`, not only at the domain root.
- Pages need useful front matter: unique title, specific description, stable
  permalink, and the correct navigation parent/order where applicable. Keep
  one clear page heading and descriptive link text; code blocks need a language
  when known. Instruction files such as this one are not public content pages.
- Keep metadata, canonical URLs, sitemap/robots behavior, social previews, and
  structured data consistent. Reuse the theme/SEO plugin output rather than
  producing duplicate tags. Structured data must describe visible, real content.
- Document actual CLI flags, defaults, supported tools, and measured results.
  Configuration, processor counts, release versions, licenses, and comparison
  claims must agree with the repository's authoritative sources and tests.
- Explain that savings are estimated from characters; benchmark claims require
  a reproducible scenario. Avoid universal error-preservation, information-loss,
  billing-savings, or speed claims beyond what the implementation demonstrates.
- A processor page should include supported commands, a representative input
  and output, preserved information, deliberate omissions, and relevant limits.
  Link it from the processor index and keep discovery/LLM-readable content in
  sync when adding or changing public pages.
- Keep the GitHub Pages build compatible with the configured build workflow;
  adding a plugin or changing the theme needs build verification. Do not assume
  Markdown source checks establish that the generated page renders correctly.

Run relevant content-consistency tests after doc/config edits. For template,
navigation, or SEO changes, inspect generated HTML and key rendered pages when
the build environment is available; report any build limitation accurately.
