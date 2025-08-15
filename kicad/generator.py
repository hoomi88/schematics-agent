from __future__ import annotations
from pathlib import Path
from typing import TextIO
from uuid import uuid4
from core.models import GeneratedDesign


class KiCadSchematicGenerator:
    def _write_header(self, f: TextIO, title: str) -> None:
        f.write("(kicad_sch (version 20211014) (generator \"schematic-agent\")\n")
        f.write("  (paper \"A4\")\n")
        f.write("  (title_block\n")
        f.write(f"    (title \"{title}\")\n")
        f.write("  )\n")

    def _write_property(self, f: TextIO, name: str, value: str, x: int, y: int, pid: int) -> None:
        f.write(
            f"    (property \"{name}\" \"{value}\" (id {pid}) (at {x} {y} 0) (effects (font (size 1.27 1.27))))\n"
        )

    def _write_symbol(self, f: TextIO, ref: str, symbol: str, value: str | None, x: int, y: int, rot: int) -> None:
        u = str(uuid4())
        f.write(
            "  (symbol (lib_id \"%s\")\n" % symbol
        )
        f.write(
            "    (at %d %d %d)\n" % (x, y, rot)
        )
        f.write("    (unit 1) (in_bom yes) (on_board yes)\n")
        f.write(f"    (uuid {u})\n")
        self._write_property(f, "Reference", ref, x, y - 5, 0)
        if value:
            self._write_property(f, "Value", value, x, y + 5, 1)
        f.write("  )\n")

    def _write_footer(self, f: TextIO) -> None:
        f.write(")\n")

    def write_schematic(self, design: GeneratedDesign, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            self._write_header(f, design.title)
            for part in design.parts:
                x, y = part.position
                self._write_symbol(
                    f,
                    ref=part.ref,
                    symbol=part.symbol,
                    value=part.value,
                    x=x,
                    y=y,
                    rot=part.rotation or 0,
                )
            # Note: wires/labels are not emitted in this minimal generator
            self._write_footer(f)

