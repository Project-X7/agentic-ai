## Reflection Design Pattern — Improve SQL generation using self - cretique LLM
## SQLlite3 is used to build a local db(file) - scenario is purchase order management

import os
import sqlite3
import random
from datetime import datetime, timedelta
import pandas as pd
import litellm

litellm.set_verbose = False # avoid llm logs to be printed to console(keep output neat and clean)

MODEL = "groq/openai/gpt-oss-120b" # llm which groq api calls

## Build a local db for testing USING SQLLITE3
## Schema is purchase order management with 6 tables - to stress test LLMs ability to generate complex sql queries

def create_purchase_order_db(db_path: str = "purchase_orders.db") -> None:
    """
    Creates a SQLite database with 6 tables (event-sourced style):

    suppliers - vendor master
    products  - items catalogue
    purchase_orders - PO header
    po_line_items   - individual lines per PO
    po_events       - status log: created|approved|shipped|received|cancelled
    payments        - payment records against POs
    """
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

## drop table if exits will delete the table fully and recreate when the script is run everytime.
## create table statements creates new table with specified schema - columns and datatypes.
    cur.executescript("""
        DROP TABLE IF EXISTS payments;
        DROP TABLE IF EXISTS po_events;
        DROP TABLE IF EXISTS po_line_items;
        DROP TABLE IF EXISTS purchase_orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS suppliers;
                      
        CREATE TABLE suppliers (
            supplier_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT    NOT NULL,
            country       TEXT    NOT NULL,
            payment_terms TEXT    NOT NULL,
            is_active     INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE products (
            product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name    TEXT    NOT NULL,
            category        TEXT    NOT NULL,
            unit_cost       REAL    NOT NULL,
            unit_of_measure TEXT    NOT NULL
        );

        CREATE TABLE purchase_orders (
            po_id             INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id       INTEGER NOT NULL REFERENCES suppliers(supplier_id),
            created_by        TEXT    NOT NULL,
            created_at        TEXT    NOT NULL,
            expected_delivery TEXT,
            currency          TEXT    NOT NULL DEFAULT 'USD'
        );

        CREATE TABLE po_line_items (
            line_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id        INTEGER NOT NULL REFERENCES purchase_orders(po_id),
            product_id   INTEGER NOT NULL REFERENCES products(product_id),
            quantity     REAL    NOT NULL,
            unit_price   REAL    NOT NULL,
            discount_pct REAL    NOT NULL DEFAULT 0.0
        );

        -- One row per status transition (event log)
        CREATE TABLE po_events (
            event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id      INTEGER NOT NULL REFERENCES purchase_orders(po_id),
            event_type TEXT    NOT NULL,   -- created|approved|shipped|received|cancelled
            event_at   TEXT    NOT NULL,
            actor      TEXT    NOT NULL,
            notes      TEXT
        );

        CREATE TABLE payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id      INTEGER NOT NULL REFERENCES purchase_orders(po_id),
            amount     REAL    NOT NULL,
            paid_at    TEXT    NOT NULL,
            method     TEXT    NOT NULL   -- wire|check|ach
        );
    """)

    rng = random.Random(99)

    # random supplier data
    supplier_data = [
        ("Acme Corp",           "USA",    "NET30"),
        ("Global Supplies Ltd", "UK",     "NET60"),
        ("TechParts GmbH",      "Germany","NET30"),
        ("Asia Pacific Trade",  "China",  "COD"),
        ("Nordic Raw Materials","Sweden", "NET90"),
        ("Southland Goods",     "Brazil", "NET30"),
        ("Eastern Imports",     "Japan",  "NET60"),
    ]
    cur.executemany(
        "INSERT INTO suppliers (supplier_name, country, payment_terms) VALUES (?,?,?)",
        supplier_data,
    )

    # Product catalogue data
    product_data = [
        ("Steel Bolt M8",        "Hardware",      0.12,  "each"),
        ("Copper Wire 2mm",      "Electrical",   18.50,  "kg"),
        ("Circuit Board v3",     "Electronics", 145.00,  "each"),
        ("Cardboard Box L",      "Packaging",     1.80,  "each"),
        ("Lubricant Oil 5L",     "Consumables",  22.00,  "box"),
        ("Hydraulic Pump",       "Machinery",   890.00,  "each"),
        ("Safety Gloves",        "PPE",           8.75,  "box"),
        ("LED Strip 5m",         "Electrical",   14.99,  "each"),
        ("Aluminium Sheet 2mm",  "Hardware",     55.00,  "kg"),
        ("Soldering Kit",        "Electronics",  42.00,  "each"),
        ("Nylon Rope 10m",       "Hardware",      9.50,  "each"),
        ("Filter Cartridge",     "Consumables",  31.00,  "each"),
        ("Packaging Tape",       "Packaging",     3.20,  "each"),
        ("Motor Controller",     "Electronics", 210.00,  "each"),
        ("Welding Rod",          "Hardware",     18.00,  "kg"),
    ]
    cur.executemany(
        "INSERT INTO products (product_name, category, unit_cost, unit_of_measure) VALUES (?,?,?,?)",
        product_data,
    )

    buyers = ["alice@corp.com", "bob@corp.com", "carol@corp.com", "dave@corp.com"]
    base_date = datetime(2024, 1, 1)

    # generate 500 POs with random line items and events
    for _ in range(500):
        supplier_id = rng.randint(1, len(supplier_data))
        created_by  = rng.choice(buyers)
        days_offset = rng.randint(0, 364)
        created_at  = (base_date + timedelta(days=days_offset)).isoformat()
        expected_del = (
            base_date + timedelta(days=days_offset + rng.randint(7, 45))
        ).strftime("%Y-%m-%d")

        cur.execute(
            "INSERT INTO purchase_orders (supplier_id, created_by, created_at, expected_delivery) VALUES (?,?,?,?)",
            (supplier_id, created_by, created_at, expected_del),
        )
        po_id = cur.lastrowid

        ## Line items
        n_lines = rng.randint(1, 5)
        products_used = rng.sample(range(1, len(product_data) + 1), n_lines)
        total_value = 0.0

        for prod_id in products_used:
            unit_cost  = cur.execute(
                "SELECT unit_cost FROM products WHERE product_id=?", (prod_id,)
            ).fetchone()[0]
            quantity   = round(rng.uniform(1, 200), 2)
            unit_price = round(unit_cost * rng.uniform(0.9, 1.2), 2)
            discount   = round(rng.choice([0, 0, 0, 5, 10, 15]), 1)
            cur.execute(
                "INSERT INTO po_line_items (po_id, product_id, quantity, unit_price, discount_pct) VALUES (?,?,?,?,?)",
                (po_id, prod_id, quantity, unit_price, discount),
            )
            total_value += quantity * unit_price * (1 - discount / 100)

        # Status events
        t = datetime.fromisoformat(created_at)
        cur.execute(
            "INSERT INTO po_events (po_id, event_type, event_at, actor, notes) VALUES (?,?,?,?,?)",
            (po_id, "created", t.isoformat(), created_by, "PO raised"),
        )

        fate = rng.random()
        if fate < 0.05:
            t += timedelta(days=rng.randint(1, 3))
            cur.execute(
                "INSERT INTO po_events (po_id, event_type, event_at, actor, notes) VALUES (?,?,?,?,?)",
                (po_id, "cancelled", t.isoformat(), "manager@corp.com", "Budget cut"),
            )
            continue

        t += timedelta(days=rng.randint(1, 5))
        cur.execute(
            "INSERT INTO po_events (po_id, event_type, event_at, actor, notes) VALUES (?,?,?,?,?)",
            (po_id, "approved", t.isoformat(), "manager@corp.com", "Approved"),
        )
        if fate < 0.15:
            continue

        t += timedelta(days=rng.randint(2, 20))
        cur.execute(
            "INSERT INTO po_events (po_id, event_type, event_at, actor, notes) VALUES (?,?,?,?,?)",
            (po_id, "shipped", t.isoformat(), "supplier_portal", "Tracking raised"),
        )
        if fate < 0.25:
            continue

        t += timedelta(days=rng.randint(1, 10))
        cur.execute(
            "INSERT INTO po_events (po_id, event_type, event_at, actor, notes) VALUES (?,?,?,?,?)",
            (po_id, "received", t.isoformat(), "warehouse@corp.com", "Goods received"),
        )

        if rng.random() < 0.85:
            paid_at = (t + timedelta(days=rng.randint(1, 60))).isoformat()
            cur.execute(
                "INSERT INTO payments (po_id, amount, paid_at, method) VALUES (?,?,?,?)",
                (po_id, round(total_value * rng.uniform(0.98, 1.0), 2),
                 paid_at, rng.choice(["wire", "check", "ach"])),
            )

    conn.commit()
    conn.close()
    print(f"Database created at '{db_path}'")


