"""Build batched extraction prompts and split their results into extract/.

    build [--size N] [--ids ID ...] [--force]   write batch/bNNN.md for pending docs
    split batch/bNNN.json [--out DIR]           validate and write DIR/{id}.json
"""
import argparse
import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / "batch"
DOC_ID = re.compile(r'<document id="([0-9a-f]+)"')


def load_template():
    return (ROOT / "extract-prompt.md").read_text().split("\n---\n", 1)[1].strip() + "\n"


def render_doc(m):
    body = (ROOT / "blind" / f"{m['blind_id']}.md").read_text().strip()
    attrs = f'id="{m["blind_id"]}" genre="{escape(m["genre"])}" request="{escape(m["request"])}"'
    return f"<document {attrs}>\n{body}\n</document>"


def build(args):
    mapping = json.loads((ROOT / "mapping.json").read_text())
    if args.ids:
        by_id = {m["blind_id"]: m for m in mapping}
        targets = [by_id[i] for i in args.ids]
    else:
        targets = [m for m in mapping if args.force or not (ROOT / "extract" / f"{m['blind_id']}.json").exists()]
    BATCH.mkdir(exist_ok=True)
    n = max((int(p.stem[1:]) for p in BATCH.glob("b[0-9][0-9][0-9].md")), default=0)
    template = load_template()
    for i in range(0, len(targets), args.size):
        n += 1
        prompt = BATCH / f"b{n:03d}.md"
        chunk = targets[i : i + args.size]
        text = template.replace("{documents}", "\n\n".join(render_doc(m) for m in chunk))
        prompt.write_text(text.replace("{output_path}", str(prompt.with_suffix(".json"))))
        print(prompt.relative_to(ROOT), len(chunk), sep="\t")


def split(args):
    result_path = Path(args.result)
    ids = DOC_ID.findall(result_path.with_suffix(".md").read_text())
    result = json.loads(result_path.read_text())
    out = Path(args.out) if args.out else ROOT / "extract"
    out.mkdir(parents=True, exist_ok=True)
    missing = [i for i in ids if i not in result]
    extra = [k for k in result if k not in ids]
    total = mismatch = 0
    for i in ids:
        if i not in result:
            continue
        body = (ROOT / "blind" / f"{i}.md").read_text()
        findings = result[i]["findings"]
        for f in findings:
            total += 1
            if f["quote"] not in body:
                mismatch += 1
                print(f"quote mismatch: {i}: {f['quote']}")
        (out / f"{i}.json").write_text(json.dumps({"findings": findings}, ensure_ascii=False, indent=2) + "\n")
    print(f"docs: {len(ids) - len(missing)}/{len(ids)}, findings: {total}, quote mismatch: {mismatch}")
    if missing or extra:
        print(f"missing: {missing}, unexpected: {extra}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    b = sub.add_parser("build")
    b.add_argument("--size", type=int, default=10)
    b.add_argument("--ids", nargs="+")
    b.add_argument("--force", action="store_true", help="include docs already extracted")
    b.set_defaults(func=build)
    s = sub.add_parser("split")
    s.add_argument("result")
    s.add_argument("--out")
    s.set_defaults(func=split)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
