# Python Coding Guidelines

## Core Principles

1. **Prioritize readability and performance**
2. **Use built-in functions before custom implementations**
3. **Vectorize operations when working with data**
4. **Handle exceptions specifically, not broadly**
5. **Minimize branching and conditionals**
6. **Use explicit, brief, and formal naming — no abbreviations**

---

## 1. Naming Conventions

### ⚠️ CRITICAL: No abbreviations in variable, parameter, or annotation names

**Abbreviations reduce readability and introduce inconsistency. Use full, explicit names.**

### ✅ DO: Use explicit, full names

```python
# Good - Clear, formal naming
for customer_assignment in assignments:
    process_assignment(customer_assignment)

# Good - Full names in annotations
subquery = (
    Model.objects.filter(...)
    .annotate(count=Count("id"))
    .values("count")
)

# Good - Loop variables are explicit
for service in services:
    price = service.price * quantity
    total += price
```

### ❌ DON'T: Use abbreviations

```python
# Bad - Abbreviations reduce clarity
for ca in assignments:          # ❌ What is 'ca'?
    process_assignment(ca)

# Bad - Short form annotations
.annotate(cnt=Count("id"))      # ❌ 'cnt' vs 'count'
.values("cnt")

# Bad - Single-letter or short loop variables
for s in services:              # ❌ What is 's'?
    price = s.price * qty       # ❌ What is 'qty'?
    total += price

# Bad - Config/temp variable abbreviations
cfg = load_config()             # ❌ Use 'config'
tmp_results = []                # ❌ Use 'temporary_results' or 'processing_results'
asg = Assignment(...)           # ❌ Use 'assignment'
```

### Common abbreviations to AVOID:

- `cnt` → `count`
- `asg` / `asn` → `assignment`
- `pkg` → `package`
- `cfg` → `config`
- `tmp` → Use descriptive name (`processing_results`, `temporary_buffer`)
- `qty` → `quantity`
- `num` → `number`
- `val` → `value`
- `i`, `j`, `k` in loops → Use `index`, `item`, or descriptive names
- `s`, `u`, `r` → Use full names (`service`, `user`, `result`)

---

## 2. Vectorization & Performance

### ✅ DO: Use vectorized operations

```python
# Good - Vectorized
df['new_col'] = df['col'].map(mapping_dict)
df['is_valid'] = df['status'].isin(['active', 'pending'])
result = df[df['age'] > 18].copy()

# Good - NumPy vectorization
ids = np.array([str(uuid.uuid4()) for _ in range(n)])
```

### ❌ DON'T: Loop over DataFrames

```python
# Bad - Loops
for idx, row in df.iterrows():
    df.at[idx, 'new_col'] = mapping_dict.get(row['col'])

# Bad - List comprehension where vectorization is available
df['is_valid'] = [x in ['active', 'pending'] for x in df['status']]
```

---

## 2. Exception Handling

### ⚠️ CRITICAL: Use exceptions ONLY when absolutely needed

**Exceptions are for exceptional cases, not normal control flow.**

### ✅ DO: Use exceptions for truly exceptional situations

```python
# Good - Exception for genuine error condition
def load_config(file_path: Path) -> dict:
    """Load config file. Raises FileNotFoundError if missing."""
    if not file_path.exists():
        raise FileNotFoundError(f"Config not found: {file_path}")
    return json.load(file_path.open())


# Good - Specific exception with meaningful handling
try:
    config = load_config(config_path)
except FileNotFoundError as e:
    logger.warning(f"{e}. Using defaults.")
    config = get_default_config()


# Good - No try/except when not needed
def calculate_total(items: List[Item]) -> float:
    return sum(item.price for item in items)  # No exception needed
```

### ❌ DON'T: Wrap everything in try/except or use for control flow

