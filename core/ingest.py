from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple
import json
from core.models import CircuitSpec, PartSpec, NetSpec


def _map_component_to_partspec(component: Dict[str, Any], index: int) -> PartSpec:
    cid = component.get("id", f"U{index+1}")
    category = (component.get("category") or "").lower()
    value = component.get("value")

    type_guess = "U"
    symbol_guess = None

    if category == "passive":
        if str(cid).upper().startswith("C"):
            type_guess = "C"
            symbol_guess = "Device:C"
        elif str(cid).upper().startswith("R"):
            type_guess = "R"
            symbol_guess = "Device:R"
        else:
            type_guess = "R"
            symbol_guess = "Device:R"
    elif category in {"microcontroller", "processor", "mcu"}:
        type_guess = "MCU"
        symbol_guess = "Device:U"
    elif category in {"sensor", "power-protection", "power-supply"}:
        type_guess = "U"
        symbol_guess = "Device:U"
    elif category == "connector":
        type_guess = "Conn"
        symbol_guess = "Connector_Generic:Conn_01x02"

    return PartSpec(
        ref=str(cid),
        type=type_guess,
        symbol=symbol_guess,
        value=value,
        pins={},
        position=None,
        rotation=0,
    )


def _convert_pseudo_cad_schema(data: Dict[str, Any]) -> CircuitSpec:
    title = data.get("device", {}).get("name") or "Untitled"

    parts: List[PartSpec] = []
    for idx, comp in enumerate(data.get("components", [])):
        try:
            parts.append(_map_component_to_partspec(comp, idx))
        except Exception:
            continue

    nets: List[NetSpec] = []
    seen = set()
    for n in data.get("nets", []):
        for key in ("id", "name"):
            name = n.get(key)
            if isinstance(name, str) and name and name not in seen:
                nets.append(NetSpec(name=name))
                seen.add(name)
    for pd in data.get("powerDomains", []):
        name = pd.get("name")
        if isinstance(name, str) and name and name not in seen:
            nets.append(NetSpec(name=name))
            seen.add(name)

    if "GND" not in seen:
        nets.append(NetSpec(name="GND"))

    return CircuitSpec(title=title, parts=parts, nets=nets)


def load_circuit_spec(path: Path) -> CircuitSpec:
    raw_text = Path(path).read_text(encoding="utf-8")
    raw = json.loads(raw_text)
    if isinstance(raw, dict) and "components" in raw:
        return _convert_pseudo_cad_schema(raw)
    if isinstance(raw, dict) and ("parts" in raw or "nets" in raw):
        return CircuitSpec(**raw)
    return CircuitSpec(title="Untitled", parts=[], nets=[])


def read_json_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


# Extend CircuitSpec to provide a minimal adapter when needed
setattr(
    CircuitSpec,
    "to_generated_design",
    lambda self: self,  # placeholder; unused in new GPT path
)

setattr(
    CircuitSpec,
    "title_or_default",
    lambda self: (self.title or "design"),
)
