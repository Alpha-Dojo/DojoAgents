"""Traceability gate for the 30 Harness/Session design acceptance conditions."""

from pathlib import Path

ACCEPTANCE_EVIDENCE = {
    1: "tests/harnesses/test_runtime_composer.py",
    2: "tests/harnesses/test_runtime_composer.py",
    3: "tests/test_architecture_boundaries.py",
    4: "tests/harnesses/financial/test_prompts.py",
    5: "tests/harnesses/financial/test_harness_lifecycle.py",
    6: "tests/harnesses/financial/test_tool_inventory.py",
    7: "tests/harnesses/financial/test_policy_order.py",
    8: "tests/test_session_principal_propagation.py",
    9: "tests/harnesses/test_state_isolation.py",
    10: "tests/harnesses/test_extra_sources.py",
    11: "tests/harnesses/test_declarative.py",
    12: "tests/harnesses/test_builder.py",
    13: "tests/harnesses/test_lifecycle.py",
    14: "tests/test_architecture_boundaries.py",
    15: "pyproject.toml",
    16: "tests/sessions/test_contract_fakes.py",
    17: "tests/sessions/test_external_store_contract.py",
    18: "tests/sessions/test_service_objects.py",
    19: "tests/sessions/test_service_scope.py",
    20: "tests/dashboard/test_session_auth_scope.py",
    21: "tests/harnesses/financial/test_state_codec.py",
    22: "tests/sessions/test_strands_compat.py",
    23: "tests/sessions/test_run_failover.py",
    24: "tests/dashboard/test_durable_sse.py",
    25: "tests/sessions/test_object_compensation.py",
    26: "tests/sessions/test_migration.py",
    27: "tests/harnesses/financial/test_presenters.py",
    28: "tests/characterization/test_financial_flow_baseline.py",
    29: "tests/sessions/test_factory.py",
    30: "docs/session-store-adapter.md",
}


def test_all_thirty_acceptance_conditions_have_existing_evidence():
    assert set(ACCEPTANCE_EVIDENCE) == set(range(1, 31))
    missing = [path for path in ACCEPTANCE_EVIDENCE.values() if not Path(path).is_file()]
    assert missing == []


def test_external_sql_gate_is_explicit_and_optional_in_core():
    source = Path("tests/sessions/test_external_store_contract.py").read_text(encoding="utf-8")
    assert "DOJO_TEST_SESSION_STORE_FACTORY" in source
    assert "DOJO_TEST_BLOB_STORE_FACTORY" in source
    metadata = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    assert "sqlalchemy" not in metadata
    assert "psycopg" not in metadata
    assert "pymysql" not in metadata


def test_packaging_includes_harness_task_and_skill_assets():
    metadata = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"harnesses/built_in/financial/tasks/definitions/**/*"' in metadata
    assert '"harnesses/built_in/financial/pipelines/definitions/*.yaml"' in metadata
    assert '"skills/built_in/**/*"' in metadata
