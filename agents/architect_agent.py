from __future__ import annotations
from typing import Dict, List
from core.models import CircuitSpec, GeneratedDesign, PlacedPart
from tools.openai_client import LLMClient
import json
from kicad.library import resolve_lib_id
from kicad.rag import candidates_for_parts


DEFAULT_SYMBOL_MAP: Dict[str, str] = {
    "R": "Device:R",
    "C": "Device:C",
    "L": "Device:L",
    "LED": "Device:LED",
    "D": "Device:D",
    "Q": "Device:Q_NPN_BCE",
    "U": "Device:U",
    "MCU": "Device:U",
    "Conn": "Connector_Generic:Conn_01x04",
}


class ArchitectAgent:
    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        self.llm = LLMClient() if use_llm else None

    def _choose_symbol(self, part_type: str, fallback_symbol: str | None, value: str | None = None) -> str:
        if fallback_symbol:
            lib_id = resolve_lib_id(fallback_symbol, part_type, value)
            return lib_id
        guess = DEFAULT_SYMBOL_MAP.get(part_type, "Device:U")
        lib, _, sym = guess.partition(":")
        resolved = resolve_lib_id(sym or None, part_type, value)
        return resolved

    def _grid_position(self, index: int) -> tuple[int, int]:
        cols = 6
        spacing_x = 30
        spacing_y = 25
        margin_x = 50
        margin_y = 50
        x = margin_x + (index % cols) * spacing_x
        y = margin_y + (index // cols) * spacing_y
        return x, y

    def _extract_json(self, text: str) -> dict | None:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                return None
        return None

    def _apply_positions_and_symbols_from_json(self, design: GeneratedDesign, data: dict, allowed_by_ref: Dict[str, List[str]]) -> GeneratedDesign:
        by_ref = {p["ref"]: p for p in data.get("parts", []) if isinstance(p, dict) and "ref" in p}
        updated = design.model_copy(deep=True)
        for p in updated.parts:
            entry = by_ref.get(p.ref)
            if entry:
                # lib_id selection (enforced against allowed list)
                sel = entry.get("lib_id") or entry.get("symbol")
                allowed = allowed_by_ref.get(p.ref, [])
                if allowed:
                    if sel in allowed:
                        p.symbol = sel
                    else:
                        p.symbol = allowed[0]
                elif isinstance(sel, str):
                    p.symbol = sel
                # position / rotation
                pos = entry.get("position") or entry.get("pos")
                if isinstance(pos, list) and len(pos) == 2:
                    x, y = int(pos[0]), int(pos[1])
                    p.position = (x, y)
                    bx, by, bw, bh = p.bbox
                    if bw == 0 or bh == 0:
                        bw, bh = 18, 10
                    p.bbox = (x - bw // 2, y - bh // 2, bw, bh)
                rot = entry.get("rotation") or entry.get("rot")
                if isinstance(rot, int):
                    p.rotation = rot
        nets = data.get("nets")
        if isinstance(nets, list):
            for n in nets:
                if isinstance(n, str) and n not in updated.nets:
                    updated.nets.append(n)
        return updated

    def _base_design(self, circuit: CircuitSpec) -> GeneratedDesign:
        placed_parts: List[PlacedPart] = []
        for idx, part in enumerate(circuit.parts):
            position = part.position or self._grid_position(idx)
            symbol = self._choose_symbol(part.type, part.symbol, part.value)
            bbox_w, bbox_h = 18, 10
            bbox = (position[0] - bbox_w // 2, position[1] - bbox_h // 2, bbox_w, bbox_h)
            placed_parts.append(
                PlacedPart(
                    ref=part.ref,
                    symbol=symbol,
                    value=part.value,
                    position=position,
                    rotation=part.rotation or 0,
                    pins=part.pins,
                    bbox=bbox,
                )
            )
        nets = [n.name for n in circuit.nets]
        for p in placed_parts:
            for net in p.pins.values():
                if net and net not in nets:
                    nets.append(net)
        return GeneratedDesign(title=circuit.title or "Untitled", parts=placed_parts, nets=nets)

    def produce_design(self, circuit: CircuitSpec) -> GeneratedDesign:
        base = self._base_design(circuit)
        if not self.use_llm or not self.llm:
            return base

        # RAG: allowed lib_ids per part
        allowed = candidates_for_parts(circuit.parts, max_per_lib=5)

        try:
            prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are an EDA assistant. Choose a valid KiCad 9 symbol from the allowed list for each part and improve placement.\n"
                        "Return ONLY JSON with key 'parts': array of objects {ref, lib_id, position:[x,y], rotation?}.\n"
                        "Rules: lib_id MUST be one of the allowed candidates for that ref. Do not invent symbols."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "title": base.title,
                            "parts": [
                                {
                                    "ref": p.ref,
                                    "current_lib_id": p.symbol,
                                    "value": p.value,
                                    "position": list(p.position),
                                    "rotation": p.rotation,
                                    "allowed": allowed.get(p.ref, []),
                                }
                                for p in base.parts
                            ],
                        }
                    ),
                },
            ]
            reply = self.llm.chat(prompt, temperature=0.1, max_tokens=900)
            data = self._extract_json(reply)
            if data:
                return self._apply_positions_and_symbols_from_json(base, data, allowed)
        except Exception:
            pass

        return base

    def revise_design(self, design: GeneratedDesign, issues: List[str]) -> GeneratedDesign:
        updated = design.model_copy(deep=True)
        if self.use_llm and self.llm:
            # Build a minimal pseudo CircuitSpec-like for candidates
            dummy_parts = [
                # Using ref/type/value from current placed parts best-effort
                # Type is not stored on PlacedPart; infer from symbol prefix or fallback
                # We pass an empty type so RAG uses ref heuristic
                type("PartSpec", (), {"ref": p.ref, "type": "", "value": p.value})
                for p in updated.parts
            ]
            allowed = candidates_for_parts(dummy_parts, max_per_lib=5)
            try:
                prompt = [
                    {
                        "role": "system",
                        "content": (
                            "You are an EDA assistant. Fix reported issues by adjusting positions and selecting ONLY allowed KiCad symbols.\n"
                            "Return ONLY JSON: {parts:[{ref, lib_id, position:[x,y], rotation?}], nets?:string[]}."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "issues": issues,
                                "current": {
                                    "title": updated.title,
                                    "parts": [
                                        {
                                            "ref": p.ref,
                                            "current_lib_id": p.symbol,
                                            "value": p.value,
                                            "position": list(p.position),
                                            "rotation": p.rotation,
                                            "allowed": allowed.get(p.ref, []),
                                        }
                                        for p in updated.parts
                                    ],
                                    "nets": updated.nets,
                                },
                            }
                        ),
                    },
                ]
                reply = self.llm.chat(prompt, temperature=0.1, max_tokens=900)
                data = self._extract_json(reply)
                if data:
                    return self._apply_positions_and_symbols_from_json(updated, data, allowed)
            except Exception:
                pass

        # Heuristic fallback if no LLM or bad reply
        shift_x = 10
        shift_y = 8
        any_overlap = any("overlap" in i.lower() for i in issues)
        if any_overlap:
            for idx, part in enumerate(updated.parts):
                x, y = part.position
                nx, ny = x + (idx % 3) * shift_x, y + (idx % 3) * shift_y
                part.position = (nx, ny)
                bx, by, bw, bh = part.bbox
                part.bbox = (nx - bw // 2, ny - bh // 2, bw, bh)

        for iss in issues:
            if "unknown net" in iss.lower():
                start = iss.find("'")
                end = iss.rfind("'")
                if 0 <= start < end:
                    net = iss[start + 1 : end]
                    if net and net not in updated.nets:
                        updated.nets.append(net)

        return updated
