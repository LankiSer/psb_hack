"""Собирает минимальный ZIP с файлами в корне, без ключей и локальных данных."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]

def build(output: Path | None = None) -> Path:
    output = output or ROOT / "dist" / "psb-submission.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in ("solution.py", "psb_engine.py"):
            archive.write(ROOT / "backend" / name, name)
        archive.write(ROOT / "requirements.txt", "requirements.txt")
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {"solution.py", "psb_engine.py", "requirements.txt"}
        assert archive.testzip() is None
    if output.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Архив превышает 128 МБ")
    return output

if __name__ == "__main__":
    path = build()
    print(f"Ready: {path} ({path.stat().st_size} bytes)")
