# PlanClose

Offline maintenance-plan closer for one-truck trades. Operator Pages.

FieldQuote prices the job. FieldClose prints the invoice and a checksum receipt. PlanClose is the next sale: a recurring visit plan, a paper agreement, and a chase file Chaser can import.

It does **not** sign evidence. A PlanClose checksum is SHA-256 of the plan fields. QuantumGuard remains the only verifier.

## Sell

Add-on to the FieldQuote pack. Do not replace the $349 / $1,497 sheet.

| Tier | Price | What the buyer gets |
|------|------:|---------------------|
| Plan add-on | $199 | This CLI, three plan codes, agreement HTML, Chaser CSV |
| Command bundle | included in $1,497 | Add-on plus the scripts in `docs/` |

## Run

Python 3.9+. No install. No network.

```bash
python3 planclose.py catalog
python3 planclose.py open --customer "Ada Nguyen" --plan hvac-season --phone "573-555-0142" --job FQ-1044
python3 planclose.py list
python3 planclose.py render 1 --out agreement-1.html
python3 planclose.py due
python3 planclose.py export --out chase.csv
python3 planclose.py mark 1 visited
```

Data stays in `planclose.db` in `--root` (default: current folder).

## Honest limits

- Local only. No Stripe, no email send, no accounting sync.
- Three plan codes, fixed prices in the script. Edit `PLANS` before you sell a custom menu.
- Checksum, not a signature. Do not market this as QuantumGuard.
- Chase CSV is an import file. Chaser still has to send the reminder.
