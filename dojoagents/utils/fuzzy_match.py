from __future__ import annotations

import re
from typing import Tuple, List

def fuzzy_find_and_replace(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> Tuple[str, int, str | None, str | None]:
    """
    Finds and replaces text using a chain of matching strategies.
    
    Returns:
        (new_content, match_count, strategy_name, error_message)
    """
    if not old_string:
        return content, 0, None, "old_string cannot be empty"
    if old_string == new_string:
        return content, 0, None, "old_string and new_string are identical"

    strategies = [
        ("exact", _strategy_exact),
        ("line_trimmed", _strategy_line_trimmed),
        ("whitespace_normalized", _strategy_whitespace_normalized),
        ("indentation_flexible", _strategy_indentation_flexible),
    ]

    for strategy_name, strategy_fn in strategies:
        matches = strategy_fn(content, old_string)
        if matches:
            if len(matches) > 1 and not replace_all:
                return content, 0, None, f"Found {len(matches)} matches for old_string. Provide more context to make it unique, or use replace_all=True."
            
            # Apply replacements from back to front to preserve offsets
            new_content = content
            for start, end in sorted(matches, reverse=True):
                new_content = new_content[:start] + new_string + new_content[end:]
            return new_content, len(matches), strategy_name, None

    return content, 0, None, "Could not find a match for old_string in the file"

def _strategy_exact(content: str, pattern: str) -> List[Tuple[int, int]]:
    matches = []
    start = 0
    while True:
        pos = content.find(pattern, start)
        if pos == -1:
            break
        matches.append((pos, pos + len(pattern)))
        start = pos + 1
    return matches

def _calculate_line_positions(content_lines: List[str], start_line: int, end_line: int, content_len: int) -> Tuple[int, int]:
    start_pos = sum(len(line) + 1 for line in content_lines[:start_line])
    end_pos = sum(len(line) + 1 for line in content_lines[:end_line]) - 1
    return start_pos, min(content_len, end_pos)

def _strategy_line_trimmed(content: str, pattern: str) -> List[Tuple[int, int]]:
    pattern_lines = [line.strip() for line in pattern.splitlines()]
    pattern_normalized = "\n".join(pattern_lines)
    
    content_lines = content.splitlines()
    content_normalized_lines = [line.strip() for line in content_lines]
    
    matches = []
    pat_len = len(pattern_lines)
    if pat_len == 0:
        return []
        
    for i in range(len(content_normalized_lines) - pat_len + 1):
        block = "\n".join(content_normalized_lines[i : i + pat_len])
        if block == pattern_normalized:
            start_pos, end_pos = _calculate_line_positions(content_lines, i, i + pat_len, len(content))
            matches.append((start_pos, end_pos))
    return matches

def _strategy_whitespace_normalized(content: str, pattern: str) -> List[Tuple[int, int]]:
    pattern_normalized = re.sub(r"[ \t]+", " ", pattern)
    content_len = len(content)
    pattern_len = len(pattern_normalized)

    def match_positions():
        # KMP keeps search storage proportional to the pattern, not the file.
        prefixes = [0] * pattern_len
        matched = 0
        for index in range(1, pattern_len):
            while matched and pattern_normalized[index] != pattern_normalized[matched]:
                matched = prefixes[matched - 1]
            if pattern_normalized[index] == pattern_normalized[matched]:
                matched += 1
            prefixes[index] = matched
        matched = 0
        index = -1
        in_blanks = False
        if not pattern_len:
            yield 0
        for char in content:
            if char in " \t":
                if in_blanks:
                    continue
                char = " "
                in_blanks = True
            else:
                in_blanks = False
            index += 1
            if not pattern_len:
                yield index + 1
                continue
            while matched and char != pattern_normalized[matched]:
                matched = prefixes[matched - 1]
            if char == pattern_normalized[matched]:
                matched += 1
            if matched == pattern_len:
                yield index - pattern_len + 1
                matched = prefixes[matched - 1]

    def mapped_runs():
        norm_idx = run_start = 0
        blank_mapped = False
        for orig_idx, char in enumerate(content, 1):
            if char in " \t":
                if blank_mapped:
                    continue
                # Spaces map immediately; tabs map at a nonblank boundary.
                if char != " " and (orig_idx == content_len or content[orig_idx] in " \t"):
                    continue
                blank_mapped = True
            else:
                blank_mapped = False
            yield norm_idx, run_start, orig_idx
            norm_idx += 1
            run_start = orig_idx
        if run_start < content_len:
            yield norm_idx, run_start, content_len

    # Match starts and ends advance independently, including overlapping matches.
    start_runs = mapped_runs()
    end_runs = mapped_runs()
    start_run = end_run = None
    original_matches = []
    for pos in match_positions():
        if start_run is None:
            start_run = next(start_runs, None)
        if end_run is None:
            end_run = next(end_runs, None)
        while start_run is not None and start_run[0] < pos:
            start_run = next(start_runs, None)
        orig_start = start_run[1] if start_run is not None else 0

        end_idx = pos + pattern_len - 1
        while end_run is not None and end_run[0] < end_idx:
            end_run = next(end_runs, None)
        if end_run is not None and end_run[0] == end_idx:
            orig_end = end_run[2]
        else:
            orig_end = orig_start + pattern_len

        while orig_end < content_len and content[orig_end] in " \t":
            orig_end += 1
        original_matches.append((orig_start, min(orig_end, content_len)))
    return original_matches

def _strategy_indentation_flexible(content: str, pattern: str) -> List[Tuple[int, int]]:
    pattern_lines = [line.lstrip() for line in pattern.splitlines()]
    pattern_normalized = "\n".join(pattern_lines)
    
    content_lines = content.splitlines()
    content_normalized_lines = [line.lstrip() for line in content_lines]
    
    matches = []
    pat_len = len(pattern_lines)
    if pat_len == 0:
        return []
        
    for i in range(len(content_normalized_lines) - pat_len + 1):
        block = "\n".join(content_normalized_lines[i : i + pat_len])
        if block == pattern_normalized:
            start_pos, end_pos = _calculate_line_positions(content_lines, i, i + pat_len, len(content))
            matches.append((start_pos, end_pos))
    return matches
