# Building a standalone executable (.exe)

BEAMER can be packaged into a single standalone `.exe` using **PyInstaller**.

## 1. Install PyInstaller

```bash
pip install pyinstaller
```

## 2. Build

From the project root (where `main.py` is), run:

```bash
python -m PyInstaller --onefile --noconsole --icon=beam_icon.ico --add-data="beam_icon.png;." main.py
```

Flags:

- `--onefile` – bundle everything into a single `.exe`,
- `--noconsole` – launch without a console window (GUI app),
- `--icon=beam_icon.ico` – executable icon,
- `--add-data="beam_icon.png;."` – bundle the PNG icon into the package root.

> **Note:** the `--add-data` path separator is `;` on Windows and `:` on
> Linux / macOS — e.g. `--add-data="beam_icon.png:."`.

## 3. Result

The finished executable appears in the **`dist`** folder as **`main.exe`** and
runs standalone, without a Python installation.
