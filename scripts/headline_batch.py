"""Build batched headline-extraction prompts for slide documents and split the results.

    build [--size N] [--ids ID ...] [--force]   write batch/hNNN.md for pending slide docs
    split batch/hNNN.json [--out DIR]           validate and write DIR/{id}.json
    show ID ...                                 print the headlines parsed from blind/ID.md
"""
import argparse
import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / "batch"
OUT = ROOT / "extract-compress"
DOC_ID = re.compile(r'<document id="([0-9a-f]+)"')
SLIDE_PREFIX = re.compile(r"^(スライド\s*\d+|\d+[.．])\s*[:：]?\s*")
TITLE_LINE = re.compile(r"^\*{0,2}(?:タイトル\s*[:：])?\s*(.*?)\*{0,2}$")
TITLE_LABEL = re.compile(r"^\*{0,2}タイトル\s*[:：]\s*\*{0,2}\s*(.+?)\s*\*{0,2}$")


def headlines(text):
    """Return slide titles.

    Each markdown heading is a provisional title; an explicit '**タイトル:** ...' line under it
    replaces it (the heading is then only a slide label). A bare 'スライドN' heading takes the
    next non-empty line as its title.
    """
    out = []
    current = None
    pending = False
    for line in text.splitlines():
        line = line.strip()
        label = TITLE_LABEL.match(line)
        heading = re.match(r"^#{1,4}\s*(.*)$", line)
        if label:
            if current is not None:
                out[current] = label.group(1)
                current = None
            else:
                out.append(label.group(1))
            pending = False
        elif heading:
            title = SLIDE_PREFIX.sub("", heading.group(1).strip())
            pending = not title
            current = None
            if title:
                out.append(title)
                current = len(out) - 1
        elif pending and line:
            pending = False
            title = TITLE_LINE.match(line).group(1)
            if title:
                out.append(title)
    return [t for t in dict.fromkeys(out) if t not in ("タイトル", "表紙")]


def load_template():
    return (ROOT / "compress-prompt.md").read_text().split("\n---\n", 1)[1].strip() + "\n"


def doc_headlines(blind_id):
    return headlines((ROOT / "blind" / f"{blind_id}.md").read_text())


def render_doc(m):
    lines = "\n".join(doc_headlines(m["blind_id"]))
    return f'<document id="{m["blind_id"]}" request="{escape(m["request"])}">\n{lines}\n</document>'


def build(args):
    mapping = json.loads((ROOT / "mapping.json").read_text())
    if args.ids:
        by_id = {m["blind_id"]: m for m in mapping}
        targets = [by_id[i] for i in args.ids]
    else:
        targets = [
            m
            for m in mapping
            if m["genre"] == "プレゼン資料" and (args.force or not (OUT / f"{m['blind_id']}.json").exists())
        ]
    for m in targets:
        n = len(doc_headlines(m["blind_id"]))
        if n < 5:
            print(f"warning: {m['blind_id']} ({m['source']}) has only {n} headlines")
    BATCH.mkdir(exist_ok=True)
    n = max((int(p.stem[1:]) for p in BATCH.glob("h[0-9][0-9][0-9].md")), default=0)
    template = load_template()
    for i in range(0, len(targets), args.size):
        n += 1
        prompt = BATCH / f"h{n:03d}.md"
        chunk = targets[i : i + args.size]
        text = template.replace("{documents}", "\n\n".join(render_doc(m) for m in chunk))
        prompt.write_text(text.replace("{output_path}", str(prompt.with_suffix(".json"))))
        print(prompt.relative_to(ROOT), len(chunk), sep="\t")


def split(args):
    result_path = Path(args.result)
    ids = DOC_ID.findall(result_path.with_suffix(".md").read_text())
    result = json.loads(result_path.read_text())
    out = Path(args.out) if args.out else OUT
    out.mkdir(parents=True, exist_ok=True)
    missing = [i for i in ids if i not in result]
    extra = [k for k in result if k not in ids]
    total = mismatch = 0
    for i in ids:
        if i not in result:
            continue
        titles = doc_headlines(i)
        findings = result[i]["findings"]
        for f in findings:
            total += 1
            if f["quote"] not in titles:
                mismatch += 1
                print(f"quote mismatch: {i}: {f['quote']}")
        (out / f"{i}.json").write_text(json.dumps({"findings": findings}, ensure_ascii=False, indent=2) + "\n")
    print(f"docs: {len(ids) - len(missing)}/{len(ids)}, findings: {total}, quote mismatch: {mismatch}")
    if missing or extra:
        print(f"missing: {missing}, unexpected: {extra}")


def show(args):
    for i in args.ids:
        print(f"== {i}")
        for t in doc_headlines(i):
            print(f"  {t}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    b = sub.add_parser("build")
    b.add_argument("--size", type=int, default=12)
    b.add_argument("--ids", nargs="+")
    b.add_argument("--force", action="store_true", help="include docs already extracted")
    b.set_defaults(func=build)
    s = sub.add_parser("split")
    s.add_argument("result")
    s.add_argument("--out")
    s.set_defaults(func=split)
    sh = sub.add_parser("show")
    sh.add_argument("ids", nargs="+")
    sh.set_defaults(func=show)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
