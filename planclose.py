#!/usr/bin/env python3
"""PlanClose — offline maintenance-plan closer for trades.

Sits after FieldQuote / FieldClose. Turns a closed job into a recurring
service plan, a printable agreement, and a chase CSV for Chaser.

Local only. Stdlib only. No network. Not a QuantumGuard signature.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

APP = "PlanClose"
VERSION = "0.1.0"
DB_NAME = "planclose.db"

PLANS = {
    "hvac-season": {
        "name": "HVAC Season Plan",
        "trade": "HVAC",
        "visits_per_year": 2,
        "interval_days": 182,
        "price": 289.00,
        "includes": "Spring AC check and fall furnace check. Filter size on file. Priority scheduling.",
    },
    "plumb-annual": {
        "name": "Plumbing Annual",
        "trade": "Plumbing",
        "visits_per_year": 1,
        "interval_days": 365,
        "price": 189.00,
        "includes": "Whole-home water check, visible supply/drain inspection, water heater flush if accessible.",
    },
    "handyman-quarter": {
        "name": "Handyman Quarter",
        "trade": "Handyman",
        "visits_per_year": 4,
        "interval_days": 91,
        "price": 480.00,
        "includes": "Four scheduled punch-list visits. Up to 2 hours each. Materials billed separately.",
    },
}


def db_path(root: Path) -> Path:
    return root / DB_NAME


def connect(root: Path) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path(root))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY,
            customer TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            plan_code TEXT NOT NULL,
            plan_name TEXT NOT NULL,
            trade TEXT NOT NULL,
            annual_price REAL NOT NULL,
            interval_days INTEGER NOT NULL,
            source_job TEXT,
            started_on TEXT NOT NULL,
            next_visit TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT,
            at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def money(n: float) -> str:
    return f"${n:,.2f}"


def checksum(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def add_plan(conn, args) -> None:
    spec = PLANS[args.plan]
    started = date.fromisoformat(args.start) if args.start else date.today()
    nxt = started + timedelta(days=spec["interval_days"])
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    cur = conn.execute(
        """
        INSERT INTO plans (
            customer, phone, email, address, plan_code, plan_name, trade,
            annual_price, interval_days, source_job, started_on, next_visit,
            status, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            args.customer,
            args.phone or "",
            args.email or "",
            args.address or "",
            args.plan,
            spec["name"],
            spec["trade"],
            spec["price"],
            spec["interval_days"],
            args.job or "",
            started.isoformat(),
            nxt.isoformat(),
            args.notes or "",
            now,
        ),
    )
    conn.execute(
        "INSERT INTO events (plan_id, kind, detail, at) VALUES (?, 'opened', ?, ?)",
        (cur.lastrowid, spec["name"], now),
    )
    conn.commit()
    print(f"opened plan #{cur.lastrowid} {spec['name']} for {args.customer}")
    print(f"annual {money(spec['price'])}  next visit {nxt.isoformat()}")


def list_plans(conn, due_only: bool) -> None:
    today = date.today().isoformat()
    sql = "SELECT * FROM plans WHERE status = 'active'"
    if due_only:
        rows = conn.execute(sql + " AND next_visit <= ? ORDER BY next_visit", (today,)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY next_visit").fetchall()
    if not rows:
        print("no plans")
        return
    print(f"{'id':>4}  {'next':<12} {'price':>10}  customer")
    for r in rows:
        print(f"{r['id']:>4}  {r['next_visit']:<12} {money(r['annual_price']):>10}  {r['customer']} ({r['plan_name']})")


def mark(conn, plan_id: int, kind: str) -> None:
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        sys.exit(f"no plan {plan_id}")
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if kind == "visited":
        nxt = date.fromisoformat(row["next_visit"]) + timedelta(days=row["interval_days"])
        conn.execute("UPDATE plans SET next_visit = ? WHERE id = ?", (nxt.isoformat(), plan_id))
        detail = f"next {nxt.isoformat()}"
    elif kind == "paid":
        detail = money(row["annual_price"])
    elif kind == "cancel":
        conn.execute("UPDATE plans SET status = 'cancelled' WHERE id = ?", (plan_id,))
        detail = "cancelled"
    else:
        sys.exit("unknown mark")
    conn.execute(
        "INSERT INTO events (plan_id, kind, detail, at) VALUES (?, ?, ?, ?)",
        (plan_id, kind, detail, now),
    )
    conn.commit()
    print(f"plan #{plan_id} {kind}: {detail}")


def export_chase(conn, dest: Path) -> None:
    today = date.today().isoformat()
    rows = conn.execute(
        "SELECT * FROM plans WHERE status = 'active' AND next_visit <= ? ORDER BY next_visit",
        (today,),
    ).fetchall()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["customer", "phone", "email", "amount", "due", "memo", "source"])
        for r in rows:
            w.writerow([
                r["customer"], r["phone"], r["email"], f"{r['annual_price']:.2f}",
                r["next_visit"], f"{r['plan_name']} visit due", "planclose",
            ])
    print(f"wrote {len(rows)} chase rows to {dest}")


