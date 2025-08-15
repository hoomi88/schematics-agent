## Schematic Agent

Dual GPT-based agents that convert JSON circuit descriptions into KiCad `.kicad_sch` and validate via ERC, with a PySide6 GUI to upload JSON and monitor progress.

### Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Optionally configure environment variables in `.env`:

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5
```

### Run GUI

```bash
python -m gui.app
```

### CLI (optional)

```bash
python main.py --input data/example.json --out-dir output
```

### KiCad ERC

This project attempts to run `kicad-cli sch erc` (KiCad 7/8). If unavailable, it falls back to `kicad-sch sch erc`.

### JSON Input (minimal example)

```json
{
  "title": "Blink LED",
  "parts": [
    {"ref": "U1", "type": "MCU", "symbol": "MCU_Microchip_ATtiny85", "pins": {"VCC": "+5V", "GND": "GND", "PB0": "LED"}},
    {"ref": "R1", "type": "R", "value": "1k", "pins": {"1": "LED", "2": "+5V"}},
    {"ref": "D1", "type": "LED", "pins": {"A": "LED", "K": "GND"}}
  ],
  "nets": [
    {"name": "+5V"}, {"name": "GND"}, {"name": "LED"}
  ]
}
```

### Notes
- The generator creates a basic S-expression `.kicad_sch` (KiCad 6/7+ format) with simple symbol placement and wires.
- The validator checks basic connectivity and bounding-box overlaps, then runs ERC if KiCad is installed.
- Iteration between architect and validator is supported in scaffolding; extend as needed.

