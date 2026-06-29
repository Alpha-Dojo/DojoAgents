# Migration Notes

> Status: migration index  
> Last reviewed: 2026-06-29

Migration source notes are kept under `docs/plans/`. Legacy `docs/hermes/` materials have been removed from the active docs tree.

## Bilingual Site Reflection

1. The formal site is isolated under `docs/site/`.
2. Chinese and English pages use matching paths for language switching.
3. Legacy docs remain in place but are not scanned as the primary MkDocs site.
4. English pages are concise first-pass versions and can be expanded later.
5. New i18n dependencies must stay synchronized with `uv.lock`.
