import re
import subprocess
from pathlib import Path

_MAX_FILE_CHARS = 10_000


def _run_git(args: list[str], cwd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or "Unknown git error"
        return True, result.stdout
    except subprocess.TimeoutExpired:
        return False, "Git command timed out after 30 s"
    except FileNotFoundError:
        return False, "git not found in PATH"
    except Exception as e:
        return False, str(e)


def list_repo_files(repo_path: str, directory: str = "", branch: str = "HEAD") -> dict:
    args = ["ls-tree", "-r", "--name-only", branch]
    if directory:
        args.append(directory)
    ok, output = _run_git(args, repo_path)
    if not ok:
        return {"error": output, "files": []}
    files = [f for f in output.strip().split("\n") if f]
    return {"files": files, "count": len(files)}


def read_file_from_git(repo_path: str, file_path: str, branch: str = "HEAD") -> str:
    ok, output = _run_git(["show", f"{branch}:{file_path}"], repo_path)
    if not ok:
        return f"[ERROR] {output}"
    if len(output) > _MAX_FILE_CHARS:
        return output[:_MAX_FILE_CHARS] + f"\n\n[TRUNCATED — showing first {_MAX_FILE_CHARS:,} of {len(output):,} chars]"
    return output


def get_git_log(repo_path: str, file_path: str = "", n: int = 15) -> str:
    args = ["log", "--oneline", f"-{n}"]
    if file_path:
        args += ["--", file_path]
    ok, output = _run_git(args, repo_path)
    return output if ok else f"[ERROR] {output}"


def read_file_lines(repo_path: str, file_path: str, start_line: int, end_line: int) -> str:
    """Read a specific line range from a repo file — used to pinpoint stack trace locations."""
    full_path = Path(repo_path) / file_path
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        total = len(all_lines)
        s = max(0, start_line - 1)
        e = min(total, end_line)
        selected = all_lines[s:e]
        numbered = "".join(f"{s+i+1:5d}: {line}" for i, line in enumerate(selected))
        return f"# {file_path}  (lines {s+1}–{e} of {total})\n{numbered}"
    except FileNotFoundError:
        return f"[ERROR] File not found: {full_path}"
    except Exception as ex:
        return f"[ERROR] {ex}"


def grep_codebase(
    repo_path: str,
    pattern: str,
    extensions: list[str] | None = None,
    max_results: int = 30,
) -> list[dict]:
    """Search the codebase for a regex pattern — used to trace symbols from stack traces to source."""
    rx = re.compile(pattern, re.IGNORECASE)
    root = Path(repo_path)
    ext_set = {e.lstrip(".").lower() for e in (extensions or [])}
    results: list[dict] = []

    for fpath in root.rglob("*"):
        if not fpath.is_file():
            continue
        if ext_set and fpath.suffix.lstrip(".").lower() not in ext_set:
            continue
        if fpath.name.startswith(".") or fpath.suffix in {".pyc", ".class", ".o", ".so"}:
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if rx.search(line):
                        results.append({
                            "file": str(fpath.relative_to(root)),
                            "line": lineno,
                            "content": line.rstrip(),
                        })
                        if len(results) >= max_results:
                            return results
        except Exception:
            continue

    return results if results else [{"info": f"No matches for '{pattern}' in {repo_path}"}]


def parse_stack_trace_locations(stack_trace: str) -> list[dict]:
    """Extract file:line references from Python, Java, Go, and generic stack traces."""
    locations: list[dict] = []
    seen: set[tuple] = set()

    patterns = [
        re.compile(r'File ["\']([^"\']+\.py)["\'],\s*line\s*(\d+)'),
        re.compile(r'at\s+[\w.$]+\(([\w./]+\.java):(\d+)\)'),
        re.compile(r'([\w./]+\.go):(\d+)'),
        re.compile(r'([\w./\\-]+\.\w+):(\d+)'),
    ]

    for rx in patterns:
        for m in rx.finditer(stack_trace):
            key = (m.group(1), m.group(2))
            if key not in seen:
                seen.add(key)
                locations.append({"file": m.group(1), "line": int(m.group(2))})

    return locations
