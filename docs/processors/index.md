---
title: Processors
description: One page per tool family, documenting exactly what each processor keeps, what it drops, and which config knobs are available.
permalink: /processors/
nav_order: 2
has_toc: false
---

# Processors

Token-Saver ships 36 specialized processors, each one built around the output
shape of a single tool family. A processor knows which lines carry signal —
errors, diffs, stack traces, changed resources — and which are ceremony, so it
can drop the ceremony without the guesswork a generic truncator would need.

Every page below documents the same three things: what the processor matches,
what it keeps, and what it drops. The full list is also in the sidebar.

## All processors

{% assign processor_pages = site.pages | where: "parent", "Processors" | sort_natural: "title" %}
<ul>
{% for processor_page in processor_pages %}
  <li><a href="{{ processor_page.url | relative_url }}">{{ processor_page.title | escape }}</a> — {{ processor_page.description | escape }}</li>
{% endfor %}
</ul>

[Compare compression approaches](../comparison.md) or check the
[measured benchmarks](../benchmarks.md) before choosing thresholds.
