# Frontend Style Guide

The dashboard is a financial analysis and agent operations interface. It should favor scanning, comparison, and repeated workflows.

## Core Rules

- SaaS/CRM/operator-style screens should stay quiet, clear, and scan-friendly.
- Prefer familiar controls such as icon buttons, segmented controls, checkboxes, sliders, menus, and tabs.
- Keep page sections full-width or plainly constrained; do not turn sections into floating cards.
- Use cards only for repeated items, modals, or genuinely framed tools.
- Text must not overflow or overlap on mobile or desktop.
- Fixed-format elements need stable dimensions, such as boards, toolbars, counters, tiles, and chart containers.
- Tables, lists, and charts should prioritize density, alignment, and comparability.

## Implementation Conventions

- Reuse components from `dojoagents/dashboard/web/src/components/` and `components/ui/`.
- API calls belong in `dojoagents/dashboard/web/src/api/`.
- Types belong in `dojoagents/dashboard/web/src/types/`.
- Page-level views belong in `dojoagents/dashboard/web/src/views/`.
- Shared calculations belong in `dojoagents/dashboard/web/src/utils/`.

## Verification

Frontend changes should at least run:

```bash
cd dojoagents/dashboard/web
npm run build
```

For responsive layouts, charts, or canvas work, check desktop and mobile widths for text overflow, control overlap, and visible data layers.