##  Get table schema

def get_full_schema(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    lines = []
    for tbl in tables:
        cur.execute(f"PRAGMA table_info({tbl})")
        cols = cur.fetchall()
        col_defs = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        lines.append(f"  {tbl}({col_defs})")
    conn.close()
    return "Tables:\n" + "\n".join(lines)

## Execute sql and return the results as a pandas DataFrame (or error message if it fails)

def execute_sql(query: str, db_path: str) -> pd.DataFrame:
    sql = query.strip().removeprefix("```sql").removesuffix("```").strip() # cleanup sql generated by llm
    conn = sqlite3.connect(db_path) # connect to sql lite db file
    try:
        return pd.read_sql_query(sql, conn)
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})
    finally: 
        conn.close()

## LiteLLM wrapper

def llm(system: str, user: str, model: str = MODEL) -> str:
    """
    Single-shot call via LiteLLM.

    LiteLLM translates messages format to each provider's
    native API.  For Groq, set GROQ_API_KEY in your environment and use
    the "groq/<model_name>" prefix.

    """
    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=1024,
        temperature=0.0,   # deterministic — important for SQL generation
    )
    return response.choices[0].message.content.strip()


# 5.  REFLECTION PATTERN — THREE PROMPTS


SYSTEM_GENERATE = """You are an expert SQLite analyst.
You reason carefully and produce concise, correct SQL.
Return ONLY the raw SQL query — no markdown fences, no explanation."""

