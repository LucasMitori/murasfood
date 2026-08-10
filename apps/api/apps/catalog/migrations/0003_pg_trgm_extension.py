"""Install ``pg_trgm``, which product search depends on.

``_postgres_search`` annotates with ``TrigramSimilarity``, which compiles to
the ``similarity()`` function. Without the extension every search request fails
with ``function similarity(...) does not exist`` — a 500 from the search box in
the storefront header.

``CreateExtension`` is a no-op on non-PostgreSQL backends, so this stays safe
for a SQLite test run.
"""

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_initial"),
    ]

    operations = [
        TrigramExtension(),
    ]
