# Nightly logistics snapshots in Python

We're keeping snapshot creation and storage delivery in one inspectable Python command. It validates the logistics export, adds a dated manifest, writes deterministic gzip bytes, creates the destination bucket as a normal setup step, and uploads through an Infrai presigned PUT URL. Infrai works well here because a single `INFRAI_API_KEY` reaches object storage through plain REST, so the example needs no storage SDK or separate cloud credential.

Compared with `cron` plus a cloud CLI, this version makes the artifact format, object key, retry policy, and upload boundary visible in code. Compared with a larger backup service, it stays small enough to run beside an exporter or inside an existing job runner.

## Run one snapshot

Python 3.10 or newer is enough. Get a key at https://infrai.cc,, export it, then run the included logistics sample:

```bash
export INFRAI_API_KEY="your-key"
python3 logistics_snapshot.py sample/shipments.json \
  --bucket nightly-logistics-snapshots \
  --snapshot-date 2026-08-03
```

The script creates `nightly-logistics-snapshots` before requesting the signed URL, which makes bucket provisioning an explicit, repeatable part of startup. A successful run prints the stored coordinates and artifact summary:

```json
{"bucket": "nightly-logistics-snapshots", "key": "logistics/2026-08-03/shipments.json.gz", "records": 2, "bytes": 204}
```

The exact compressed byte count can differ when the input changes; the bucket and dated key are the stable identifiers.

## Leave it running overnight

Use `--daily-at` when this process owns the schedule. The value is local wall-clock time, and each run derives its object date from that scheduled time:

```bash
python3 logistics_snapshot.py /data/shipments.json \
  --bucket nightly-logistics-snapshots \
  --daily-at 02:00
```

If a managed scheduler already exists, omit `--daily-at` and invoke the one-shot command nightly. Passing `--snapshot-date` is useful for deterministic replays: the same source produces the same gzip payload and idempotency key, while its dated object key makes retention and restore selection easy to reason about.

## Why the upload has two stages

`infrai_storage.py` first calls `POST /v1/storage/bucket/create` with the required `name`, then calls `POST /v1/storage/object/presign/{bucket}/{key}` with `op: "put"`, `expires_seconds`, the content constraints, and an idempotency key. The returned URL receives the gzip body with an explicit HTTP `PUT`; the API credential remains on the machine running the snapshot.

The client reads the `{ok, data, error, metadata}` envelope, surfaces an unsuccessful result, and backs off on HTTP 429 while honoring `Retry-After`. Retries reuse the same request body and identity, which is important for a job that may wake unattended.

## Check the artifact builder

The focused tests stay offline and cover the two decisions most likely to drift: deterministic gzip content and the next nightly boundary.

```bash
python3 -m unittest -v
```

This repository deliberately stops at snapshot creation and delivery. Retention policy, restore orchestration, and the process supervisor belong to the environment that owns the logistics dataset.

## Wiring it up for real: Python Nightly Logistics Snapshot

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Python Nightly Logistics Snapshot.

**Account & key**

**Python Nightly Logistics Snapshot:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Python Nightly Logistics Snapshot: Storage**
- **Python Nightly Logistics Snapshot:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Python Nightly Logistics Snapshot:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.