```python
# Bad - Unnecessary try/except (no exception expected)
try:
    total = sum(prices)
    return total
except Exception as e:
    logger.error(e)

# Bad - Using exceptions for control flow
try:
    value = my_dict['key']
except KeyError:
    value = default_value

# Good alternative - EAFP only when appropriate
value = my_dict.get('key', default_value)

# Bad - Overly defensive
try:
    try:
        result = process_data(data)
    except ValueError:
        result = None
except Exception:
    result = None
```

### Rule: Don't use try/except "just in case"

```python
# Bad - Wrapping everything unnecessarily
def simple_calculation(a: int, b: int) -> int:
    try:
        return a + b
    except Exception as e:
        logger.error(e)
        return 0


# Good - No exception handling needed
def simple_calculation(a: int, b: int) -> int:
    return a + b
```

### ✅ DO: Catch specific exceptions only (when needed)

```python
# Good - Specific exceptions for expected failure modes
try:
    data = json.load(file)
except (json.JSONDecodeError, FileNotFoundError) as e:
    logger.error(f"Failed to load config: {e}")
    return default_config
```

### ❌ DON'T: Catch broadly or re-raise pointlessly

```python
# Bad - Broad exception
try:
    process_data()
except Exception as e:
    logger.error(e)

# Bad - Pointless catch-and-re-raise
try:
    process_data()
except ValueError as e:
    logger.error(f"Error: {e}")
    raise  # Why catch if you're just going to re-raise?
```

### Rule: If you're only logging and re-raising, don't catch at all

```python
# Good - Let it raise naturally
def process_data():
    return json.load(file)  # FileNotFoundError will bubble up
```

### When to use exceptions:

✅ File I/O operations (FileNotFoundError, PermissionError)
✅ Network requests (ConnectionError, Timeout)
✅ Parsing external data (json.JSONDecodeError, ValueError)
✅ Database operations (IntegrityError, OperationalError)

### When NOT to use exceptions:

❌ Normal business logic
❌ Validation (use if/return instead)
❌ Type checking (use type hints)
❌ "Just in case" defensive programming
❌ Control flow (use if/else or dict.get())

---

## 3. Use Built-ins First

### ✅ DO: Leverage standard library

```python
# Good - Built-in functions
unique_items = set(items)
sorted_items = sorted(items, key=lambda x: x.score)
max_value = max(values)
file_exists = Path(file_path).exists()

# Good - Standard library
from collections import Counter, defaultdict
from itertools import groupby, chain
from functools import lru_cache
```

### ❌ DON'T: Reinvent the wheel

```python
# Bad - Custom unique implementation
unique_items = []
for item in items:
    if item not in unique_items:
        unique_items.append(item)

# Bad - Manual max finding
max_value = values[0]
for v in values:
    if v > max_value:
        max_value = v
```

---

## 4. Minimize Branching

### ✅ DO: Use vectorized conditionals and data structures

```python
# Good - Vectorized conditional
df['category'] = np.where(df['score'] > 80, 'high', 'low')

# Good - Dictionary dispatch instead of if/elif
handlers = {
    'create': create_handler,
    'update': update_handler,
    'delete': delete_handler
}
result = handlers[action](data)

# Good - Boolean indexing
valid_records = df[df['is_valid'] & (df['age'] > 18)]
```

### ❌ DON'T: Chain if/elif or nested conditionals

```python
# Bad - Chain of if/elif
if action == 'create':
    result = create_handler(data)
elif action == 'update':
    result = update_handler(data)
elif action == 'delete':
    result = delete_handler(data)

# Bad - Nested conditionals
for item in items:
    if item.status == 'active':
        if item.age > 18:
            if item.verified:
                process(item)
```

---

## 5. Data Processing

### ✅ DO: Use pandas/numpy efficiently

```python
# Good - Batch operations
df['normalized'] = (df['value'] - df['value'].mean()) / df['value'].std()

# Good - Efficient I/O
df = pd.read_csv(file, usecols=['id', 'name'], dtype={'id': 'str'}, engine='pyarrow')
```

