from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from tools.openai_client import LLMClient


class GptSchematicWriter:
    def __init__(self, model: Optional[str] = None):
        self.llm = LLMClient(model=model)
        self._history: List[dict] = []  # capped to last 10 messages
        self._iter_counter: int = 0
        self._debug_dir: Optional[Path] = None

    def _add_history(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        if len(self._history) > 10:
            self._history = self._history[-10:]

    def _build_prompt(
        self,
        spec_json_text: str,
        allowed_by_ref: Dict[str, List[str]],
        prev_text: Optional[str],
        issues: Optional[List[str]],
        reference_text: Optional[str],
    ):
        system = (
            "You are a KiCad 9 schematic generator. Produce a valid KiCad 9 S-expression schematic file strictly from the given LLD JSON.\n"
            "Constraints:\n"
            "- Output ONLY the schematic text starting with (kicad_sch ...). No prose, no code fences.\n"
            "- Use top-level: (kicad_sch (version 20250114) (generator eeschema) ...).\n"
            "- Include (paper \"A4\") and (title_block (title \"<title>\")).\n"
            "- Library symbols live under (lib_symbols ...). Their names are generic prefixes WITHOUT numbers (e.g., R, C, L, D, Q, Y, U, J, S, or Custom:<name>), and include pins and an outline (rectangle/polyline).\n"
            "- Placed instances live directly under (kicad_sch) as (symbol ...). For each ref in 'allowed' (input order), CREATE ONE (symbol ...) with: (lib_id <Library:Symbol> chosen ONLY from that ref's allowed list), (at ...), (uuid <GUID>), and sibling properties including (property \"Reference\" \"<ref>\"). Every placed instance MUST include a UUID.\n"
            "- Reference prefix rules (by lib_id category): R (resistors), C (capacitors), L (inductors), J (connectors), S (switches/buttons), D (diodes/LEDs), Q (transistors/MOSFETs), Y (crystals/oscillators), U (ICs/others). Normalize refs to match and number sequentially per prefix based on input order.\n"
            "- If no suitable real symbol exists, embed a custom symbol in (lib_symbols ...) and reference it via a Custom:<name> lib_id (no numbers in the symbol name).\n"
            "- Add minimal (sheet_instances ...) bookkeeping expected by KiCad 9.\n"
            "- STRICTLY follow the provided template schema if given: replicate header, section order, nesting, and formatting. Do not change section names or hierarchy.\n"
            "- Apply engineering drawing practices: readable spacing, avoid overlaps, consistent orientation.\n"
        )
        try:
            raw = json.loads(spec_json_text)
        except Exception:
            raw = {"raw": spec_json_text[:4000]}
        payload = {
            "lld_json": raw,
            "allowed": allowed_by_ref,
            "refs": list(allowed_by_ref.keys()),
        }
        if prev_text:
            payload["previous_text"] = prev_text[:12000]
        if issues:
            payload["issues_to_fix"] = issues[:100]
        if reference_text:
            payload["reference_schematic"] = reference_text[:20000]
        user = json.dumps(payload)
        return system, user

    def generate_text(
        self,
        spec_json_text: str,
        allowed_by_ref: Dict[str, List[str]],
        prev_text: Optional[str] = None,
        issues: Optional[List[str]] = None,
        reference_text: Optional[str] = None,
    ) -> Tuple[str, str]:
        system, user = self._build_prompt(spec_json_text, allowed_by_ref, prev_text, issues, reference_text)
        self._add_history("user", user)
        messages: List[dict] = []
        messages.extend(self._history)
        messages.insert(0, {"role": "system", "content": system})

        # dump prompt for debugging
        try:
            if self._debug_dir:
                (self._debug_dir / f"iter_{self._iter_counter:02d}_prompt.json").write_text(
                    json.dumps({"system": system, "messages": messages}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass

        try:
            reply = self.llm.chat(messages, max_completion_tokens=7000)
        except Exception as e:
            reply = ""
            try:
                if self._debug_dir:
                    (self._debug_dir / f"iter_{self._iter_counter:02d}_error.txt").write_text(repr(e), encoding="utf-8")
            except Exception:
                pass

        if not reply:
            return "", ""
        self._add_history("assistant", reply)

        start = reply.find("(kicad_sch")
        end = reply.rfind(")")
        if start != -1 and end != -1 and end > start:
            return reply[start : end + 1], reply
        return reply.strip(), reply

    def _seed_schematic(self, title: str) -> str:
        return (
            "(kicad_sch (version 20250114) (generator eeschema)\n"
            "  (paper \"A4\")\n"
            "  (title_block (title \"%s\"))\n"
            ")\n" % (title or "Untitled")
        )

    def write(
        self,
        spec_json_text: str,
        allowed_by_ref: Dict[str, List[str]],
        out_path: Path,
        prev_text: Optional[str] = None,
        issues: Optional[List[str]] = None,
        reference_text: Optional[str] = None,
    ) -> None:
        # configure debug dir
        self._iter_counter += 1
        self._debug_dir = out_path.parent / "gpt_debug"
        self._debug_dir.mkdir(parents=True, exist_ok=True)

        parsed_text, raw_reply = self.generate_text(
            spec_json_text, allowed_by_ref, prev_text=prev_text, issues=issues, reference_text=reference_text
        )

        # debug dump
        try:
            if self._debug_dir:
                (self._debug_dir / f"iter_{self._iter_counter:02d}_reply.txt").write_text(raw_reply or "", encoding="utf-8")
        except Exception:
            pass

        if parsed_text.strip().startswith("(kicad_sch") and parsed_text.strip().endswith(")"):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(parsed_text, encoding="utf-8")
        else:
            if prev_text and prev_text.strip():
                out_path.write_text(prev_text, encoding="utf-8")
            else:
                seed = self._seed_schematic(title="Untitled")
                out_path.write_text(seed, encoding="utf-8")
