from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Dict, Set, Iterable, Optional, List, Tuple


SYMBOL_FILE_EXT = ".kicad_sym"


def _candidate_symbol_dirs() -> Iterable[Path]:
    env_dir = os.getenv("KICAD_SYMBOLS_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            yield p
    # Common Windows install
    for base in (
        os.getenv("ProgramFiles", r"C:\Program Files"),
        os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        if not base:
            continue
        for ver in ("9.0", "8.0", "7.0"):
            p = Path(base) / "KiCad" / ver / "share" / "kicad" / "symbols"
            if p.exists():
                yield p
    # Fallback common Unix paths
    for p in (
        Path("/usr/share/kicad/symbols"),
        Path("/usr/local/share/kicad/symbols"),
    ):
        if p.exists():
            yield p


def _list_symbol_files(root: Path) -> Iterable[Path]:
    for path in root.rglob(f"*{SYMBOL_FILE_EXT}"):
        if path.is_file():
            yield path


_symbol_cache: Optional[Dict[str, Set[str]]] = None


def index_symbols() -> Dict[str, Set[str]]:
    global _symbol_cache
    if _symbol_cache is not None:
        return _symbol_cache

    index: Dict[str, Set[str]] = {}
    for sym_dir in _candidate_symbol_dirs():
        for fpath in _list_symbol_files(sym_dir):
            lib_nickname = fpath.stem  # e.g., Device.kicad_sym -> Device
            symbols = index.setdefault(lib_nickname, set())
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # Extract symbol names: lines like (symbol "R" ...)
            for m in re.finditer(r"\(symbol\s+\"([^\"]+)\"", text):
                symbols.add(m.group(1))
    _symbol_cache = index
    return index


def resolve_lib_id(preferred: str | None, part_type: str, value: str | None = None) -> str:
    # If caller provided a full lib_id already, keep it
    if preferred and ":" in preferred:
        return preferred

    index = index_symbols()

    # Heuristic mappings
    candidates: list[tuple[str, str]] = []
    t = part_type.upper()
    if t == "R":
        candidates.append(("Device", "R"))
    elif t == "C":
        candidates.append(("Device", "C"))
    elif t in {"L"}:
        candidates.append(("Device", "L"))
    elif t in {"LED"}:
        candidates.append(("Device", "LED"))
    elif t in {"CONN", "CONNECTOR"}:
        # Try a few common connector symbols
        for sym in ("Conn_01x02", "Conn_01x03", "Conn_01x04"):
            candidates.append(("Connector_Generic", sym))
    elif t in {"MCU", "U"}:
        # Generic IC placeholder if specific one not found
        candidates.append(("Device", "U"))

    # Try value-based exact match if value looks like a known symbol
    if value:
        for lib in ("Device", "Connector_Generic"):
            candidates.append((lib, value))

    # Resolve against index
    for lib, sym in candidates:
        if lib in index and sym in index[lib]:
            return f"{lib}:{sym}"

    # Fallback to provided preferred as symbol name within Device lib
    if preferred:
        lib = "Device"
        sym = preferred
        if lib in index and sym in index[lib]:
            return f"{lib}:{sym}"

    # Last resort
    return "Device:Unknown"


def search_symbols_by_substrings(substrings: List[str]) -> List[Tuple[str, str]]:
    idx = index_symbols()
    if not substrings:
        return []
    lowered = [s.lower() for s in substrings if s]
    results: List[Tuple[str, str]] = []
    for lib, syms in idx.items():
        for name in syms:
            nm = name.lower()
            if all(tok in nm for tok in lowered):
                results.append((lib, name))
    return results
