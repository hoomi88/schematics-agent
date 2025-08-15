from __future__ import annotations
from typing import List, Tuple
from pathlib import Path
from tools.openai_client import LLMClient
import re


class ValidatorAgent:
    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        self.llm = LLMClient() if use_llm else None

    def _check_kicad_text_llm(self, sch_path: Path) -> List[str]:
        if not self.llm:
            return []
        try:
            text = sch_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return [f"Cannot read schematic file: {sch_path}"]
        system = (
            "You are a KiCad 9 schematic format validator. Check the text for KiCad 9 S-expression compliance and layout sanity.\n"
            "Verify: top-level (kicad_sch ...), (paper ...), (title_block ...), symbol blocks with (lib_id ...), (at ...), (uuid ...), (property ...).\n"
            "Also verify engineering layout basics: placed symbol instances not overlapping based on their (at x y) position and typical symbol sizes; reasonable spacing; consistent orientation.\n"
            "Return ONLY JSON: {issues: string[]} with specific, actionable messages."
        )
        user = text[:10000]
        reply = self.llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], max_completion_tokens=1500)
        if not reply:
            return []
        import json as _json
        s = reply.find("{")
        e = reply.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                data = _json.loads(reply[s:e+1])
                if isinstance(data, dict) and isinstance(data.get("issues"), list):
                    return [str(x) for x in data["issues"]]
            except Exception:
                return ["LLM returned non-JSON response for KiCad validation."]
        return []

    def _check_missing_embedded_symbols(self, sch_path: Path) -> List[str]:
        try:
            text = sch_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        issues: List[str] = []
        has_lib_symbols = "(lib_symbols" in text
        used_lib_ids = re.findall(r"\(lib_id\s+\"([^\"]+)\"\)", text)
        if used_lib_ids and not has_lib_symbols:
            uniq = sorted(set(used_lib_ids))
            issues.append(
                "No (lib_symbols ...) block present. Embed symbol definitions for: " + ", ".join(uniq[:20])
            )
        return issues

    def _check_symbol_pins_and_graphics(self, sch_path: Path) -> List[str]:
        try:
            text = sch_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        issues: List[str] = []
        if "(lib_symbols" not in text:
            return issues
        pin_count = len(re.findall(r"\(pin\b", text))
        shape_count = len(re.findall(r"\((rectangle|polyline|circle|arc)\b", text))
        if pin_count == 0:
            issues.append("Embedded symbols lack (pin ...) definitions. Add pins with name/number, (at x y), and length.")
        if shape_count == 0:
            issues.append("Embedded symbols lack basic graphics (rectangle/polyline). Add a body rectangle around the symbol.")
        return issues

    def _check_invalid_lib_ids_and_sheet(self, sch_path: Path) -> List[str]:
        try:
            text = sch_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        issues: List[str] = []
        invalids = [m for m in re.findall(r"\(lib_id\s+\"([^\"]+)\"\)", text) if m.strip().lower() in {"device:u", "device:unknown"}]
        if invalids:
            uniq = sorted(set(invalids))
            issues.append("Invalid lib_id(s) found: " + ", ".join(uniq) + ". Replace with valid symbols or embed their definitions.")
        if "(sheet_instances" not in text:
            issues.append("Missing (sheet_instances ...) block. Add minimal KiCad 9 sheet bookkeeping to improve compatibility.")
        if "(kicad_sch" in text and "(version 20250114)" not in text:
            issues.append("Header version is not KiCad 9 (20250114). Use (version 20250114) (generator eeschema).")
        return issues

    def _extract_instances(self, sch_path: Path) -> List[Tuple[str, float, float, float, str, bool]]:
        try:
            text = sch_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        instances: List[Tuple[str, float, float, float, str, bool]] = []
        for m in re.finditer(r"\(property\s+\"Reference\"\s+\"([A-Za-z]+\d+)\"", text):
            ref = m.group(1)
            start = max(0, m.start() - 2000)
            end = min(len(text), m.end() + 2000)
            window = text[start:end]
            at_m = re.search(r"\(at\s+(-?[\d\.]+)\s+(-?[\d\.]+)(?:\s+(-?[\d\.]+))?\)", window)
            lib_m = re.search(r"\(lib_id\s+\"([^\"]+)\"\)", window)
            uuid_m = re.search(r"\(uuid\s+[0-9a-fA-F-]{8,}\)", window)
            if at_m and lib_m:
                try:
                    x = float(at_m.group(1))
                    y = float(at_m.group(2))
                    rot = float(at_m.group(3)) if at_m.group(3) else 0.0
                except Exception:
                    x, y, rot = 0.0, 0.0, 0.0
                lib_id = lib_m.group(1)
                has_uuid = bool(uuid_m)
                instances.append((ref, x, y, rot, lib_id, has_uuid))
        return instances

    def _desired_prefix_for_lib(self, lib_id: str) -> str:
        l = lib_id.lower()
        if "device:r" in l or "resistor" in l:
            return "R"
        if "device:c" in l or "capacitor" in l:
            return "C"
        if "device:l" in l or "inductor" in l:
            return "L"
        if "connector" in l or l.startswith("conn"):
            return "J"
        if "switch" in l or l.startswith("sw") or "button" in l:
            return "S"
        if "device:d" in l or "diode" in l or "led" in l:
            return "D"
        if "device:q" in l or "transistor" in l or "bjt" in l or "mosfet" in l:
            return "Q"
        if "crystal" in l or "xtal" in l or "osc" in l or "resonator" in l:
            return "Y"
        return "U"

    def _check_instance_positions_and_refs(self, sch_path: Path) -> List[str]:
        inst = self._extract_instances(sch_path)
        issues: List[str] = []
        min_spacing = 20.0
        for i in range(len(inst)):
            ref_i, xi, yi, _, _, _ = inst[i]
            for j in range(i + 1, len(inst)):
                ref_j, xj, yj, _, _, _ = inst[j]
                dx = xi - xj
                dy = yi - yj
                if (dx * dx + dy * dy) < (min_spacing * min_spacing):
                    issues.append(f"Placed instances too close: {ref_i} and {ref_j} (increase spacing >= {min_spacing}).")
        for ref, _, _, _, lib_id, has_uuid in inst:
            want_prefix = self._desired_prefix_for_lib(lib_id)
            if not ref.upper().startswith(want_prefix):
                issues.append(f"Reference prefix mismatch for {ref}: expected to start with '{want_prefix}' based on lib_id {lib_id}.")
            if not has_uuid:
                issues.append(f"Placed instance {ref} is missing (uuid ...). Add a UUID to each (symbol ...) instance.")
        return issues

    def validate(self, sch_path: Path) -> List[str]:
        issues: List[str] = []
        issues.extend(self._check_missing_embedded_symbols(sch_path))
        issues.extend(self._check_symbol_pins_and_graphics(sch_path))
        issues.extend(self._check_invalid_lib_ids_and_sheet(sch_path))
        issues.extend(self._check_instance_positions_and_refs(sch_path))
        if self.use_llm:
            issues.extend(self._check_kicad_text_llm(sch_path))
        return issues

