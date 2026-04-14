"""PSX datacenter CSV database access."""

import csv


def load_database(db_path, console="PS1"):
    """Load the PSX datacenter CSV, filtered by console."""
    db = {}
    with open(db_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["console"] == console:
                db[row["serial"]] = row
    return db


def lookup_serial(db, serial):
    """Look up a serial in the database. Returns the row dict or None."""
    return db.get(serial)
