from __future__ import annotations

from dojoagents.agent.think_scrubber import StreamingThinkScrubber


def test_scrubber_simple_closed_pair():
    scrubber = StreamingThinkScrubber()

    # Closed pair should be immediately stripped
    text = "Hello <think>secret thought</think>World!"
    result = scrubber.feed(text) + scrubber.flush()
    assert result == "Hello World!"


def test_scrubber_streaming_split_tags():
    scrubber = StreamingThinkScrubber()

    # Part 1: tag starts at boundary (beginning of stream)
    r1 = scrubber.feed("<thi")
    assert r1 == ""  # "<thi" is buffered

    # Part 2: tag finishes, content inside
    r2 = scrubber.feed("nk>private logic")
    assert r2 == ""  # inside block, private logic discarded

    # Part 3: tag closes
    r3 = scrubber.feed("</think>World!")
    assert r3 == "World!"

    assert scrubber.flush() == ""


def test_scrubber_orphan_close():
    scrubber = StreamingThinkScrubber()
    # Orphan close tags should be removed along with trailing whitespace
    result = scrubber.feed("Some prose </think> here") + scrubber.flush()
    assert result == "Some prose here"


def test_scrubber_boundary_rule():
    scrubber = StreamingThinkScrubber()

    # Tag in the middle of a line should NOT be treated as block boundary unless it's a closed pair
    # This prevents accidental stripping of discussions about tags.
    r1 = scrubber.feed("We should use <think> in our prompts.")
    assert "We should use <think> in our prompts." in (r1 + scrubber.flush())


def test_scrubber_flush_non_tag():
    scrubber = StreamingThinkScrubber()

    # A trailing potential tag prefix that turns out to be regular text
    r1 = scrubber.feed("Hello <thi")
    assert r1 == "Hello "

    r2 = scrubber.flush()
    assert r2 == "<thi"
