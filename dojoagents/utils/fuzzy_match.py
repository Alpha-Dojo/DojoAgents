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
    def normalize(s: str) -> str:
        return re.sub(r"[ \t]+", " ", s)

    pattern_normalized = normalize(pattern)
    content_normalized = normalize(content)
    
    norm_matches = []
    start = 0
    while True:
        pos = content_normalized.find(pattern_normalized, start)
        if pos == -1:
            break
        norm_matches.append((pos, pos + len(pattern_normalized)))
        start = pos + 1
        
    if not norm_matches:
        return []
        
    orig_to_norm = []
    orig_idx = 0
    norm_idx = 0
    while orig_idx < len(content) and norm_idx < len(content_normalized):
        if content[orig_idx] == content_normalized[norm_idx]:
            orig_to_norm.append(norm_idx)
            orig_idx += 1
            norm_idx += 1
        elif content[orig_idx] in " \t" and content_normalized[norm_idx] == " ":
            orig_to_norm.append(norm_idx)
            orig_idx += 1
            if orig_idx < len(content) and content[orig_idx] not in " \t":
                norm_idx += 1
        elif content[orig_idx] in " \t":
            orig_to_norm.append(norm_idx)
            orig_idx += 1
        else:
            orig_to_norm.append(norm_idx)
            orig_idx += 1
            
    while orig_idx < len(content):
        orig_to_norm.append(len(content_normalized))
        orig_idx += 1
        
    norm_to_orig_start = {}
    norm_to_orig_end = {}
    for orig_pos, norm_pos in enumerate(orig_to_norm):
        if norm_pos not in norm_to_orig_start:
            norm_to_orig_start[norm_pos] = orig_pos
        norm_to_orig_end[norm_pos] = orig_pos
        
    original_matches = []
    for norm_start, norm_end in norm_matches:
        if norm_start in norm_to_orig_start:
            orig_start = norm_to_orig_start[norm_start]
        else:
            orig_start = min((i for i, n in enumerate(orig_to_norm) if n >= norm_start), default=0)
            
        if (norm_end - 1) in norm_to_orig_end:
            orig_end = norm_to_orig_end[norm_end - 1] + 1
        else:
            orig_end = orig_start + (norm_end - norm_start)
            
        while orig_end < len(content) and content[orig_end] in " \t":
            orig_end += 1
        original_matches.append((orig_start, min(orig_end, len(content))))
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
