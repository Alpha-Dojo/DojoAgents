from dojoagents.agent.context_length import ContextLengthExceededError, parse_context_length_error


def test_parse_context_length_error_openai_message():
    message = (
        "Error code: 400 - {'error': {'message': \"This model's maximum context length is 1048565 tokens. "
        "However, you requested 3037564 tokens (3037564 in the messages, 0 in the completion). "
        "Please reduce the length of the messages or completion.\", 'type': 'invalid_request_error'}}"
    )
    max_context, requested = parse_context_length_error(message)
    assert max_context == 1048565
    assert requested == 3037564


def test_parse_context_length_error_partial():
    assert parse_context_length_error("maximum context length is 128000") == (128000, None)


def test_context_length_exceeded_error_fields():
    err = ContextLengthExceededError("boom", max_context=100, requested_tokens=200)
    assert err.max_context == 100
    assert err.requested_tokens == 200
