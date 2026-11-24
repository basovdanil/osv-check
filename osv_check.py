#!/usr/bin/env python3
"""usage: osv_check.py FILE [--expect FILE] [--json] [--limit N]

Пересчитывает оборотно-сальдовую ведомость из CSV и находит расхождения:
арифметику строк, красное сальдо на активных и пассивных счетах,
отрицательные обороты, неравенство итогов дебета и кредита.

Коды возврата:
  0 — находок нет (или набор совпал с --expect)
  2 — ошибка аргументов
  3 — файл не найден или в шапке нет нужных колонок
  4 — есть находки / набор не совпал с ожидаемым
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

COLUMNS = (
    "account", "name", "type",
    "open_debit", "open_credit",
    "turn_debit", "turn_credit",
    "close_debit", "close_credit",
)
ACTIVE = "активный"
PASSIVE = "пассивный"
EPS = 0.01


class BadFile(Exception):
    """Файл не читается или не похож на выгрузку ОСВ."""


def parse_num(value) -> float:
    """Число из ячейки 1С: '1 234 567,89', '1\xa0234', '(1 000)', пусто."""
    if value is None:
        return 0.0
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if text in ("", "-", "—", "–"):
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace(",", ".")
    try:
        result = float(text)
    except ValueError as exc:
        raise BadFile(f"не число: {value!r}") from exc
    return -result if negative else result


def load_rows(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            missing = [column for column in COLUMNS if column not in header]
            if missing:
                raise BadFile("нет колонок: " + ", ".join(missing))
            return list(reader)
    except OSError as exc:
        raise BadFile(f"не открыть {path}: {exc.strerror}") from exc


def check(rows: list[dict]) -> tuple[list[dict], dict[str, float]]:
    findings: list[dict] = []
    totals = {
        "open_debit": 0.0, "open_credit": 0.0,
        "turn_debit": 0.0, "turn_credit": 0.0,
        "close_debit": 0.0, "close_credit": 0.0,
    }

    for row in rows:
        account = row["account"]
        values = {key: parse_num(row[key]) for key in totals}
        for key, value in values.items():
            totals[key] += value

        open_net = values["open_debit"] - values["open_credit"]
        turn_net = values["turn_debit"] - values["turn_credit"]
        close_net = values["close_debit"] - values["close_credit"]
        diff = round(close_net - (open_net + turn_net), 2)
        if abs(diff) > EPS:
            findings.append({"code": "row_mismatch", "account": account, "value": diff})

        kind = (row["type"] or "").strip().lower()
        credit_close = values["close_credit"]
        debit_close = values["close_debit"]
        if kind == ACTIVE and credit_close > EPS:
            findings.append({"code": "red_balance", "account": account, "value": credit_close})
        elif kind == PASSIVE and debit_close > EPS:
            findings.append({"code": "red_balance", "account": account, "value": debit_close})
        elif kind not in (ACTIVE, PASSIVE, "активно-пассивный"):
            findings.append({"code": "unknown_type", "account": account, "value": 0.0})

        for field in ("turn_debit", "turn_credit"):
            if values[field] < -EPS:
                findings.append({"code": "negative_turnover", "account": account, "value": values[field]})

    for moment in ("open", "turn", "close"):
        diff = round(totals[f"{moment}_debit"] - totals[f"{moment}_credit"], 2)
        if abs(diff) > EPS:
            findings.append({"code": f"totals_{moment}", "account": "", "value": diff})

    return findings, totals


def normalize(items) -> list[tuple]:
    """Находки к сравнимому виду: и объекты, и тройки [код, счёт, сумма]."""
    triples = [
        (item["code"], str(item["account"]), float(item["value"]))
        if isinstance(item, dict) else (item[0], str(item[1]), float(item[2]))
        for item in items
    ]
    return sorted((code, account, round(value, 2)) for code, account, value in triples)


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,.2f}".replace(",", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osv_check.py",
        description="Проверка оборотно-сальдовой ведомости из 1С (CSV).",
    )
    parser.add_argument("file", help="CSV с колонками: " + ", ".join(COLUMNS))
    parser.add_argument("--expect", metavar="FILE", help="JSON с ожидаемым набором находок")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    parser.add_argument("--limit", type=int, default=200, help="сколько находок печатать (по умолчанию 200)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        rows = load_rows(args.file)
    except BadFile as exc:
        print(f"osv_check: {exc}", file=sys.stderr)
        return 3

    expected = None
    if args.expect:
        try:
            with open(args.expect, encoding="utf-8") as handle:
                expected = normalize(json.load(handle))
        except (OSError, ValueError) as exc:
            print(f"osv_check: не читается {args.expect}: {exc}", file=sys.stderr)
            return 3

    findings, totals = check(rows)
    matched = None if expected is None else normalize(findings) == expected
    status = "ok" if not findings else "findings"
    if matched is False:
        status = "mismatch"

    if args.json:
        print(json.dumps({
            "file": args.file,
            "rows": len(rows),
            "status": status,
            "findings": findings,
            "totals": {key: round(value, 2) for key, value in totals.items()},
            "expected_matched": matched,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"строк: {len(rows)}, находок: {len(findings)}")
        for item in findings[: args.limit]:
            where = f" счёт {item['account']}" if item["account"] else ""
            print(f"  {item['code']}{where}: {money(item['value'])}")
        if len(findings) > args.limit:
            print(f"  … ещё {len(findings) - args.limit}")
        print("итоги по ведомости:")
        for key, value in totals.items():
            print(f"  {key}: {money(value)}")
        if matched is not None:
            print("набор находок совпал с ожидаемым" if matched else "набор находок не совпал с ожидаемым")

    if matched is False:
        return 4
    if matched is True:
        return 0
    return 0 if not findings else 4


if __name__ == "__main__":
    sys.exit(main())
