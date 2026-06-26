from dojoagents.agent.token_policy import TokenCompressionPolicy


def test_compression_policy_threshold_boundaries():
    policy = TokenCompressionPolicy(threshold_ratio=0.8)
    assert policy.should_compress(52427, 65536, enabled=True) is False
    assert policy.should_compress(52428, 65536, enabled=True) is True
    assert policy.should_compress(8000, 10000, enabled=True) is True
    assert policy.should_compress(7999, 10000, enabled=True) is False
    assert policy.should_compress(8000, 10000, enabled=False) is False