### ❌ DON'T: Process row-by-row or make redundant queries

```python
# Bad - Multiple queries
total_users = pd.read_sql("SELECT COUNT(*) FROM users", conn).iloc[0, 0]
total_orders = pd.read_sql("SELECT COUNT(*) FROM orders", conn).iloc[0, 0]

# Bad - Row-by-row processing
for idx, row in df.iterrows():
    df.at[idx, 'normalized'] = (row['value'] - mean) / std

# Bad - Loading unnecessary data
df = pd.read_csv(file)  # Loads all columns
df = df[['id', 'name']]  # Then filters
```

---

## 6. Function Design

### ✅ DO: Single responsibility, clear contracts

```python
# Good - Clear purpose, type hints, single responsibility
def calculate_discount(price: float, discount_pct: float) -> float:
    """Calculate discounted price.

    Args:
        price: Original price
        discount_pct: Discount percentage (0-100)

    Returns:
        Discounted price
    """
    return price * (1 - discount_pct / 100)


# Good - Return early
def get_user(user_id: str) -> Optional[User]:
    if not user_id:
        return None

    user = db.query(User).filter_by(id=user_id).first()
    return user
```

### ❌ DON'T: Do multiple things or nest deeply

```python
# Bad - Does too much
def process_user(user_id):
    user = get_user(user_id)
    orders = get_orders(user_id)
    total = calculate_total(orders)
    send_email(user.email, total)
    log_activity(user_id, 'processed')
    return total


# Bad - Deep nesting
def process_data(data):
    if data:
        if data.is_valid:
            if data.status == 'active':
                if data.user:
                    return process_user(data.user)
    return None
```

---

## 7. Memory Efficiency

### ✅ DO: Use generators and lazy evaluation

```python
# Good - Generator (memory efficient)
def process_large_file(file_path: Path):
    with open(file_path) as f:
        for line in f:
            yield process_line(line)


# Good - Generator expression
total = sum(x ** 2 for x in range(1000000))

# Good - Chunked processing
for chunk in pd.read_csv(file, chunksize=10000):
    process_chunk(chunk)
```

### ❌ DON'T: Load everything into memory

```python
# Bad - Loads entire file into memory
with open(file_path) as f:
    lines = f.readlines()  # All lines loaded
    return [process_line(line) for line in lines]

# Bad - List comprehension for large data
total = sum([x ** 2 for x in range(1000000)])  # Creates list in memory
```

---

## 8. String Operations

### ✅ DO: Use f-strings and efficient methods

```python
# Good - f-strings
message = f"User {user.name} has {len(orders)} orders"

# Good - str.join for multiple strings
result = ', '.join(items)

# Good - String methods
cleaned = text.strip().lower()
is_valid = text.startswith('prefix') and text.endswith('suffix')
```

### ❌ DON'T: Concatenate in loops or use old formatting

```python
# Bad - String concatenation in loop
result = ''
for item in items:
    result += item + ', '

# Bad - Old formatting
message = "User %s has %d orders" % (user.name, len(orders))
message = "User {} has {} orders".format(user.name, len(orders))
```

---

## 9. Imports

### ✅ DO: Import specifically and organize

```python
# Good - Specific imports
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

# Good - Absolute imports in libraries
from myproject.utils.helper import calculate_total
```

### ❌ DON'T: Import everything, use relative imports, or import inside functions

```python
# Bad - Star imports
from utils import *
from pandas import *

# Bad - Relative imports in reusable code
from ..utils import helper  # Only OK in application code, not libraries


# Bad - Import inside a function
def process_data(data):
    import json  # Move this to the top of the file
    return json.dumps(data)
```

### Rule: All imports must be at the top of the file

---

## 10. No Nested Functions

### ✅ DO: Define functions at module level

```python
# Good - Helper defined at module level
def _build_payload(record: Record) -> dict:
    return {'id': str(record.pk), 'name': record.name}


def process_record(record: Record) -> dict:
    return _build_payload(record)
```

