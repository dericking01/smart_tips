# Smart Health Tips

## Start

docker compose up --build

## API

http://localhost:8000

## Queue flow & deployment

- Start services:

```bash
docker compose up -d --build
```

- Scheduler (`api` service) enqueues AI jobs to `ai_generation_queue`.
- AI workers (`ai-worker`) process profiles, call the classifier and generator, persist logs, and enqueue SMS sends to `sms_dispatch_queue` as retry tasks.
- SMS workers (`sms-worker`) and `retry-worker` process send tasks. Retries for port-down scenarios are scheduled into `retry_queue`.

Notes:
- SMS send attempts are rate-limited to `SMS_TPS` (default 200) per configured SMS port using Redis counters. Configure `SMS_TPS` in `.env` to change throughput.
- Apply DB schema before running:

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f sql/init_schema.sql
```

Logs are written to `logs/app.log` in JSON format for auditing AI prompts, outputs, validation failures, retries, and send attempts.