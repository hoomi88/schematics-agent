import argparse
from pathlib import Path
from agents.orchestrator import run_orchestration


def main():
    parser = argparse.ArgumentParser(description="Generate KiCad 9 schematic via GPT from LLD JSON, then validate via GPT and ERC")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=False, type=Path, default=Path("output"))
    parser.add_argument("--iters", required=False, type=int, default=3)
    parser.add_argument("--llm-validator", action="store_true", help="Enable GPT-based KiCad 9 compliance checks")
    args = parser.parse_args()

    sch_file = run_orchestration(
        json_path=args.input,
        out_dir=args.out_dir,
        max_iters=args.iters,
        progress_cb=print,
        validator_use_llm=args.llm_validator,
    )
    print("Schematic written to:", sch_file)


if __name__ == "__main__":
    main()
