"""
ByteByteGo System Design 101 Knowledge Base
Sourced from ByteByteGoHq/system-design-101 and modern 2026/2027 engineering architectures.
Covers real architectural case studies, distributed primitives, scale numbers, and runnable simulations.
"""

from typing import Dict, List, Any

SYSTEM_DESIGN_CASE_STUDIES: List[Dict[str, Any]] = [
    {
        "id": "uber-geohash",
        "title": "Design Uber / Proximity Location Service",
        "category": "Real-World Architecture",
        "badge": "ByteByteGo Top #1",
        "diagram_concept": "Client App <-> WebSocket Gateway <-> Redis Geospatial (Geohash) <-> Driver Matching Service",
        "summary": "How Uber tracks millions of moving drivers and matches riders within 1 second using spatial indexing.",
        "description": "Design an end-to-end location ingestion and proximity matching system for a ride-hailing platform. The system must ingest live GPS telemetry from millions of moving drivers and return the top-K nearest available drivers to a rider in under 500ms without overwhelming traditional relational databases.",
        "examples": [
            {
                "input": "Rider Location: (lat: 12.9716, lon: 77.5946), Search Radius: 2.5 km, Top-K: 5 drivers",
                "output": "Matching Drivers: [Driver#104 (0.4km away), Driver#88 (0.9km away), Driver#201 (1.2km away)]",
                "explanation": "Calculates rider's Geohash prefix at level 6 (~1.2km) and queries adjacent 8 cells in Redis cluster, sorting candidates by routing ETA."
            }
        ],
        "constraints": [
            "10 Million active drivers globally emitting GPS pings every 4 seconds",
            "Write throughput: 2,500,000 GPS pings / second peak write load",
            "Rider ride request read QPS: ~8,000 QPS peak",
            "Latency SLA: Driver matching response < 300ms p99",
            "Availability SLA: 99.99% uptime"
        ],
        "target_complexity": {
            "time": "Spatial Lookup: O(log N) via 52-bit Geohash index in Redis",
            "space": "RAM: ~1.2 GB in Redis hot memory for 10M active drivers (15s TTL)"
        },
        "architecture_points": [
            "Spatial Indexing: Regular lat/lng queries cause full table scans. Use Geohash (base32 string where common prefixes share geographic regions) or Google S2 / QuadTree.",
            "Live Driver Telemetry: Drivers emit GPS pings every 4 seconds over persistent WebSockets to a dedicated Location Ingestion Gateway.",
            "In-Memory Hot Store: Driver locations are held in Redis using GEOADD / GEORADIUS with 15-second TTL.",
            "Driver-Rider Matching: Query rider's Geohash cell and the 8 neighbor cells, filter available drivers, and rank by ETA."
        ],
        "interview_grill_questions": [
            "Why is Geohash preferred over QuadTree for distributed scaling? (Geohash partitions easily across Redis cluster keys; QuadTree requires distributed tree synchronization).",
            "What happens if a driver is on the boundary between two Geohash cells? (Query the 8 surrounding neighbor cells using 8-directional neighbor hashing)."
        ],
        "starter_code": {
            "python": """import math

class ProximityEngine:
    def __init__(self):
        # Simulated geospatial grid: cell_id -> list of (driver_id, lat, lon)
        self.cells = {}

    def _get_cell_key(self, lat: float, lon: float, precision: float = 0.02) -> str:
        # Simple spatial grid hashing simulating Geohash prefix
        r = round(lat / precision) * precision
        c = round(lon / precision) * precision
        return f"{r:.2f}:{c:.2f}"

    def update_driver_location(self, driver_id: str, lat: float, lon: float):
        cell_key = self._get_cell_key(lat, lon)
        if cell_key not in self.cells:
            self.cells[cell_key] = []
        # Update or add driver
        self.cells[cell_key] = [d for d in self.cells[cell_key] if d[0] != driver_id]
        self.cells[cell_key].append((driver_id, lat, lon))

    def find_nearest_drivers(self, rider_lat: float, rider_lon: float, limit: int = 3):
        cell_key = self._get_cell_key(rider_lat, rider_lon)
        candidates = self.cells.get(cell_key, [])
        # Calculate Euclidean distance as proxy
        ranked = []
        for d_id, d_lat, d_lon in candidates:
            dist_km = math.sqrt((rider_lat - d_lat)**2 + (rider_lon - d_lon)**2) * 111
            ranked.append((d_id, round(dist_km, 2)))
        ranked.sort(key=lambda x: x[1])
        return ranked[:limit]

# Run Simulation
engine = ProximityEngine()
engine.update_driver_location("Driver_A", 12.9715, 77.5945)
engine.update_driver_location("Driver_B", 12.9720, 77.5950)
engine.update_driver_location("Driver_C", 12.9735, 77.5960)

print("Simulating Uber Spatial Proximity Search:")
matches = engine.find_nearest_drivers(12.9716, 77.5946, limit=2)
print("Nearest Drivers Matched:", matches)
""",
            "javascript": """class ProximityEngine {
    constructor() {
        this.cells = new Map();
    }
    getCellKey(lat, lon, precision = 0.02) {
        const r = (Math.round(lat / precision) * precision).toFixed(2);
        const c = (Math.round(lon / precision) * precision).toFixed(2);
        return `${r}:${c}`;
    }
    updateDriver(id, lat, lon) {
        const key = this.getCellKey(lat, lon);
        if (!this.cells.has(key)) this.cells.set(key, []);
        const list = this.cells.get(key).filter(d => d.id !== id);
        list.push({ id, lat, lon });
        this.cells.set(key, list);
    }
    findNearest(rLat, rLon, limit = 2) {
        const key = this.getCellKey(rLat, rLon);
        const candidates = this.cells.get(key) || [];
        return candidates.map(d => {
            const dist = Math.sqrt((rLat - d.lat)**2 + (rLon - d.lon)**2) * 111;
            return { id: d.id, distKm: Number(dist.toFixed(2)) };
        }).sort((a, b) => a.distKm - b.distKm).slice(0, limit);
    }
}

const engine = new ProximityEngine();
engine.updateDriver("Driver_101", 12.9715, 77.5945);
engine.updateDriver("Driver_102", 12.9720, 77.5950);
console.log("Matched Drivers:", engine.findNearest(12.9716, 77.5946));
"""
        }
    },

    {
        "id": "whatsapp-chat",
        "title": "Design WhatsApp / Real-Time Chat at Scale",
        "category": "Real-World Architecture",
        "badge": "ByteByteGo Top #2",
        "diagram_concept": "Mobile Client <-> TCP / WebSocket Gateway (Erlang/Go) <-> Message Broker <-> ScyllaDB/Cassandra",
        "summary": "Scaling persistent connections for 2+ billion active users with sub-100ms message delivery and offline sync.",
        "description": "Design a globally distributed messaging architecture capable of handling billions of concurrent bidirectional connections with guaranteed message order, offline delivery queueing, delivery ticks (sent, delivered, read), and end-to-end encryption.",
        "examples": [
            {
                "input": "User A sends message 'Hello' to User B (offline)",
                "output": "Server responds with Single Tick (ACK); writes message blob to Cassandra offline mailbox. When User B reconnects, message is pushed and Double Tick is emitted to User A.",
                "explanation": "Decouples message relay from client availability using persistent LSM-tree storage."
            }
        ],
        "constraints": [
            "2 Billion active users, 100 Billion messages / day",
            "Average 1.15 Million messages / second write throughput",
            "Sub-100ms delivery latency for online recipients",
            "Zero server plaintext inspection (End-to-End Encryption)",
            "Ephemeral offline mailbox: messages purged immediately upon successful client ACK"
        ],
        "target_complexity": {
            "time": "Relay Latency: <50ms over active WebSockets",
            "space": "Connection RAM: <3KB memory per idle TCP connection via Go epoll / Erlang"
        },
        "architecture_points": [
            "Connection Management: Maintain long-lived TCP/WebSocket connections using lightweight actors (Erlang/Go) to minimize RAM.",
            "User Presence & Session Registry: Distributed Redis/ZooKeeper cluster maps user_id -> connection_server_ip.",
            "Offline Message Store: If recipient is offline, store in write-optimized ScyllaDB/Cassandra (user_id partition key).",
            "E2E Encryption: Server only routes encrypted payloads; encryption keys stay exclusively on client devices."
        ],
        "interview_grill_questions": [
            "How do you handle group chats with 1,024 members? (Fan-out on publish at broker, duplicating pointer rather than payloads).",
            "How do delivery ticks work? (Event-driven ACK messages emitted through WebSocket back to the sender)."
        ],
        "starter_code": {
            "python": """class ChatGateway:
    def __init__(self):
        # Maps user_id -> server_address (Presence registry)
        self.presence = {}
        # Maps user_id -> list of unread message payloads (Offline store)
        self.offline_store = {}

    def connect_user(self, user_id: str, gateway_ip: str):
        self.presence[user_id] = gateway_ip
        # Deliver pending offline messages
        pending = self.offline_store.pop(user_id, [])
        return pending

    def disconnect_user(self, user_id: str):
        self.presence.pop(user_id, None)

    def send_message(self, sender_id: str, recipient_id: str, text: str):
        msg = {"from": sender_id, "text": text, "status": "sent"}
        if recipient_id in self.presence:
            # Immediate live push
            dest_gateway = self.presence[recipient_id]
            msg["status"] = "delivered_online"
            return f"Routed to {recipient_id} on {dest_gateway} [Double Tick]"
        else:
            # Queue in offline store
            if recipient_id not in self.offline_store:
                self.offline_store[recipient_id] = []
            self.offline_store[recipient_id].append(msg)
            return f"Stored in offline mailbox for {recipient_id} [Single Tick]"

# Simulation
gateway = ChatGateway()
gateway.connect_user("Alice", "gateway-node-1")
print(gateway.send_message("Alice", "Bob", "Are you available?"))

print("\\nBob comes online...")
pending_msgs = gateway.connect_user("Bob", "gateway-node-2")
print(f"Bob received {len(pending_msgs)} pending messages: {pending_msgs}")
""",
            "javascript": """class ChatGateway {
    constructor() {
        this.presence = new Map();
        this.offlineStore = new Map();
    }
    connect(user, ip) {
        this.presence.set(user, ip);
        const pending = this.offlineStore.get(user) || [];
        this.offlineStore.delete(user);
        return pending;
    }
    send(sender, receiver, text) {
        if (this.presence.has(receiver)) {
            return `Delivered to ${receiver} live [Double Tick]`;
        }
        if (!this.offlineStore.has(receiver)) this.offlineStore.set(receiver, []);
        this.offlineStore.get(receiver).push({ from: sender, text });
        return `Buffered in offline store for ${receiver} [Single Tick]`;
    }
}

const gw = new ChatGateway();
gw.connect("Alice", "srv-1");
console.log(gw.send("Alice", "Bob", "Hello world!"));
console.log("Bob connects:", gw.connect("Bob", "srv-2"));
"""
        }
    },

    {
        "id": "payment-idempotency",
        "title": "Design Payment Gateway (Stripe/Razorpay) & Idempotency",
        "category": "FinTech & Distributed Transactions",
        "badge": "ByteByteGo Critical",
        "diagram_concept": "Client (Idempotency-Key) <-> API Gateway <-> Redis Distributed Lock <-> Ledger Service (Two-Phase Commit)",
        "summary": "Guaranteeing exact-once payment execution, zero double-charges, and distributed ledger consistency.",
        "description": "Design an idempotent payment processing architecture. Network timeouts and mobile app retries must never result in duplicate financial debits. The architecture must handle distributed locks, double-entry bookkeeping, and transaction reconciliation.",
        "examples": [
            {
                "input": "POST /v1/charges { amount: $100, user: 'U1' } Header: Idempotency-Key: 'uuid-789-xyz'",
                "output": "Charge processed, transaction ID: 'ch_44921'. Subsequent identical requests return exact same response without re-charging.",
                "explanation": "Redis SETNX distributed lock acquires key in 'PROCESSING' state; once completed, cached payload is returned for 24 hours."
            }
        ],
        "constraints": [
            "Strict Exactly-Once semantics (Zero double billing tolerance)",
            "Idempotency key TTL: 24 to 72 hours",
            "Distributed race conditions: Multiple concurrent requests with same key must block or wait",
            "Auditability: Double-entry ledger with immutable credit/debit records"
        ],
        "target_complexity": {
            "time": "Idempotency Lock Check: O(1) in Redis (~2ms latency)",
            "space": "Redis Storage: ~200 bytes per idempotency key record"
        },
        "architecture_points": [
            "Idempotency Key Pattern: Every charge contains a unique UUIDv4. Gateway locks this key with state 'PROCESSING'.",
            "Double-Charge Prevention: Retries with same key wait or receive the cached original response.",
            "Two-Phase Commit / Saga: Coordinate bank network and balance ledger using orchestrated Saga pattern.",
            "Double-Entry Ledger: Store immutable debit/credit ledger records where total credits = total debits."
        ],
        "interview_grill_questions": [
            "What happens if payment provider is slow and the Redis lock expires? (Lock renewal heartbeats + DB unique constraint on idempotency_key).",
            "How do you reconcile ledger discrepancies? (End-of-day asynchronous batch settlement comparing bank files)."
        ],
        "starter_code": {
            "python": """import time
import uuid

class IdempotentPaymentGateway:
    def __init__(self):
        # Simulated Redis key-value store: idempotency_key -> (status, response, timestamp)
        self.idempotency_store = {}
        self.accounts = {"Alice": 500, "Merchant": 1000}

    def process_charge(self, idempotency_key: str, user: str, amount: float):
        # 1. Check idempotency store
        if idempotency_key in self.idempotency_store:
            record = self.idempotency_store[idempotency_key]
            if record["status"] == "COMPLETED":
                return {"cached": True, "data": record["response"], "note": "Duplicate retry prevented!"}
            elif record["status"] == "PROCESSING":
                return {"error": "Concurrent request in progress. Please wait.", "code": 409}

        # 2. Acquire lock (SETNX)
        self.idempotency_store[idempotency_key] = {"status": "PROCESSING", "time": time.time()}

        # 3. Execute financial transaction
        if self.accounts.get(user, 0) < amount:
            self.idempotency_store.pop(idempotency_key)
            return {"error": "Insufficient funds", "code": 400}

        # Double-entry ledger mutation
        self.accounts[user] -= amount
        self.accounts["Merchant"] += amount
        charge_id = f"ch_{uuid.uuid4().hex[:8]}"
        response_payload = {"charge_id": charge_id, "amount": amount, "status": "succeeded"}

        # 4. Save response in cache
        self.idempotency_store[idempotency_key] = {"status": "COMPLETED", "response": response_payload}
        return {"cached": False, "data": response_payload}

# Simulation
gateway = IdempotentPaymentGateway()
key = "req_uuid_9921_abc"

print("1. First charge request ($100):")
print(gateway.process_charge(key, "Alice", 100))

print("\\n2. Duplicate retry with same idempotency key (e.g. mobile timeout retry):")
print(gateway.process_charge(key, "Alice", 100))

print("\\nFinal Balances:", gateway.accounts)
""",
            "javascript": """class IdempotentPaymentGateway {
    constructor() {
        this.cache = new Map();
        this.accounts = { Alice: 500, Merchant: 1000 };
    }
    charge(key, user, amount) {
        if (this.cache.has(key)) {
            return { cached: true, response: this.cache.get(key), note: "Prevented duplicate charge!" };
        }
        if (this.accounts[user] < amount) return { error: "Insufficient balance" };
        this.accounts[user] -= amount;
        this.accounts.Merchant += amount;
        const res = { chargeId: "ch_" + Math.random().toString(36).substr(2, 8), amount, status: "succeeded" };
        this.cache.set(key, res);
        return { cached: false, response: res };
    }
}

const gw = new IdempotentPaymentGateway();
const key = "key_123";
console.log("First request:", gw.charge(key, "Alice", 100));
console.log("Retry request:", gw.charge(key, "Alice", 100));
console.log("Balances:", gw.accounts);
"""
        }
    },

    {
        "id": "rate-limiter-algorithms",
        "title": "Design Distributed Rate Limiter (Token Bucket)",
        "category": "Core Primitives",
        "badge": "ByteByteGo Fundamental",
        "diagram_concept": "API Client -> Reverse Proxy -> Redis Lua Script (Token Bucket) -> Backend Microservice",
        "summary": "Protecting APIs from DDoS and abuse across distributed worker nodes using Token Bucket.",
        "description": "Design a high-throughput, low-latency distributed rate limiter that throttles API traffic per user/IP. The rate limiter must support burst traffic while enforcing long-term limits using atomic Redis Lua scripts.",
        "examples": [
            {
                "input": "Rate limit: 5 requests/sec, Burst: 5 tokens. User fires 7 rapid requests.",
                "output": "First 5 requests accepted (HTTP 200). Requests 6 & 7 rejected with HTTP 429 Too Many Requests (Retry-After: 1s).",
                "explanation": "Token bucket refills at rate R. Tokens consumed per request; when empty, request is rejected."
            }
        ],
        "constraints": [
            "Handle 100,000+ API requests per second",
            "Rate limiting check latency: <2ms p99",
            "Zero race conditions across distributed API servers (Atomicity guaranteed via Redis Lua)",
            "Headers returned: X-RateLimit-Limit, X-RateLimit-Remaining, Retry-After"
        ],
        "target_complexity": {
            "time": "O(1) evaluation via Redis Lua script",
            "space": "O(N) where N is number of active client keys (~100 bytes per user key)"
        },
        "architecture_points": [
            "Token Bucket Algorithm: Tokens added at constant rate up to bucket capacity. Request consumes 1 token.",
            "Distributed Lua Scripts: Executed atomically inside single Redis thread, avoiding race conditions.",
            "Client Feedback: Standard HTTP headers: X-RateLimit-Limit, X-RateLimit-Remaining, Retry-After."
        ],
        "interview_grill_questions": [
            "Why use Lua scripts instead of separate Redis GET and INCR? (Lua executes atomically, eliminating race conditions).",
            "How do you handle Redis failure? (Fail-open for business-critical APIs, fail-closed for public auth endpoints)."
        ],
        "starter_code": {
            "python": """import time

class TokenBucketRateLimiter:
    def __init__(self, capacity: int, refill_rate_per_sec: float):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.tokens = capacity
        self.last_refill = time.time()

    def allow_request(self) -> bool:
        now = time.time()
        # Calculate refilled tokens based on elapsed time
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

# Simulation
limiter = TokenBucketRateLimiter(capacity=3, refill_rate_per_sec=1.0)
print("Testing Token Bucket Rate Limiter (Capacity: 3, Refill: 1 token/sec):")
for i in range(5):
    allowed = limiter.allow_request()
    status = "ALLOWED (HTTP 200)" if allowed else "THROTTLED (HTTP 429 Too Many Requests)"
    print(f"Request #{i+1}: {status} | Remaining Tokens: {limiter.tokens:.1f}")
""",
            "javascript": """class TokenBucket {
    constructor(capacity, refillPerSec) {
        this.capacity = capacity;
        this.refillRate = refillPerSec;
        this.tokens = capacity;
        this.lastTime = Date.now();
    }
    allow() {
        const now = Date.now();
        const elapsedSec = (now - this.lastTime) / 1000;
        this.tokens = Math.min(this.capacity, this.tokens + elapsedSec * this.refillRate);
        this.lastTime = now;
        if (this.tokens >= 1) {
            this.tokens -= 1;
            return true;
        }
        return false;
    }
}

const limiter = new TokenBucket(3, 1);
for (let i = 1; i <= 5; i++) {
    console.log(`Req #${i}:`, limiter.allow() ? "HTTP 200 (Allowed)" : "HTTP 429 (Throttled)");
}
"""
        }
    },

    {
        "id": "caching-pitfalls",
        "title": "Distributed Caching Pitfalls & Eviction",
        "category": "Core Primitives",
        "badge": "Interview High-Frequency",
        "diagram_concept": "Cache Avalanche | Cache Breakdown | Cache Penetration Strategies",
        "summary": "The 3 fundamental caching failures that take down large systems and how to architect resilience.",
        "description": "Architect defensive mechanisms against the three catastrophic cache failure modes: Cache Avalanche (simultaneous TTL expiration), Cache Breakdown (hotspot key expiration), and Cache Penetration (queries for non-existent keys).",
        "examples": [
            {
                "input": "User queries for non-existent product ID = -999",
                "output": "Bloom filter returns False in O(1) memory; request rejected immediately without querying database.",
                "explanation": "Prevents malicious DB resource exhaustion using probabilistic membership checking."
            }
        ],
        "constraints": [
            "Handle 1,000,000 cache lookups per second",
            "Zero database connection pool saturation during sudden traffic spikes",
            "Sub-millisecond cache latency",
            "Bloom filter false positive rate < 1%"
        ],
        "target_complexity": {
            "time": "Bloom Filter check: O(K) where K is number of hash functions (~0.1ms)",
            "space": "Bit array: 9.6 bits per item for 1% false positive rate"
        },
        "architecture_points": [
            "Cache Avalanche Fix: Add random jitter to TTL (e.g. base_ttl + random(0, 300)s).",
            "Cache Breakdown Fix: Mutex / Distributed Lock (Redis SETNX) so only 1 thread recomputes.",
            "Cache Penetration Fix: Bloom Filter in front of cache + caching null values with 60s TTL."
        ],
        "interview_grill_questions": [
            "How does a Bloom filter work? (Bit array with K independent hash functions; zero false negatives).",
            "When should you use Cache-Aside vs Write-Through? (Cache-Aside for read-heavy workloads; Write-Through for strict read-consistency)."
        ],
        "starter_code": {
            "python": """import random

class ResilientCacheManager:
    def __init__(self):
        self.cache = {}
        self.bloom_filter = set(["item_1", "item_2", "item_3"]) # Simulated Bloom filter

    def get_with_jitter_ttl(self, key: str, base_ttl_sec: int = 300) -> int:
        # Prevents Cache Avalanche: adds random jitter
        jitter = random.randint(0, 60)
        return base_ttl_sec + jitter

    def safe_get(self, key: str):
        # 1. Prevent Cache Penetration: Check Bloom Filter first
        if key not in self.bloom_filter:
            return {"status": "BLOCKED_BY_BLOOM_FILTER", "data": None, "note": "Non-existent item shielded from DB!"}

        # 2. Check Cache
        if key in self.cache:
            return {"status": "CACHE_HIT", "data": self.cache[key]}

        # 3. Simulate DB fetch & write back with jitter TTL
        ttl = self.get_with_jitter_ttl(key)
        self.cache[key] = f"Value_of_{key}"
        return {"status": "CACHE_MISS_DB_LOADED", "data": self.cache[key], "ttl_assigned": ttl}

# Simulation
mgr = ResilientCacheManager()
print("1. Query non-existent key (Cache Penetration attempt):")
print(mgr.safe_get("invalid_id_999"))

print("\\n2. Query valid key (Cache miss -> loaded with jitter TTL):")
print(mgr.safe_get("item_1"))
""",
            "javascript": """class ResilientCache {
    constructor() {
        this.cache = new Map();
        this.knownKeys = new Set(["item_1", "item_2"]);
    }
    get(key) {
        if (!this.knownKeys.has(key)) {
            return { status: "REJECTED_BY_BLOOM_FILTER", data: null };
        }
        if (this.cache.has(key)) {
            return { status: "CACHE_HIT", data: this.cache.get(key) };
        }
        const val = `Loaded_${key}`;
        this.cache.set(key, val);
        return { status: "CACHE_MISS_LOADED", data: val, jitterTtl: 300 + Math.floor(Math.random() * 60) };
    }
}

const c = new ResilientCache();
console.log(c.get("fake_id"));
console.log(c.get("item_1"));
"""
        }
    },

    {
        "id": "rag-enterprise-system-design",
        "title": "Design Enterprise Real-Time RAG & Vector Pipeline (2026/2027)",
        "category": "GenAI & LLM Architecture",
        "badge": "Modern 2026 Tech",
        "diagram_concept": "Doc Ingestion -> Semantic Chunker -> Embedding Model -> Qdrant/Pinecone (HNSW) -> Hybrid Search -> Cohere Re-ranker -> Context Window",
        "summary": "Building production Retrieval-Augmented Generation for enterprise scale with low latency and high precision.",
        "description": "Design an enterprise-grade Retrieval-Augmented Generation (RAG) architecture capable of ingesting millions of internal documents, indexing dense & sparse representations, and delivering sub-200ms context retrieval with cross-encoder re-ranking to prevent hallucinations.",
        "examples": [
            {
                "input": "User query: 'What is our refund SLA for damaged freight under contract v2.4?'",
                "output": "Dense + Sparse Hybrid Search returns 50 chunks; Cohere Re-ranker filters to top 3 relevant chunks injected into prompt.",
                "explanation": "Hybrid search prevents lexical misses (e.g. exact contract numbers) while dense embeddings capture semantic meaning."
            }
        ],
        "constraints": [
            "Document corpus: 10 Million enterprise PDFs / Notion / Confluence docs",
            "Retrieval SLA: < 150ms p99 before LLM generation starts",
            "Hallucination rate < 0.5% with mandatory citation attribution",
            "Role-based access control (RBAC): Enforce document permissions at vector search query time"
        ],
        "target_complexity": {
            "time": "HNSW Vector Search: O(log N) nearest neighbor search (~10ms)",
            "space": "Vector RAM: ~1536 floats per chunk * 10M chunks = ~60GB RAM"
        },
        "architecture_points": [
            "Hybrid Search (Dense + Sparse): Combine dense embeddings with lexical BM25 using Reciprocal Rank Fusion (RRF).",
            "Cross-Encoder Re-ranking: Re-rank top 50 vector candidates down to top 5 using Cohere/BGE re-ranker.",
            "Vector Indexing: HNSW (Hierarchical Navigable Small World) for sub-15ms search latency.",
            "Metadata Pre-Filtering: Filter by tenant_id and user_role directly inside vector query before distance calculation."
        ],
        "interview_grill_questions": [
            "How do you prevent the lost-in-the-middle phenomenon in LLMs? (Re-rank chunks and position highest-scoring context at start and end).",
            "How do you handle real-time document permission changes? (Enforce RBAC metadata pre-filters in vector DB query)."
        ],
        "starter_code": {
            "python": """class SimpleRAGPipeline:
    def __init__(self):
        # Simulated vector database documents: id -> (title, text, keywords)
        self.docs = [
            {"id": "doc_1", "text": "Refund policy for damaged goods: Full refund within 30 days with photo proof.", "kw": ["refund", "damaged", "policy"]},
            {"id": "doc_2", "text": "Enterprise contract SLA: 99.9% uptime with 4-hour response time.", "kw": ["sla", "uptime", "contract"]},
            {"id": "doc_3", "text": "Employee vacation policy: 20 days paid time off annually.", "kw": ["vacation", "pto", "employee"]}
        ]

    def hybrid_search(self, query: str, top_k: int = 1):
        query_words = set(query.lower().split())
        scored_docs = []
        for doc in self.docs:
            # Simulated lexical overlap score
            overlap = len(query_words.intersection(set(doc["kw"])))
            scored_docs.append((doc, overlap))
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return [doc["text"] for doc, score in scored_docs[:top_k]]

# Run Simulation
rag = SimpleRAGPipeline()
query = "What is the refund policy for damaged shipments?"
print("User Query:", query)
retrieved_context = rag.hybrid_search(query)
print("\\nRetrieved Context for LLM Injection:")
print(retrieved_context[0])
""",
            "javascript": """class RAGPipeline {
    constructor() {
        this.docs = [
            { id: 1, text: "Refunds for damaged goods issued within 30 days.", kws: ["refund", "damaged"] },
            { id: 2, text: "Enterprise SLA guarantees 99.9% uptime.", kws: ["sla", "uptime"] }
        ];
    }
    retrieve(query) {
        const words = new Set(query.toLowerCase().split(" "));
        return this.docs.map(d => ({
            ...d,
            score: d.kws.filter(w => words.has(w)).length
        })).sort((a, b) => b.score - a.score)[0].text;
    }
}

const rag = new RAGPipeline();
console.log("Retrieved:", rag.retrieve("Need a refund on damaged items"));
"""
        }
    }
]


def list_system_design_cases() -> List[Dict[str, Any]]:
    """Returns list of ByteByteGo 101 system design case studies."""
    return SYSTEM_DESIGN_CASE_STUDIES


def get_system_design_case(case_id: str) -> Dict[str, Any]:
    """Retrieve details of a specific system design case study."""
    case_id_clean = case_id.lower().strip()
    for case in SYSTEM_DESIGN_CASE_STUDIES:
        if case["id"] == case_id_clean or case_id_clean in case["id"]:
            return case
    return SYSTEM_DESIGN_CASE_STUDIES[0]
