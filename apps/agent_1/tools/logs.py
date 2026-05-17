import re


def read_log_file(log_path: str, lines: int = 200) -> str:
    """Read the last N lines from a specific log file path."""
    return _tail(log_path, lines)


def grep_log_file(log_path: str, pattern: str, context_lines: int = 10) -> list[dict]:
    """
    Search a log file for pattern and return each match with surrounding context.
    Returns a list of {line_number, matched_line, context_before, context_after}.
    """
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except FileNotFoundError:
        return [{"error": f"Log file not found: {log_path}"}]
    except PermissionError:
        return [{"error": f"Permission denied: {log_path}"}]
    except Exception as e:
        return [{"error": str(e)}]

    rx = re.compile(pattern, re.IGNORECASE)
    results = []
    for i, line in enumerate(all_lines):
        if rx.search(line):
            start = max(0, i - context_lines)
            end = min(len(all_lines), i + context_lines + 1)
            results.append({
                "line_number": i + 1,
                "matched_line": line.rstrip(),
                "context": "".join(
                    f"  {j+1:6d}: {all_lines[j].rstrip()}"
                    for j in range(start, end)
                ),
            })
    if not results:
        return [{"info": f"No matches for '{pattern}' in {log_path}"}]
    return results


def extract_stack_trace(log_path: str, error_pattern: str, max_trace_lines: int = 40) -> str:
    """
    Find the last occurrence of error_pattern in the log, then capture
    the full stack trace block that follows it (up to max_trace_lines).
    """
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"[ERROR] {e}"

    rx = re.compile(error_pattern, re.IGNORECASE)
    last_match_idx = -1
    for i, line in enumerate(all_lines):
        if rx.search(line):
            last_match_idx = i

    if last_match_idx == -1:
        return f"[INFO] Pattern '{error_pattern}' not found in {log_path}"

    trace_lines = all_lines[last_match_idx: last_match_idx + max_trace_lines]
    return "".join(trace_lines)


def _tail(path: str, lines: int) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        content = "".join(all_lines[-lines:])
        return content if content.strip() else f"(log file is empty: {path})"
    except FileNotFoundError:
        return f"[ERROR] Log file not found: {path}"
    except PermissionError:
        return f"[ERROR] Permission denied: {path}"
    except Exception as e:
        return f"[ERROR] {e}"