### ❌ DON'T: Define functions inside other functions

```python
# Bad - Nested function definition
def process_record(record: Record) -> dict:
    def build_payload(r):  # Move this to module level
        return {'id': str(r.pk), 'name': r.name}

    return build_payload(record)
```

### Rule: All functions must be defined at module or class level, never inside another function

---

## 11. Django FK Access — Use `.pk`; Allow `_id` Only for `bulk_create()`

### ✅ DO: Access FK primary keys via `.pk`

```python
# Good
increment_service_cancelled_count(program_service.program.pk)
Program.objects.filter(pk=assignment.center.pk)
```

### ❌ DON'T: Use Django's auto-generated `_id` accessor in ordinary code

```python
# Bad - uses the implicit FK column accessor
increment_service_cancelled_count(program_service.program_id)
Program.objects.filter(pk=assignment.center_id)
```

This prohibition applies to ordinary assignments, reads, queryset filters,
updates, serializers, helpers, and single-object create/save paths.

### ✅ Narrow exception: Constructing objects for `bulk_create()`

Direct `<field>_id=<validated_pk>` assignment is allowed only while constructing
model instances that will be passed to `bulk_create()`:

```python
# Good - validated scalar IDs avoid hydrating related objects solely for a bulk insert
assignments = [
    AssociateCenterAssignment(
        associate=associate,
        center_id=center_data["id"],
    )
    for center_data in add_centers
]
AssociateCenterAssignment.objects.bulk_create(assignments)
```

The exception applies only when:

- the foreign-key values were already validated;
- the related objects are not otherwise needed; and
- the instances are being constructed for `bulk_create()`.

Do not broaden this exception to queryset filters, ordinary object assignment,
single-object creation, or relation access merely because Django exposes the
`<field>_id` attribute.

### Rule: Use `relation.pk` everywhere except validated FK assignment during
`bulk_create()` object construction.

---

## Intentional Instant-Search Lookups

Combining `istartswith` and `icontains` on the same field is permitted only when
the product contract explicitly requires both prefix and broader substring
discovery and an adjacent comment marks the behavior as intentional.

Although `icontains` subsumes `istartswith` for result inclusion, do not simplify
or flag an explicitly documented pair. This exception does not imply prefix
ranking or conditional fallback.

---

## 12. No Raw SQL

### ✅ DO: Use the Django ORM

```python
# Good - ORM query
users = User.objects.filter(is_active=True).select_related('profile')

# Good - Aggregations via ORM
from django.db.models import Count, Sum

stats = Order.objects.aggregate(total=Sum('amount'), count=Count('id'))

# Good - Annotations
records = Record.objects.annotate(order_count=Count('orders'))
```

### ❌ DON'T: Write raw SQL strings

```python
# Bad - Raw SQL
users = User.objects.raw("SELECT * FROM users WHERE is_active = 1")

# Bad - RawSQL expression
from django.db.models.expressions import RawSQL

qs = MyModel.objects.filter(value=RawSQL("some_col + %s", [10]))

# Bad - cursor execution
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM users")
```

### Rule: All database access must go through the Django ORM. No `raw()`, `RawSQL`, or cursor execution.

---

## 13. No Migration Generation

### ⚠️ CRITICAL: Never create Django migration files

Migration generation is owned by the user.

### ❌ DON'T:

- Do not run `makemigrations`.
- Do not create migration files manually.
- Do not edit migration files unless the user explicitly asks for a specific migration-file edit.
- Do not add migration plans that require Codex to generate migrations.

### ✅ DO:

- Change models and application code only.
- Tell the user when model changes require a migration.
- Let the user generate and review migrations.

### Rule: Codex must never create Django migrations, either manually or by command.

---

## 12. Documentation & Organization

### ✅ DO: Keep documentation organized

