# Experimentation API - Architecture Documentation

## Overview

This document covers architecture decisions, trade-offs, production considerations, and design philosophy for the Experimentation API.

---

## Architecture Decisions & Trade-offs

### 1. Technology Stack

**Chosen:** FastAPI + SQLite + SQLAlchemy

**Rationale:**
- **FastAPI**: Modern async Python framework with automatic OpenAPI docs, Pydantic validation, and excellent performance. The async-first design makes it easy to scale later.
- **SQLite**: Perfect for this challenge - zero configuration, portable, and sufficient for demonstrating the data model. The same SQLAlchemy code works with PostgreSQL/MySQL for production.
- **SQLAlchemy ORM**: Type-safe database operations, easy migrations, and database-agnostic code.

**Trade-offs:**
- SQLite has write concurrency limitations (single writer). For production, PostgreSQL is recommended.
- ORM adds overhead vs raw SQL, but provides better maintainability and safety.

### 2. Data Model Design

**Experiments and Variants (Separate Tables)**
- Allows N variants per experiment (not just A/B, but A/B/C/D...)
- Each variant has independent traffic allocation
- Variant-specific config stored as JSON for flexibility

**Events Decoupled from Experiments**
- Events are recorded by user, not by experiment
- This allows:
  - One event to count across multiple concurrent experiments
  - Post-hoc analysis on any event type
  - No need to know experiments at event recording time
- Trade-off: Results query is more complex, but much more flexible

**Assignment Idempotency**
- Database constraint: `UNIQUE(experiment_id, user_id)`
- Deterministic hash-based assignment ensures consistency even before DB write
- Trade-off: Slightly more complex assignment logic, but guarantees correctness

### 3. Assignment Algorithm

**Chosen:** Deterministic hash-based bucketing

```python
bucket = SHA256(experiment_id + user_id) % 100
```

**Why this approach:**
1. **Deterministic**: Same user always gets same variant, even if DB fails
2. **Uniform distribution**: Cryptographic hash ensures even distribution
3. **Independent of order**: Assignment doesn't depend on when user arrives
4. **Stable across restarts**: No server-side state needed

**Trade-off:** Cannot easily change traffic allocation for existing users. This is intentional - changing allocation mid-experiment is statistically problematic anyway.

### 4. Authentication Design

**Chosen:** JWT (JSON Web Token) authentication

**Implementation:**
- Users authenticate via `POST /auth/token` with username/password
- Server returns a signed JWT containing user_id, role, and expiration
- All protected endpoints validate the JWT signature and expiration
- Passwords hashed with bcrypt (secure, industry-standard)

**Key Features:**
- **Stateless**: No server-side session storage needed
- **Self-contained**: Token carries user info (no DB lookup per request)
- **Expiring**: Tokens expire after configurable time (default: 60 minutes)
- **Role-based**: Supports user/admin roles for authorization

**Configuration (via .env):**
```
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60
```

**Trade-offs:**
- JWT tokens cannot be revoked before expiration (would need a blocklist)
- User store is currently in-memory (should be moved to database for production)

**Production Evolution:**
- Move users to database table with proper persistence
- Add refresh tokens for longer sessions
- Add API key management with scopes/permissions
- Implement token revocation blocklist

### 5. Results Endpoint Philosophy

**Design Goal:** One endpoint that serves multiple stakeholders like Engineers, Data Scientists, Product Managers, Executives.


**Key Design Choices:**

1. **Query Parameters for Flexibility:**
   - `format=summary|full|metrics_only` - Control response verbosity
   - `include_time_series=true` - Enable chart data
   - `event_types=purchase,signup` - Filter to specific conversions
   - `start_date/end_date` - Custom analysis windows

2. **Event Filtering by Assignment Time:**
   - Only count events AFTER user's assignment timestamp
   - Prevents pre-experiment events from polluting results
   - Critical for accurate conversion attribution

3. **Qualitative Confidence Levels:**
   - Returns "low", "medium", "high", "significant"
   - Helps non-statisticians understand result reliability
   - Production version would include p-values and confidence intervals

