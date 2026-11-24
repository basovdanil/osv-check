# osv-check

[![tests](https://github.com/basovdanil/osv-check/actions/workflows/tests.yml/badge.svg)](https://github.com/basovdanil/osv-check/actions/workflows/tests.yml)

Checks a trial balance (turnover balance sheet) exported from 1C **before** the numbers reach a
report: recomputes every row and every total, and reports the rows that do not add up or carry a
balance on the wrong side of the account.

Standard library only. Python 3.8+. No pandas, no install step: one file that runs where Python runs.

## Quick start

```
python osv_check.py demo/balance.csv              # human-readable findings
python osv_check.py demo/balance.csv --json       # machine-readable
python osv_check.py demo/balance.csv --expect demo/expected.json
```

`--expect` compares the set of findings with a reference file and returns `0` when they match — a
guard against a check that silently stopped catching an error after an edit.

## What it finds

- credit balance on an active account, debit balance on a passive one;
- rows where opening + turnover ≠ closing;
- totals that do not match the sum of rows;
- negative turnover.

On the demo sheet (16 synthetic accounts) it reports 5 findings.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | no findings, or the set matched `--expect` |
| `2` | bad arguments |
| `3` | unreadable file, missing columns, broken `--expect` |
| `4` | findings present, or the set did not match the expected one |

## Tests

```
python -m unittest discover -s tests
```

13 tests: parsing 1C number formats, row arithmetic, wrong-side balance, negative turnover,
mismatched totals, CLI exit codes, `--expect` matching.

## Scope

It checks arithmetic and signs, not the meaning of postings: a wrong account correspondence can
still balance. It reads the "balance by account" export format and does not parse multi-level
grouping. No customer data is included — the demo sheet is generated and fictional.

Case write-up with numbers: <https://basovdanil.github.io/portfolio/case-osv/case-osv.html>

---

More projects: [github.com/basovdanil](https://github.com/basovdanil) · write-ups: [portfolio](https://basovdanil.github.io/portfolio/)
