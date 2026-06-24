"""Tests for ScheduledJob.plan field addition."""

import pytest

from dojoagents.cron.jobs import ScheduledJob


class TestScheduledJobPlanField:
    def test_plan_default_false(self):
        job = ScheduledJob(id="j1", name="test", schedule={}, prompt="hello")
        assert job.plan is False

    def test_plan_true(self):
        job = ScheduledJob(id="j1", name="test", schedule={}, prompt="hello", plan=True)
        assert job.plan is True

    def test_to_record_includes_plan(self):
        job = ScheduledJob(id="j1", name="test", schedule={}, prompt="hello", plan=True)
        rec = job.to_record()
        assert rec["plan"] is True

    def test_from_record_with_plan(self):
        rec = {"id": "j1", "name": "test", "schedule": {}, "prompt": "hello", "plan": True}
        job = ScheduledJob.from_record(rec)
        assert job.plan is True

    def test_from_record_without_plan(self):
        rec = {"id": "j1", "name": "test", "schedule": {}, "prompt": "hello"}
        job = ScheduledJob.from_record(rec)
        assert job.plan is False

    def test_to_chat_request_metadata_includes_plan(self):
        job = ScheduledJob(id="j1", name="test", schedule={}, prompt="hello", plan=True)
        req = job.to_chat_request()
        assert req.metadata.get("plan") is True
