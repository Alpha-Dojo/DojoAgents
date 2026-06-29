# Precompute Sector Data

Sector precomputation reduces real-time K-line load for dashboard sector queries. Generated data is loaded by `SectorPrecomputedStore`.

## Command

```bash
dojoagents precompute-sector
```

Options:

| Option | Default | Description |
| --- | --- | --- |
| `--data-root` | Dashboard data root | Output root |
| `--start-date` | `2025-01-01` | First trade date |
| `--upload` | `false` | Upload published snapshot |

## Outputs

- `constituents.parquet`
- `sector_daily.parquet`
- `ticker_daily.parquet`

