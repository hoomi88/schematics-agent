from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional
from core.ingest import load_circuit_spec, read_json_text
from core.models import CircuitSpec
from agents.validator_agent import ValidatorAgent
from kicad.gpt_writer import GptSchematicWriter
from kicad.rag import candidates_for_parts
from kicad.erc import run_erc, parse_erc_violations, run_erc_with_json, summarize_erc_json
import json
import shutil
import re


ProgressFn = Callable[[str], None]


def _emit(progress_cb: Optional[ProgressFn], msg: str) -> None:
    if progress_cb:
        progress_cb(msg)


def run_orchestration(
    json_path: Path,
    out_dir: Path,
    max_iters: int = 3,
    progress_cb: Optional[ProgressFn] = None,
    validator_use_llm: bool = True,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clean debug dir at the start of each run
    debug_dir = out_dir / "gpt_debug"
    if debug_dir.exists():
        try:
            shutil.rmtree(debug_dir)
        except Exception:
            pass

    circuit: CircuitSpec = load_circuit_spec(json_path)
    raw_text = read_json_text(json_path)

    allowed = candidates_for_parts(circuit.parts, max_per_lib=10)
    expected_refs = list(allowed.keys())

    gpt_generator = GptSchematicWriter()
    validator = ValidatorAgent(use_llm=validator_use_llm)

    # Prefer explicit minimal template if present
    reference_text = None
    template_root = Path("kicad_sch_min_symbol_template.kicad_sch")
    if template_root.exists():
        try:
            reference_text = template_root.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            reference_text = None

    # Otherwise try reference in out_dir
    if reference_text is None:
        reference_path = out_dir / "demo_project.kicad_sch"
        if reference_path.exists():
            try:
                reference_text = reference_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                reference_text = None

    # Finally fallback to project demo if available
    if reference_text is None:
        demo_root = Path("output/demo_project.kicad_sch")
        if demo_root.exists():
            try:
                reference_text = demo_root.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                reference_text = None

    sch_path = out_dir / f"{(circuit.title or 'design').replace(' ', '_')}.kicad_sch"
    prev_text: Optional[str] = None
    issues: list[str] = []

    for iteration in range(1, max_iters + 1):
        _emit(progress_cb, f"GPT Generator: writing schematic (iteration {iteration}) from LLD JSON + RAG...")
        gpt_generator.write(
            spec_json_text=raw_text,
            allowed_by_ref=allowed,
            out_path=sch_path,
            prev_text=prev_text,
            issues=issues,
            reference_text=reference_text,
        )

        try:
            prev_text = sch_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            prev_text = None

        _emit(progress_cb, "GPT Validator: checking KiCad 9 compliance and layout...")
        issues = validator.validate(sch_path)
        if issues:
            for iss in issues:
                _emit(progress_cb, f"Issue: {iss}")
        else:
            _emit(progress_cb, "No issues detected by GPT validator.")

        # Ensure all expected refs are instantiated
        missing_refs: list[str] = []
        if prev_text:
            found_refs = set(re.findall(r"\(property\s+\"Reference\"\s+\"([A-Za-z]+\d+)\"", prev_text))
            for r in expected_refs:
                if r not in found_refs:
                    missing_refs.append(r)
        if missing_refs:
            msg = "Missing placed instances for refs: " + ", ".join(missing_refs)
            _emit(progress_cb, msg)
            issues.append(msg)

        _emit(progress_cb, "Running ERC (JSON, if available)...")
        erc_proc, erc_json, json_path_tmp = run_erc_with_json(sch_path)
        erc_rc = None
        erc_violations = None
        erc_summary_lines = []
        if erc_proc is not None:
            erc_rc = erc_proc.returncode
            erc_summary_lines = summarize_erc_json(erc_json, max_items=15)
            for line in erc_summary_lines:
                _emit(progress_cb, line)
        else:
            erc = run_erc(sch_path)
            if erc is not None:
                erc_rc = erc.returncode
                erc_violations = parse_erc_violations((erc.stdout or "") + "\n" + (erc.stderr or ""))
                _emit(progress_cb, f"ERC exit code: {erc_rc}")
                if erc.stdout:
                    _emit(progress_cb, erc.stdout.strip())
                if erc.stderr:
                    _emit(progress_cb, erc.stderr.strip())

        if erc_json is not None and erc_violations is None:
            try:
                erc_violations = len(erc_json.get("violations") or [])
            except Exception:
                pass

        if (not issues) and (erc_rc == 0) and (erc_violations is not None and erc_violations == 0):
            _emit(progress_cb, "Schematic accepted (no GPT issues, ERC exit 0, violations 0).")
            break

        feedback = {"validator_feedback": issues}
        if erc_rc is not None:
            feedback["erc_returncode"] = erc_rc
        if erc_violations is not None:
            feedback["erc_violations"] = erc_violations
        if erc_summary_lines:
            feedback["erc_summary"] = erc_summary_lines
        gpt_generator._add_history("user", json.dumps(feedback))

    return sch_path

