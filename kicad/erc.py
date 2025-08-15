from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import re
import tempfile
import json


def run_erc(schematic_path: Path) -> Optional[subprocess.CompletedProcess]:
    exe = shutil.which("kicad-cli") or shutil.which("kicad-sch")
    if not exe:
        return None
    try:
        return subprocess.run(
            [exe, "sch", "erc", str(schematic_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None


def parse_erc_violations(output_text: str) -> int:
    if not output_text:
        return 0
    m = re.search(r"Found\s+(\d+)\s+violations", output_text, flags=re.I)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return 0
    return 0


def run_erc_with_json(schematic_path: Path) -> Tuple[Optional[subprocess.CompletedProcess], Optional[Dict[str, Any]], Optional[str]]:
    exe = shutil.which("kicad-cli") or shutil.which("kicad-sch")
    if not exe:
        return None, None, None
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            tmp_file = tmp.name
        proc = subprocess.run(
            [exe, "sch", "erc", str(schematic_path), "--format", "json", "--report", tmp_file],
            capture_output=True,
            text=True,
            check=False,
        )
        data = None
        try:
            if tmp_file and Path(tmp_file).exists():
                data = json.loads(Path(tmp_file).read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            data = None
        return proc, data, tmp_file
    except Exception:
        return None, None, tmp_file


def summarize_erc_json(data: Dict[str, Any], max_items: int = 10) -> List[str]:
    lines: List[str] = []
    if not data:
        return lines
    violations = data.get("violations") or []
    lines.append(f"ERC JSON violations: {len(violations)}")
    for v in violations[:max_items]:
        sev = v.get("severity", "?")
        msg = v.get("message", "")
        refs = []
        for ref in v.get("references", []) or []:
            designator = ref.get("ref") or ref.get("uuid") or ""
            refs.append(designator)
        where = ",".join([r for r in refs if r])
        lines.append(f"- {sev}: {msg} [{where}]")
    return lines

