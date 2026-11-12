# Auditlog archives

`manage.py archive_auditlog` writes one file per month to the `auditlog_archive`
storage (`var/auditlog_archive/` or `$AUDITLOG_ARCHIVE_ROOT`):
`auditlog/YYYY-MM.jsonl.gz`. Each file is gzipped JSON Lines, one log entry per line.
See `entry_to_record` in `archive.py` for the fields.

Don't unpack the files. Read them as streams instead:

```bash
gzip -dc auditlog/2023-07.jsonl.gz | head
gzip -dc auditlog/2023-07.jsonl.gz | jq -c 'select(.m == 4182)'
gzip -dc auditlog/*.jsonl.gz | wc -l
```

```python
import gzip, json

with gzip.open("auditlog/2023-07.jsonl.gz", "rt") as fh:
    for line in fh:
        record = json.loads(line)
```
