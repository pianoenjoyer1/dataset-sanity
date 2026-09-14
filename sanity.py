"""Inspect CSV data quality and produce a portable HTML or JSON report."""
import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
from html import escape
import json
from pathlib import Path


def number(value):
    try:
        parsed = Decimal(value)
        return parsed if parsed.is_finite() else None
    except InvalidOperation:
        return None


def profile(path, delimiter=","):
    if len(delimiter) != 1 or delimiter in "\r\n\0":
        raise ValueError("Delimiter must be one non-newline character")
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        try:
            headers = [name.strip() for name in next(reader)]
        except StopIteration:
            raise ValueError("CSV is empty")
        if not headers or any(not h for h in headers):
            raise ValueError("Every column must have a name")
        if len(set(headers)) != len(headers):
            raise ValueError("Duplicate column names are not supported")
        rows = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(headers):
                raise ValueError("CSV line {}: expected {} fields, got {}".format(reader.line_num, len(headers), len(row)))
            rows.append(tuple(value.strip() for value in row))
    total = len(rows)
    columns = []
    warnings = []
    for index, name in enumerate(headers):
        values = [row[index] for row in rows]
        present = [v for v in values if v != ""]
        frequencies = Counter(present)
        missing = total - len(present)
        numeric = [parsed for parsed in map(number, present) if parsed is not None]
        kind = "empty" if not present else "numeric" if len(numeric) == len(present) else "mixed" if numeric else "text"
        column = {"name": name, "kind": kind, "missing": missing,
                  "missing_percent": round(100 * missing / total, 2) if total else 0,
                  "unique": len(frequencies), "numeric_count": len(numeric),
                  "top_values": [{"value": value, "count": count} for value, count in frequencies.most_common(5)]}
        if kind == "numeric":
            # Decimal strings preserve large values without emitting invalid JSON Infinity.
            column["min"] = str(min(numeric))
            column["max"] = str(max(numeric))
        columns.append(column)
        if missing:
            warnings.append("{}: {} missing values".format(name, missing))
        if kind == "mixed":
            warnings.append("{}: mixed numeric and text values".format(name))
        if total and len(frequencies) == 1:
            warnings.append("{}: only one distinct nonempty value".format(name))
    duplicates = total - len(set(rows))
    if duplicates:
        warnings.append("{} duplicate rows (after trimming whitespace)".format(duplicates))
    if not total:
        warnings.append("No data rows")
    return {"file": Path(path).name, "rows": total, "column_count": len(headers),
            "duplicate_rows": duplicates, "missing_cells": sum(c["missing"] for c in columns),
            "warnings": warnings, "columns": columns}


def html_report(report):
    def safe(value):
        return escape(str(value), quote=True)
    rows = []
    for column in report["columns"]:
        top = ", ".join("{} ({})".format(v["value"], v["count"]) for v in column["top_values"])
        numeric_range = "{} → {}".format(column["min"], column["max"]) if "min" in column else "—"
        rows.append("<tr>" + "".join("<td>{}</td>".format(safe(v)) for v in [
            column["name"], column["kind"], "{} ({}%)".format(column["missing"], column["missing_percent"]),
            column["unique"], numeric_range, top]) + "</tr>")
    alerts = "".join("<li>{}</li>".format(safe(w)) for w in report["warnings"]) or "<li>No issues detected by these checks.</li>"
    cards = "".join('<div class="card"><strong>{}</strong><span>{}</span></div>'.format(safe(value), label)
                    for value, label in [(report["rows"], "Rows"), (report["column_count"], "Columns"),
                                         (report["missing_cells"], "Missing cells"), (report["duplicate_rows"], "Duplicate rows")])
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Dataset Sanity</title>
<style>:root{font:16px/1.6 system-ui,sans-serif;color:#e5e9f5;background:#111827}*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:45px 25px}header{color:#9aaace;letter-spacing:.15em;font-size:13px}h1{font-size:42px;letter-spacing:-.04em;margin:28px 0 4px;overflow-wrap:anywhere}.intro{color:#a5b4cc;margin:0 0 32px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.card{background:#1d293e;padding:23px;border:1px solid #344158;border-radius:13px}.card strong{display:block;font-size:36px;color:#8adac8}.card span{color:#b4c0d6;font-size:14px}h2{font-size:20px;margin-top:35px}.table{overflow:auto;border:1px solid #344158;border-radius:12px}table{border-collapse:collapse;min-width:800px;width:100%;font-size:14px}th,td{padding:15px;text-align:left;border-bottom:1px solid #344158;max-width:340px;overflow-wrap:anywhere;vertical-align:top}th{color:#a4b5d6;background:#1d293e}li{margin:8px 0}footer{color:#8e9fb9;font-size:13px;margin-top:32px}@media(max-width:650px){.cards{grid-template-columns:1fr 1fr}h1{font-size:32px}}</style>
<main><header>DATASET / SANITY</header><h1>""" + safe(report["file"]) + """</h1>
<p class="intro">A quick look at data quality before training or analysis.</p><section class="cards">""" + cards + """</section>
<h2>Checks to review</h2><ul>""" + alerts + """</ul><h2>Column profile</h2><div class="table"><table><thead><tr><th>Column</th><th>Inferred type</th><th>Missing</th><th>Unique</th><th>Numeric range</th><th>Top values</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table></div>
<footer>Empty strings count as missing. Values are trimmed before comparison. Type inference is heuristic; identifiers may look numeric. This report contains example values from the input. No remote resources or tracking.</footer></main></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--format", choices=["html", "json"], default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-issues", action="store_true")
    args = parser.parse_args()
    try:
        report = profile(args.csv_file, args.delimiter)
        text = html_report(report) if args.format == "html" else json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            if args.output.resolve() == args.csv_file.resolve():
                raise ValueError("Output must not overwrite the input")
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        parser.error(str(error))
    return 1 if args.fail_on_issues and report["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
