from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
import json


class PartSpec(BaseModel):
    ref: str
    type: str
    symbol: Optional[str] = None
    value: Optional[str] = None
    pins: Dict[str, str] = Field(default_factory=dict)
    position: Optional[Tuple[int, int]] = None
    rotation: Optional[int] = 0


class NetSpec(BaseModel):
    name: str


class CircuitSpec(BaseModel):
    title: Optional[str] = None
    parts: List[PartSpec] = Field(default_factory=list)
    nets: List[NetSpec] = Field(default_factory=list)

    @staticmethod
    def from_json_file(path: Path) -> "CircuitSpec":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return CircuitSpec(**data)


class PlacedPart(BaseModel):
    ref: str
    symbol: str
    value: Optional[str] = None
    position: Tuple[int, int]
    rotation: int = 0
    pins: Dict[str, str] = Field(default_factory=dict)
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)


class GeneratedDesign(BaseModel):
    title: str = "Untitled"
    parts: List[PlacedPart] = Field(default_factory=list)
    nets: List[str] = Field(default_factory=list)

    def net_exists(self, name: str) -> bool:
        return name in self.nets