```python
# Good - Documentation in docs/
docs /
├── CODING_RULES.md
├── ARCHITECTURE.md
├── migration - *.md
└── README.md

# Good - Clear, descriptive filenames
docs / migration - record - id - to - uuid.md
docs / api - authentication - guide.md
```

### ❌ DON'T: Scatter documentation in root or random folders

```python
# Bad - Documentation scattered
./ CODING_RULES.md  # Should be in docs/
./ migration.md  # Should be in docs/
./ notes.txt  # Should be in docs/
random_folder / guide.md  # Should be in docs/
```

### Rule: ALL documentation goes in `docs/` folder

---

## 11. Type Hints

### ✅ DO: Use type hints for public APIs

```python
# Good - Clear type hints
def process_orders(
        orders: List[Order],
        user_id: str,
        apply_discount: bool = False
) -> Dict[str, float]:
    """Process orders and return summary statistics."""
    pass


# Good - Optional and Union
def find_user(user_id: str) -> Optional[User]:
    pass


def parse_value(value: Union[str, int]) -> float:
    pass
```

### ❌ DON'T: Skip type hints on public functions

```python
# Bad - No type hints
def process_orders(orders, user_id, apply_discount=False):
    pass
```

---

## Summary Checklist

Before committing code, verify:

- [ ] **Documentation in `docs/` folder** - All .md files belong in docs/
- [ ] **No migration generation** - Never create migration files manually and never run `makemigrations`
- [ ] **No unnecessary try/except blocks** - Only use exceptions when ABSOLUTELY needed
- [ ] **No raw SQL** - Use the Django ORM exclusively (`raw()`, `RawSQL`, and cursor execution are forbidden)
- [ ] **No imports inside functions** - All imports at the top of the file
- [ ] **No nested functions** - All functions defined at module or class level
- [ ] Used vectorized operations (pandas/numpy) instead of loops
- [ ] Caught specific exceptions only (no broad `except Exception`)
- [ ] Not catching just to re-raise
- [ ] Not using exceptions for control flow
- [ ] Used built-in functions/standard library where applicable
- [ ] Minimized if/elif chains (used dict dispatch or vectorization)
- [ ] Added type hints to public functions
- [ ] Used f-strings for formatting
- [ ] Used generators for large data processing
- [ ] Leveraged pandas/numpy efficiently (no row-by-row iteration)
- [ ] Functions have single, clear responsibilities
- [ ] Code is readable and self-documenting

---

**Remember:** Premature optimization is bad, but writing inefficient code from the start is worse. Follow these
guidelines by default, and profile before micro-optimizing.

---

## 13. Package Versions — Always Use Latest

### Rule: This project tracks the latest stable versions of all packages. Never assume a version.

When adding a new package, or referencing an existing one in code or documentation:

✅ **DO:** Check [PyPI](https://pypi.org) or the package's official release page for the current latest stable version.

✅ **DO:** Use `uv add <package>` to add packages — uv resolves and locks the latest compatible version automatically.

✅ **DO:** Use `uv sync --upgrade` to upgrade all packages to their latest compatible versions.

❌ **DON'T:** Guess version numbers from memory or training data — package versions change frequently.

❌ **DON'T:** Use `pip install` — always use `uv`. The lock file (`uv.lock`) is the single source of truth for installed versions.

❌ **DON'T:** Pin packages unnecessarily in `pyproject.toml` unless there is a specific known incompatibility — let uv resolve latest.

### Current Locked Versions (April 2026)

See `CLAUDE.md` Section 3 for the full version table. Key versions:

- **Python:** 3.14.x
- **Django:** 6.0.3
- **Django REST Framework:** 3.17.1
- **psycopg (PostgreSQL driver):** 3.3.3 (v3 API — not psycopg2)
- **pandas:** 3.0.2

### Adding a New Package

```bash
# Check latest version on PyPI first, then:
uv add package-name

# For dev-only tools:
uv add --dev package-name

# Verify the lock file updated:
git diff uv.lock
```
