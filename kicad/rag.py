from __future__ import annotations
from typing import Dict, List
from core.models import PartSpec
from kicad.library import index_symbols, search_symbols_by_substrings
from tools.chroma_client import ChromaClient
import re


def _list_if_exists(index: dict, lib: str, symbols: List[str]) -> List[str]:
	if lib not in index:
		return []
	return [f"{lib}:{s}" for s in symbols if s in index[lib]]


def _chroma_search(query: str, n: int = 5) -> List[str]:
	try:
		client = ChromaClient()
		results = client.query("kicad_symbols", query, n_results=n)
		import re as _re
		lib_ids: List[str] = []
		for r in results:
			doc: str = r.get("document") or ""
			for m in _re.finditer(r"\(symbol\s+\"([^\"]+)\"", doc):
				sym = m.group(1)
				lib = r.get("metadata", {}).get("lib") or ""
				if lib:
					lib_ids.append(f"{lib}:{sym}")
		seen = set()
		uniq: List[str] = []
		for x in lib_ids:
			if x not in seen:
				seen.add(x)
				uniq.append(x)
		return uniq[:n]
	except Exception:
		return []


def _sanitize_value_for_custom(value: str) -> str:
	base = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())[:48] or "CustomPart"
	return f"Custom:{base}"


def _suggest_from_value(value: str) -> List[str]:
	value_l = value.lower()
	suggestions: List[str] = []
	chroma_hits = _chroma_search(value, n=8)
	suggestions.extend(chroma_hits)
	if "esp32" in value_l:
		for lib, sym in search_symbols_by_substrings(["esp32", "wroom"]):
			suggestions.append(f"{lib}:{sym}")
	if "mcp73831" in value_l:
		for lib, sym in search_symbols_by_substrings(["mcp73831"]):
			suggestions.append(f"{lib}:{sym}")
	if "hih" in value_l or "4030" in value_l:
		for lib, sym in search_symbols_by_substrings(["hih", "4030"]):
			suggestions.append(f"{lib}:{sym}")
	return suggestions


def candidates_for_part(part: PartSpec, max_per_lib: int = 5) -> List[str]:
	idx = index_symbols()
	ptype = (part.type or "").upper()
	ref_id = (part.ref or "").upper()
	value = (part.value or "").upper()

	candidates: List[str] = []

	if ptype == "R" or ref_id.startswith("R"):
		cand = _list_if_exists(idx, "Device", ["R"]) or []
		candidates.extend(cand[:max_per_lib])
	elif ptype == "C" or ref_id.startswith("C"):
		cand = _list_if_exists(idx, "Device", ["C"]) or []
		candidates.extend(cand[:max_per_lib])
	elif ptype in {"CONN", "CONNECTOR"}:
		conn_syms = ["Conn_01x02", "Conn_01x03", "Conn_01x04", "Conn_01x06"]
		cand = _list_if_exists(idx, "Connector_Generic", conn_syms)
		candidates.extend(cand[:max_per_lib])
	elif ptype in {"LED", "D"}:
		cand = _list_if_exists(idx, "Device", ["LED", "D"])
		candidates.extend(cand[:max_per_lib])
	else:
		if part.value:
			suggestions = _suggest_from_value(part.value)
			candidates.extend(suggestions[:max_per_lib])

	# De-dup and cap
	seen = set()
	result: List[str] = []
	for lib_id in candidates:
		low = lib_id.lower()
		if low in {"device:u", "device:unknown"}:
			continue
		if lib_id not in seen:
			seen.add(lib_id)
			result.append(lib_id)
			if len(result) >= max_per_lib:
				break

	# If still empty, propose a custom symbol name to be embedded
	if not result:
		if part.value:
			result = [_sanitize_value_for_custom(part.value)]
		else:
			result = [f"Custom:{ref_id or 'Unknown'}"]

	return result


def candidates_for_parts(parts: List[PartSpec], max_per_lib: int = 5) -> Dict[str, List[str]]:
	return {p.ref: candidates_for_part(p, max_per_lib=max_per_lib) for p in parts}
