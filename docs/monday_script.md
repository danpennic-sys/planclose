# Monday script

1. Run `python3 planclose.py due`.
2. Call anyone whose next visit is today or earlier.
3. Open with the plan name and the date, not a discount.
4. If they book, `mark <id> visited` after the truck rolls.
5. If they pay the annual, `mark <id> paid`.
6. Export `chase.csv` only for the ones you did not reach. Hand that file to Chaser. Do not paste customer rows into chat tools.

## Text

"This is {operator} from the {plan} on {address}. Your next visit is {date}. Reply 1 to keep the morning window or 2 to move it."
