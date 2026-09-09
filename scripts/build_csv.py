import sys
import json
import csv
from pathlib import Path


def main(pdf_stem):
    state_dir = Path("state") / pdf_stem
    accepted = json.loads((state_dir / "accepted.json").read_text())

    # sort by original q_no, then renumber sequentially for clean output
    accepted.sort(key=lambda q: q.get("q_no") or 0)

    Path("output").mkdir(exist_ok=True)
    for part_idx in range(0, len(accepted), 60):
        batch = accepted[part_idx:part_idx + 60]
        part_num = part_idx // 60 + 1
        out_path = Path("output") / f"{pdf_stem}_part{part_num}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["q_no", "question", "option_a", "option_b", "option_c", "option_d", "answer"])
            for i, q in enumerate(batch, start=1):
                writer.writerow([
                    part_idx + i, q["question"],
                    q["options"]["a"], q["options"]["b"], q["options"]["c"], q["options"]["d"],
                    q["answer"],
                ])
        print(f"Wrote {out_path} ({len(batch)} questions)")


if __name__ == "__main__":
    main(sys.argv[1])
