"""Собирает минимальный ZIP с файлами в корне, без ключей и локальных данных."""
from pathlib import Path
import hashlib
import json
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
    # Паспорт лежит рядом, не меняет требуемую структуру архива и не содержит окружение.
    with ZipFile(output) as archive:
        manifest = {"archive": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                    "files": {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}}
    output.with_suffix('.build.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return output

if __name__ == "__main__":
    path = build()
    print(f"Ready: {path} ({path.stat().st_size} bytes)")