def render(conn, plan_id: int, dest: Path) -> None:
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        sys.exit(f"no plan {plan_id}")
    spec = PLANS[row["plan_code"]]
    payload = {
        "app": APP, "version": VERSION, "plan_id": row["id"],
        "customer": row["customer"], "plan": row["plan_name"],
        "annual_price": row["annual_price"], "started_on": row["started_on"],
        "next_visit": row["next_visit"], "source_job": row["source_job"],
    }
    digest = checksum(payload)
    html = f"""<!DOCTYPE html>
<html lang=\"en\"><head><meta charset=\"utf-8\"/><title>PlanClose agreement #{row['id']}</title>
<style>body{{font-family:Georgia,serif;max-width:720px;margin:40px auto;color:#1c1917}} h1{{font-size:28px}} .muted{{color:#57534e}} table{{width:100%;border-collapse:collapse;margin:24px 0}} td{{padding:8px 0;border-bottom:1px solid #e7e5e4}} td:first-child{{width:180px;color:#57534e}} .line{{border-top:1px solid #1c1917;width:240px;margin-top:48px;padding-top:6px;font-size:13px;display:inline-block;margin-right:32px}} footer{{margin-top:36px;font-size:12px;color:#78716c}}</style></head>
<body>
<p class=\"muted\">Operator Pages · PlanClose {VERSION}</p>
<h1>{row['plan_name']}</h1>
<p>Maintenance agreement for {row['customer']}.</p>
<table>
<tr><td>Customer</td><td>{row['customer']}</td></tr>
<tr><td>Address</td><td>{row['address'] or '—'}</td></tr>
<tr><td>Phone</td><td>{row['phone'] or '—'}</td></tr>
<tr><td>Email</td><td>{row['email'] or '—'}</td></tr>
<tr><td>Trade</td><td>{row['trade']}</td></tr>
<tr><td>Annual price</td><td>{money(row['annual_price'])}</td></tr>
<tr><td>Started</td><td>{row['started_on']}</td></tr>
<tr><td>Next visit</td><td>{row['next_visit']}</td></tr>
<tr><td>Source job</td><td>{row['source_job'] or '—'}</td></tr>
<tr><td>Includes</td><td>{spec['includes']}</td></tr>
</table>
<p>Customer agrees to the annual price above, billed at the first visit of each term. Either party may cancel in writing before the next scheduled visit. Unused visits are not refunded. Materials and work outside the included scope are quoted separately.</p>
<div class=\"line\">Customer signature / date</div>
<div class=\"line\">Operator signature / date</div>
<footer>Checksum (not a signature): {digest}<br/>This receipt is a local SHA-256 of the plan fields. It is not a QuantumGuard Ed25519 seal.</footer>
</body></html>
"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html)
    print(f"wrote {dest}")
    print(f"checksum {digest}")


def catalog() -> None:
    for code, spec in PLANS.items():
        print(f"{code:18} {money(spec['price']):>10}  {spec['visits_per_year']} visits/yr  {spec['name']}")


def build_parser():
    p = argparse.ArgumentParser(prog="planclose", description="Offline maintenance-plan closer")
    p.add_argument("--root", default=".", help="folder for planclose.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog", help="list sellable plan codes")
    a = sub.add_parser("open", help="open a plan for a customer")
    a.add_argument("--customer", required=True)
    a.add_argument("--plan", required=True, choices=sorted(PLANS))
    a.add_argument("--phone")
    a.add_argument("--email")
    a.add_argument("--address")
    a.add_argument("--job", help="FieldQuote / FieldClose job id")
    a.add_argument("--start", help="YYYY-MM-DD")
    a.add_argument("--notes")
    sub.add_parser("list", help="list active plans")
    sub.add_parser("due", help="list visits due today or earlier")
    m = sub.add_parser("mark", help="record visited, paid, or cancel")
    m.add_argument("plan_id", type=int)
    m.add_argument("kind", choices=["visited", "paid", "cancel"])
    e = sub.add_parser("export", help="write Chaser-ready CSV of due plans")
    e.add_argument("--out", default="chase.csv")
    r = sub.add_parser("render", help="write a printable agreement")
    r.add_argument("plan_id", type=int)
    r.add_argument("--out", default="")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    if args.cmd == "catalog":
        catalog()
        return 0
    conn = connect(root)
    if args.cmd == "open":
        add_plan(conn, args)
    elif args.cmd == "list":
        list_plans(conn, False)
    elif args.cmd == "due":
        list_plans(conn, True)
    elif args.cmd == "mark":
        mark(conn, args.plan_id, args.kind)
    elif args.cmd == "export":
        export_chase(conn, Path(args.out))
    elif args.cmd == "render":
        out = Path(args.out) if args.out else Path(f"agreement-{args.plan_id}.html")
        render(conn, args.plan_id, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
