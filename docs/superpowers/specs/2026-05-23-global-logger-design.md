# Global Logger Design

## Goal

Add a DojoAgents global logger that is configured from `~/.dojo/agents.yaml` and uses a default format containing process, thread, timestamp, log level, logger name, source file, line number, and message.

## Configuration

The existing `AgentsConfig` model will gain a `logging` section:

```yaml
logging:
  level: INFO
  format: "%(asctime)s %(process)d %(thread)d %(levelname)s %(name)s %(filename)s:%(lineno)d - %(message)s"
  date_format: "%Y-%m-%d %H:%M:%S"
```

All fields are optional in user YAML. Missing values use defaults.

## Public API

Create `dojoagents/logging.py` with:

- `DEFAULT_LOG_FORMAT`
- `DEFAULT_DATE_FORMAT`
- `configure_logging(config: LoggingConfig | None = None) -> logging.Logger`
- `get_logger(name: str | None = None) -> logging.Logger`

`get_logger()` returns the top-level `dojoagents` logger. `get_logger("agent.loop")` returns `dojoagents.agent.loop`.

## Behavior

The logger uses Python's standard library `logging` module and introduces no new dependency.

`configure_logging` configures only the `dojoagents` logger, not the root logger. It attaches a stream handler if one has not already been created by DojoAgents, sets the configured formatter, and updates the logger level. Repeated calls must not append duplicate handlers.

The default log level is `INFO`. The default format must include:

- timestamp via `%(asctime)s`
- process id via `%(process)d`
- thread id via `%(thread)d`
- level via `%(levelname)s`
- logger name via `%(name)s`
- source file via `%(filename)s`
- line number via `%(lineno)d`
- message via `%(message)s`

## Integration

`dojoagents.config.models` adds a frozen `LoggingConfig` dataclass and includes it in `AgentsConfig`.

`dojoagents.config.loader._to_config` reads the `logging` mapping from merged YAML and creates `LoggingConfig`. The existing default merge behavior means a user only needs to provide fields they want to override.

Startup code can later call `configure_logging(store.snapshot().logging)` once at process entry points. This initial feature only provides the global logger and configuration contract.

## Error Handling

Invalid log levels should raise `ValueError` from `configure_logging` with a clear message. Invalid logging format strings should fail through standard `logging.Formatter` behavior when formatting a record; the implementation will not create a custom format language.

## Tests

Add coverage in `tests/test_core_contracts.py` or a focused logger test file for:

- config defaults include the default logging format and level
- YAML overrides `logging.level`, `logging.format`, and `logging.date_format`
- `configure_logging` formats a record with process, thread, file, line, and message fields
- repeated `configure_logging` calls do not duplicate output
- invalid log level raises `ValueError`
