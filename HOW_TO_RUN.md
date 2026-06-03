# How to run this project

Everything is **self-contained**: all data is bundled inside this folder, and every script uses
**relative paths**. You do **not** need to edit any file locations — you only need to (a) set up a
Python environment once and (b) run the scripts **from inside this folder**.

## Prerequisites
- Python 3.9 or newer.

## One-time setup
From a terminal, inside this project folder:

```bash
python3 -m venv .venv                 # create a fresh virtual environment
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt       # install all dependencies
```

## Run the analyses
Always run **from inside this project folder** (the scripts read `data_cache/` and write outputs to
the current directory):

```bash
python sectorwide_full.py             # main strategy backtest -> sectorwide_full.json
python survivorship_corrected.py      # point-in-time survivorship test -> survivorship_corrected.json
python bakeoff_variants.py            # variant bake-off (finds V1 defensive sleeve) -> bakeoff_variants.json
python bakeoff_improvements.py        # improvements bake-off (layered on V1) -> bakeoff_improvements.json
```

To regenerate the documents and dashboard:

```bash
python make_sectorwide_brief.py       # -> SectorWide_Strategy_Overview.docx
python make_bakeoff_memo.py           # -> Strategy_Refinement_Findings.docx
python make_sectorwide_dashboard.py   # -> sectorwide_dashboard.html (open in any browser)
```

## Notes
- **No internet needed.** All market data is cached in `data_cache/` and `course_data/`, and the
  Bloomberg point-in-time file (`Total Returns Hard Copy.xlsx`) is bundled. Internet is only required
  if you choose to re-pull fresh prices via `pull_data.py`.
- **Do not copy the `.venv` folder** between machines — it is machine-specific. Recreate it with the
  setup steps above.
- Outputs (`.json`, `.png`, `.docx`, `.html`) are written into this folder and overwrite the existing ones.