4. **Export Endpoint for External Analysis:**
   - Raw denormalized data for Jupyter/BI tools
   - Enables custom analysis beyond built-in metrics

---

## Production Scaling Consideration - Architecture (AWS)

The backend is deployed to **AWS EC2** with single instance 

**1. Current Deployment**
- Single EC2 instance, SQLite (dev) → PostgreSQL (prod), no auto-scaling yet

**2. Database Layer**
- **Problem:** SQLite can't handle concurrent writes; analytics queries slow down the main DB
- **Solution:** RDS PostgreSQL with read replicas — primary handles writes, replicas handle `/results` queries, connection pooling for efficiency

**3. Caching Layer (Reverse Proxy)**
- **Problem:** Repeated API calls hit the server unnecessarily, increasing latency and EC2 load
- **Solution:** Cache at CloudFront/ALB level (not application) — responses reach users faster without hitting the server. TTLs: 60s for experiments, 30s for results, no cache for assignments (idempotency) and writes

**4. API Scaling (Load Balancer)**
- **Problem:** Single EC2 instance can't handle traffic spikes or provide high availability
- **Solution:** ALB distributes traffic across instances, Auto Scaling (min 2, max 10) spins up/down based on CPU. Works because app is stateless, JWT is self-contained, DB is external

**5. Event Ingestion (SQS/SNS/DLQ)**
- **Problem:** High-volume event writes can overwhelm the database and slow down API responses
- **Solution:** Async processing — API publishes to SNS (non-blocking), SQS queues events, worker batch-inserts to DB. Failed messages go to DLQ for replay (no data loss)

**6. Monitoring**
- **Problem:** Can't detect issues or performance degradation without visibility
- **Solution:** CloudWatch for logs/metrics/alarms, ALB health checks every 30s, unhealthy instances auto-replaced

**7. Security**
- **Problem:** Exposed resources and credentials are attack vectors
- **Solution:** VPC private subnets, Security Groups (ALB→EC2→RDS only), Secrets Manager for creds, IAM Roles (no hardcoded secrets), SSL/TLS at ALB

---

## One Improvement I'd Prioritize Next

**Migration from SQLite to PostgreSQL**

SQLite is a single-writer database — it cannot handle concurrent write operations. For an experimentation platform where multiple users are being assigned to variants and events are being recorded simultaneously, this becomes a critical bottleneck. If we can't reliably store assignment and event data under high load, the entire purpose of running experiments is compromised. PostgreSQL supports concurrent reads and writes, proper connection pooling, and scales horizontally with read replicas — making it essential for production workloads. And apart from this I will also make sure that the JWT tokens are sent as httpOnly cookie not not displayed in the response because that is the correct way to do it with security and with the given test experiment had to return it in the response body so it can be used to authorize.

---

## Additional Features Implemented

Beyond the core requirements:

1. **Experiment Lifecycle** - Status transitions (draft → running → paused → completed) with validation
2. **Batch Event Ingestion** - `/events/batch` for high-throughput with atomic transactions
3. **Event Type Discovery** - `/events/types` lists all event types for filter UIs
4. **Data Export** - `/experiments/{id}/results/export` for BI tools and external analysis
5. **Assignment Context** - Optional metadata for post-hoc segmentation (device, location)
6. **Time Series Results** - Configurable granularity (hour/day/week) for trend visualization
7. **Request Timing** - `X-Process-Time` header on all responses for performance monitoring
8. **Interactive API Docs** - Swagger UI (`/docs`) and ReDoc (`/redoc`)

---

## Testing Strategy

For production, I would add:

1. **Unit Tests**
   - Assignment algorithm distribution verification
   - Schema validation edge cases
   - Statistical calculation accuracy

2. **Integration Tests**
   - Full API flow (create → assign → event → results)
   - Idempotency verification
   - Authentication failure scenarios

3. **Load Tests**
   - Assignment endpoint under high concurrency
   - Event ingestion throughput
   - Results query performance at scale

4. **Property-Based Tests**
   - Assignment distribution matches traffic allocation
   - No assignment changes on repeated calls

---