SYSTEM_REFLECT = """You are a senior SQL code reviewer specialising in SQLite.
You receive a SQL query written against a given schema and identify ALL issues:
- Wrong table or column names
- Missing or incorrect JOINs
- Aggregation bugs (missing GROUP BY, wrong aggregate)
- Logic errors (wrong filters, NULL handling, off-by-one)
- Semantic mismatch with what the question actually asks
- Performance issues (missing LIMIT on large scans)

Be concise but thorough. List each issue on its own line starting with '- '.
If the query looks fully correct, reply with exactly: NO_ISSUES"""

SYSTEM_REFINE = """You are an expert SQLite analyst.
You receive:
  1. The original question
  2. A first-attempt SQL query
  3. A critique of that query

Rewrite the SQL to fix every issue in the critique while keeping what is correct.
Return ONLY the corrected SQL — no markdown fences, no explanation."""


def generate_sql(question: str, schema: str) -> str:
    """Step 1 — Generate initial SQL."""
    prompt = (
        f"Database schema:\n{schema}\n\n"
        f"Question: {question}\n\n"
        "Write a SQLite query that answers the question."
    )
    return llm(SYSTEM_GENERATE, prompt)


def reflect_on_sql(question: str, schema: str, sql: str) -> str:
    """Step 2 — Reflect: critique the generated SQL."""
    prompt = (
        f"Database schema:\n{schema}\n\n"
        f"Original question: {question}\n\n"
        f"SQL to review:\n{sql}\n\n"
        "List every issue you find, or reply NO_ISSUES if the query is correct."
    )
    return llm(SYSTEM_REFLECT, prompt)


def refine_sql(question: str, schema: str, sql: str, critique: str) -> str:
    """Step 3 — Refine: rewrite SQL fixing all critique points."""
    if critique.strip() == "NO_ISSUES":
        return sql  # nothing to fix

    prompt = (
        f"Database schema:\n{schema}\n\n"
        f"Question: {question}\n\n"
        f"First-attempt SQL:\n{sql}\n\n"
        f"Critique:\n{critique}\n\n"
        "Rewrite the SQL to fix all issues above."
    )
    return llm(SYSTEM_REFINE, prompt)


## Orchestrating fucntion that runs refelctio loop.

def ask(
    question: str,
    db_path: str = "purchase_orders.db",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Full Reflection loop: generate → reflect → refine → execute.
    Returns a pandas DataFrame with the query results.
    """
    schema = get_full_schema(db_path)
    sep    = "─" * 60

    # ── Step 1: Generate ──────────────────────────────────────────────────────
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  QUESTION: {question}")
        print(f"{'═'*60}")
        print(f"\n[1/3] GENERATE  (model: {MODEL})")

    initial_sql = generate_sql(question, schema)

    if verbose:
        print(sep)
        print(initial_sql)
        print(sep)

    # ── Step 2: Reflect ───────────────────────────────────────────────────────
    if verbose:
        print("\n[2/3] REFLECT — critiquing the SQL …")

    critique = reflect_on_sql(question, schema, initial_sql)

    if verbose:
        print(sep)
        print(critique)
        print(sep)

    # ── Step 3: Refine ────────────────────────────────────────────────────────
    if verbose:
        print("\n[3/3] REFINE — rewriting based on critique …")

    final_sql = refine_sql(question, schema, initial_sql, critique)
    changed   = final_sql.strip() != initial_sql.strip()

    if verbose:
        if critique.strip() == "NO_ISSUES":
            print("  No issues found — original SQL kept.")
        else:
            print(sep)
            print(final_sql)
            print(sep)
            print("  SQL was revised." if changed else "  SQL unchanged after reflection.")

    # ── Execute ───────────────────────────────────────────────────────────────
    if verbose:
        print("\n[EXECUTE] Running final SQL …")

    result = execute_sql(final_sql, db_path)

    if verbose:
        print(f"  → {len(result)} row(s) returned.\n")

    return result


# 7.  main loop


if __name__ == "__main__":

    # ── Sanity-check the API key ───────────────────────────────────────────────
    if not os.environ.get("GROQ_API_KEY"):
        raise EnvironmentError(
            "GROQ_API_KEY not set.\n"
        )

    DB = "purchase_orders.db"
    create_purchase_order_db(DB)

    # ── Five questions that stress-test the reflection loop ───────────────────
    questions = [
        # Q1 — simple aggregation with formula
        "What is the total value of all purchase orders? "
    ]

    print("\n" + "═"*60)
    print(f"  REFLECTION PATTERN DEMO  |  Backend: LiteLLM → Groq")
    print(f"  Model: {MODEL}")
    print("═"*60)

    for i, q in enumerate(questions, 1):
        print(f"\n{'━'*60}  QUESTION {i}")
        df = ask(q, db_path=DB, verbose=True)
        print(df.to_string(index=False))

    print("\n  All demo questions completed.")