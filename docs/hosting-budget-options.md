# PlayBack90 Hosting Budget Options

This document summarizes the hosting budget options discussed for deploying PlayBack90 while keeping the full local `Data` database off hosted infrastructure.

## Budget Assumptions

These estimates assume:

- The full `Data` database remains local.
- Cloudflare R2 continues to store hosted parquet match/season files.
- Anthropic usage is removed or disabled.
- Railway Postgres is not deployed initially.
- Railway Redis is not deployed initially.
- Live scraping workers and pipeline cron jobs are not hosted initially.
- Clerk Free is used for private beta authentication.
- Sentry Free is used or monitoring is limited to platform logs initially.
- PostHog is skipped initially or used on its free tier.
- Traffic is small private beta traffic, not public production traffic.

## Summary

| Option | Estimated Monthly Cost | Practical Budget Cap | Operational Complexity |
|---|---:|---:|---|
| Vercel Free + Railway API only | `$10-$35` | `$40-$50` | Low |
| AWS Lightsail VPS | `$5-$15` | `$20` | Medium-high |
| AWS Amplify + App Runner | `$15-$60` | `$60-$75` | Medium |
| Full Railway staging stack | `$35-$85` | `$75-$100` | Low |

## Recommended Low-Cost Option

Use:

```text
Vercel Free: Next.js web app
Railway Hobby: FastAPI API only
Cloudflare R2: parquet storage
Clerk Free: authentication
Sentry Free or Railway logs: monitoring
No hosted Postgres initially
No hosted Redis initially
No hosted Data database
```

Estimated monthly cost:

```text
$10-$35/month
```

Recommended budget cap:

```text
$40-$50/month
```

This is the best balance between cost and operational simplicity. Vercel hosts the frontend for free, and Railway only runs the heavier FastAPI service.

## AWS Option 1: Lightsail VPS

Use:

```text
AWS Lightsail VPS: API, and optionally the web app
Cloudflare R2: parquet storage
Clerk Free: authentication
Sentry Free or server logs: monitoring
No RDS
No ElastiCache
No hosted Data database
```

Estimated monthly cost:

```text
$5-$15/month
```

Recommended budget cap:

```text
$20/month
```

Likely distribution:

| Item | Expected Cost |
|---|---:|
| Lightsail instance | `$5-$10` |
| Extra storage/transfer | `$0-$5` |
| Cloudflare R2 | `$0-$5` |
| Clerk | `$0` |
| Sentry | `$0` |

This is the cheapest option, but it requires managing the server, Docker, SSL, deploys, restarts, updates, and logs.

## AWS Option 2: Amplify + App Runner

Use:

```text
AWS Amplify: Next.js frontend
AWS App Runner: FastAPI API container
Cloudflare R2: parquet storage
Clerk Free: authentication
Sentry Free: monitoring
No RDS
No ElastiCache
No hosted Data database
```

Estimated monthly cost:

```text
$15-$60/month
```

Recommended budget cap:

```text
$60-$75/month
```

Likely distribution:

| Item | Expected Cost |
|---|---:|
| Amplify frontend | `$0-$10` |
| App Runner API | `$15-$45` |
| Cloudflare R2 | `$0-$5` |
| Clerk | `$0` |
| Sentry | `$0` |

This is more managed than Lightsail, but usually not cheaper than Vercel Free plus Railway API only.

## Full Railway Option

Use:

```text
Railway: Next.js web service
Railway: FastAPI API service
Railway Postgres
Railway Redis
Cloudflare R2
Clerk Free
Sentry Free
```

Estimated monthly cost:

```text
$35-$85/month
```

Recommended budget cap:

```text
$75-$100/month
```

Likely distribution:

| Item | Expected Cost |
|---|---:|
| Railway API | `$12-$30` |
| Railway web | `$5-$15` |
| Railway Postgres | `$5-$15` |
| Railway Redis | `$2-$8` |
| Railway egress | `$1-$8` |
| Cloudflare R2 | `$0-$5` |
| Clerk | `$0` |
| Sentry | `$0` |

This is operationally simple but costs more because multiple services run continuously.

## Services That Should Stay Free Initially

| Service | Initial Plan |
|---|---|
| Clerk | Free |
| Sentry | Free |
| PostHog | Free or skipped initially |
| Better Stack | Free or skipped initially |
| football-data.org | Free unless higher limits are needed |

## Cost Reduction Decisions

To keep hosting costs low:

1. Keep the full `Data` database local.
2. Do not deploy Postgres until durable hosted state is required.
3. Do not deploy Redis until hosted queues/cache are required.
4. Do not host live scraping workers initially.
5. Do not host pipeline cron jobs initially.
6. Keep Cloudflare R2 as the object storage layer.
7. Host the frontend on a free frontend platform if possible.
8. Slim the API Docker image so it does not copy the full `Data` folder.
9. Remove or disable Anthropic-related code and dependencies before production deployment.

## Current Recommendation

Start with:

```text
Vercel Free + Railway API only
```

Expected monthly cost:

```text
$10-$35/month
```

Use AWS Lightsail only if minimizing cost is more important than convenience and you are comfortable managing the server directly.

