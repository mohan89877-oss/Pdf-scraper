import sys
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path("scripts")


def run(script, *args):
    subprocess.run([sys.executable, str(SCRIPTS_DIR / script)] + list(args), check=True)


def main():
    input_dir = Path("input")
    for pdf_path in sorted(input_dir.glob("*.pdf")):
        stem = pdf_path.stem
        state_dir = Path("state") / stem
        state_dir.mkdir(parents=True, exist_ok=True)

        run("extract_text.py", str(pdf_path))
        run("extract_mcqs.py", stem)

        extract_flag = state_dir / "extract_complete.flag"
        if not (extract_flag.exists() and extract_flag.read_text().strip() == "1"):
            print(f"{stem}: extraction not finished yet, will resume next run.")
            continue

        run("knowledge_check.py", stem)

        resolve_flag = state_dir / "resolve_complete.flag"
        if not (resolve_flag.exists() and resolve_flag.read_text().strip() == "1"):
            print(f"{stem}: resolution not finished yet, will resume next run.")
            continue

        csv_flag = state_dir / "csv_built.flag"
        if not csv_flag.exists():
            run("build_csv.py", stem)
            csv_flag.write_text("1")


if __name__ == "__main__":
    main()
