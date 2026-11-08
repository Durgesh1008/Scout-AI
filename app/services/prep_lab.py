import logging
import re
from typing import Dict, List, Any, Optional

from app.data.company_problems import get_company_leetcode_problems
from app.data.system_design_101 import list_system_design_cases, get_system_design_case

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. CORE TECHNICAL MASTER TRACKS (Playlists, Roadmaps & Top Questions)
# ==============================================================================

PREP_TRACKS: Dict[str, Dict[str, Any]] = {
    "systemdesign": {
        "id": "systemdesign",
        "title": "System Design (HLD & LLD)",
        "badge": "Architecture & Scaling",
        "icon": "bi-diagram-3",
        "color": "#7c3aed",
        "gradient": "linear-gradient(135deg, rgba(124, 58, 237, 0.2), rgba(88, 166, 255, 0.1))",
        "description": "Master scaling from 1 to 10M users: Load Balancing, Caching (Redis), DB Sharding, Microservices, CAP Theorem, and Message Queues (Kafka/RabbitMQ).",
        "playlists": [
            {
                "title": "System Design for Beginners",
                "creator": "Gaurav Sen",
                "url": "https://www.youtube.com/playlist?list=PLMCXHnjXnTnvo6alSjVkgxV-VH6EPyvoX",
                "tag": "Foundations"
            },
            {
                "title": "ByteByteGo System Design Fundamentals",
                "creator": "Alex Xu (ByteByteGo)",
                "url": "https://www.youtube.com/@ByteByteGo",
                "tag": "HLD Diagrams"
            },
            {
                "title": "Backend Engineering Masterclass",
                "creator": "Hussein Nasser",
                "url": "https://www.youtube.com/c/HusseinNasser-software-engineering",
                "tag": "Database & Protocols"
            }
        ],
        "roadmap": [
            "1. Client-Server Architecture, DNS & Reverse Proxies (Nginx)",
            "2. Caching Strategies: Cache-Aside, Write-Through, Write-Back, Redis eviction policies",
            "3. Database Scaling: Read Replicas, Horizontal Sharding, Master-Slave, Normalization vs Denormalization",
            "4. Asynchronous Processing: Message Queues (Kafka vs RabbitMQ), Event-Driven Architecture",
            "5. Microservices Resilience: Circuit Breaker pattern, Rate Limiting (Token Bucket), Idempotency Keys"
        ],
        "top_questions": [
            {
                "q": "What is the difference between Cache-Aside and Write-Through caching, and when do you use Redis?",
                "a": "In Cache-Aside, the app first checks cache; on miss, it loads from DB and writes to cache. In Write-Through, data is written to cache and DB simultaneously. Redis is preferred in memory for sub-millisecond lookups, session storage, and rate limiting with TTL expiry."
            },
            {
                "q": "How does Database Sharding work, and what is the re-sharding problem?",
                "a": "Sharding splits a huge DB table across multiple database servers using a shard key (e.g. hash(user_id) % N). If you add new servers, regular hashing causes almost all keys to move. Consistent Hashing solves this by mapping nodes and keys on a ring, moving only K/N keys when scaling."
            },
            {
                "q": "Explain the CAP theorem with a real-world example.",
                "a": "In a distributed network with partitions (P), you can only guarantee either Consistency (all nodes see latest data) or Availability (every request gets a non-error response). Example: ATM withdrawal during network split chooses Consistency (blocks withdrawal) over Availability to avoid double-spending."
            },
            {
                "q": "How do you handle API idempotency in payments and order creation?",
                "a": "The client passes a unique `Idempotency-Key` (UUIDv4) in headers. The backend stores this key in Redis/DB with state 'PROCESSING'. If a duplicate request arrives (e.g. network retry), the server returns the cached response instead of charging again."
            }
        ]
    },

    "networking": {
        "id": "networking",
        "title": "Computer Networking",
        "badge": "Core Fundamentals",
        "icon": "bi-hdd-network",
        "color": "#0ea5e9",
        "gradient": "linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(59, 130, 246, 0.1))",
        "description": "Essential protocols powering the web: OSI 7 Layers, TCP 3-way Handshake vs UDP, HTTP/1.1 vs HTTP/2 vs HTTP/3, WebSockets, DNS, and TLS Handshake.",
        "playlists": [
            {
                "title": "Networking Fundamentals",
                "creator": "NetworkChuck",
                "url": "https://www.youtube.com/playlist?list=PLIhvC56v63IJVXv0GJcl9vO5Z6znCVb1P",
                "tag": "Visual & Simple"
            },
            {
                "title": "HTTP, TCP, UDP & WebSockets Deep-Dive",
                "creator": "Hussein Nasser",
                "url": "https://www.youtube.com/playlist?list=PLQnljOFTspQUNnkW8EZhZ6slHK6yXwtpW",
                "tag": "Interview-focused"
            }
        ],
        "roadmap": [
            "1. OSI 7 Layer Model vs TCP/IP Stack & Encapsulation",
            "2. TCP 3-way Handshake (SYN -> SYN-ACK -> ACK) & 4-way Teardown",
            "3. UDP vs TCP: Packet loss, latency, streaming vs reliable transfers",
            "4. HTTP Evolution: HTTP/1.1 (head-of-line blocking) -> HTTP/2 (multiplexing over 1 TCP connection) -> HTTP/3 (QUIC over UDP)",
            "5. WebSockets vs Long Polling vs Server-Sent Events (SSE)",
            "6. TLS/SSL Handshake: Symmetric vs Asymmetric encryption, Digital Certificates & CAs"
        ],
        "top_questions": [
            {
                "q": "What exact steps happen when you type 'google.com' in your browser and press Enter?",
                "a": "1. Browser checks cache (browser -> OS -> router -> DNS resolver). 2. Resolver performs recursive DNS lookup (Root -> TLD .com -> Authoritative). 3. TCP 3-way handshake established with destination IP. 4. TLS Handshake negotiates encryption keys. 5. Browser sends HTTP GET request. 6. Server processes and streams HTML/CSS/JS. 7. Browser DOM parser builds DOM tree and renders page."
            },
            {
                "q": "Why does HTTP/2 use multiplexing, and what problem did it solve from HTTP/1.1?",
                "a": "In HTTP/1.1, each request required its own TCP connection or queued in line (Head-of-Line Blocking). HTTP/2 splits streams into binary frames over a single TCP connection, allowing hundreds of parallel requests without waiting for previous ones to finish."
            },
            {
                "q": "When would you choose WebSockets over Server-Sent Events (SSE)?",
                "a": "WebSockets are full-duplex bidirectional (client and server can talk simultaneously, e.g., multiplayer gaming, live chat). SSE is unidirectional (server pushes to client only, e.g., stock tickers, LLM token streaming), and runs natively over standard HTTP without custom firewall protocols."
            }
        ]
    },

    "ai": {
        "id": "ai",
        "title": "Generative AI & LLM Engineering",
        "badge": "High Demand 2026",
        "icon": "bi-cpu",
        "color": "#10b981",
        "gradient": "linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(124, 58, 237, 0.1))",
        "description": "Build real LLM apps: Prompt Engineering, RAG (Retrieval-Augmented Generation), Vector DBs (Chroma/Pinecone), Embeddings, Agentic Workflows & LangChain.",
        "playlists": [
            {
                "title": "Neural Networks: Zero to Hero",
                "creator": "Andrej Karpathy",
                "url": "https://www.youtube.com/playlist?list=PLAqhIrjkxbuWI23v9cThsA9GvCAUhRvKZ",
                "tag": "Masterclass"
            },
            {
                "title": "Generative AI for Developers",
                "creator": "DeepLearning.AI / Andrew Ng",
                "url": "https://www.deeplearning.ai/short-courses/",
                "tag": "RAG & Agents"
            },
            {
                "title": "LangChain & LlamaIndex Crash Course",
                "creator": "FreeCodeCamp",
                "url": "https://www.youtube.com/watch?v=aywZrzNaKjs",
                "tag": "Hands-on Code"
            }
        ],
        "roadmap": [
            "1. Transformer Architecture: Self-Attention mechanism, Tokens & Context Windows",
            "2. Vector Embeddings: Turning text into dense numeric vectors & Cosine Similarity",
            "3. RAG Pipeline: Ingestion -> Chunking -> Vector Indexing -> Semantic Retrieval -> Context Injection",
            "4. Vector Databases: Pinecone, ChromaDB, PGVector (HNSW vs IVFFlat indexing)",
            "5. Agentic AI & Tool Calling: Function calling, ReAct pattern (Reason + Act), Memory management"
        ],
        "top_questions": [
            {
                "q": "How does Retrieval-Augmented Generation (RAG) work, and how does it prevent hallucinations?",
                "a": "RAG retrieves relevant private or up-to-date documentation using vector similarity before prompting the LLM. By injecting verified chunks directly into the prompt context window and commanding the model to answer only based on the retrieved context, hallucinations are minimized and source attribution is provided."
            },
            {
                "q": "What is the difference between Fine-Tuning and RAG?",
                "a": "Fine-Tuning adjusts the model's weights to learn tone, style, or syntax patterns (expensive, static knowledge). RAG injects dynamic external knowledge at query time (cheap, real-time data, verifiable). For adding new company documentation, RAG is 95% of the time the correct choice."
            },
            {
                "q": "What is Cosine Similarity and why is it used in Vector Search?",
                "a": "Cosine similarity measures the cosine of the angle between two multi-dimensional embedding vectors (range -1 to 1). Unlike Euclidean distance, it is normalized and measures semantic direction rather than vector magnitude, making it ideal for matching meaning."
            }
        ]
    },

    "mern": {
        "id": "mern",
        "title": "MERN & Full Stack Architecture",
        "badge": "Core Tech Stack",
        "icon": "bi-layers-half",
        "color": "#f59e0b",
        "gradient": "linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(239, 68, 68, 0.1))",
        "description": "Production-grade MERN mastery: React 19 reconciliation, Node.js Event Loop phases, Express middleware, MongoDB aggregation pipelines & indexing, JWT security.",
        "playlists": [
            {
                "title": "Namaste JavaScript & Node.js",
                "creator": "Akshay Saini",
                "url": "https://www.youtube.com/playlist?list=PLlasXeu85E9cQ32gLCvAvr9vNaUccPVNP",
                "tag": "JS Internals"
            },
            {
                "title": "Full Stack MERN Architecture",
                "creator": "Web Dev Simplified",
                "url": "https://www.youtube.com/playlist?list=PLZlA0Gpn_vH_NT5zPVp18nGe_W9LqBDQK",
                "tag": "Production Code"
            }
        ],
        "roadmap": [
            "1. JavaScript V8 Engine: Call Stack, Libuv, Event Loop (Microtask vs Macrotask queue)",
            "2. React Core: Virtual DOM, Fiber Reconciliation, useMemo/useCallback optimization, Custom Hooks",
            "3. Node.js & Express: Non-blocking I/O, Streams & Buffers, Cluster module, Error Handling middleware",
            "4. MongoDB Mastery: B-Tree Indexing, Compound Indexes, Aggregation Pipeline ($match, $lookup, $group)",
            "5. Security & Deployment: JWT vs Sessions, CORS, CSRF, Rate-limiting, Docker multi-stage builds"
        ],
        "top_questions": [
            {
                "q": "Explain the Node.js Event Loop and the difference between process.nextTick() and setImmediate().",
                "a": "The event loop has distinct phases: Timers -> Pending Callbacks -> Idle/Prepare -> Poll -> Check -> Close. `process.nextTick()` fires immediately after the current operation finishes before any event loop phase transitions. `setImmediate()` executes in the 'Check' phase of the event loop."
            },
            {
                "q": "Why is using an index in MongoDB critical, and how do compound indexes work?",
                "a": "Without an index, MongoDB executes a full collection scan (COLLSCAN) checking every document (O(N)). An index builds a B-Tree (O(log N)). A compound index on `{ company: 1, date: -1 }` supports queries filtering by company and sorting by date in the exact prefix order (ESR rule: Equality, Sort, Range)."
            },
            {
                "q": "How does React reconciliation (Fiber) work, and why is key prop necessary in lists?",
                "a": "React Fiber breaks rendering into incremental units of work that can be paused or prioritized. The `key` prop gives elements a stable identity between renders, allowing React to move or update existing DOM nodes rather than destroying and recreating the entire DOM tree."
            }
        ]
    },

    "dsa": {
        "id": "dsa",
        "title": "DSA & SDE Sheet Patterns",
        "badge": "Online Assessments",
        "icon": "bi-code-slash",
        "color": "#ec4899",
        "gradient": "linear-gradient(135deg, rgba(236, 72, 153, 0.2), rgba(124, 58, 237, 0.1))",
        "description": "Crush coding rounds with top patterns: Two Pointers, Sliding Window, Monotonic Stack, Dynamic Programming, and Graph Traversals.",
        "playlists": [
            {
                "title": "Blind 75 & NeetCode 150",
                "creator": "NeetCode",
                "url": "https://neetcode.io/practice",
                "tag": "Pattern Classification"
            },
            {
                "title": "Striver A2Z DSA Sheet",
                "creator": "take U forward (Striver)",
                "url": "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2",
                "tag": "SDE Standard"
            }
        ],
        "roadmap": [
            "1. Two Pointers & Sliding Window (Substrings, 3Sum, Container with most water)",
            "2. Fast & Slow Pointers (Cycle detection in Linked List, Middle element)",
            "3. Monotonic Stack & Deque (Next Greater Element, Daily Temperatures, Sliding Window Max)",
            "4. Trees & Graphs: BFS (Shortest path), DFS (Connected components), Topological Sort",
            "5. Dynamic Programming: 0/1 Knapsack, Longest Common Subsequence, Grid paths"
        ],
        "top_questions": [
            {
                "q": "What is the Sliding Window pattern, and when should you use it over nested loops?",
                "a": "Sliding Window maintains a window of elements defined by `left` and `right` pointers that expands or contracts based on constraints. It reduces O(N^2) subarray/substring problems to O(N) linear time by adding right elements and subtracting left elements incrementally."
            },
            {
                "q": "How do you detect a cycle in a linked list in O(1) space?",
                "a": "Floyd's Cycle-Finding Algorithm (Fast & Slow Pointers): slow moves 1 step, fast moves 2 steps. If a cycle exists, fast will inevitably lap and meet slow. If fast hits NULL, no cycle exists."
            }
        ]
    }
}


# ==============================================================================
# 2. COMPANY-SPECIFIC INTERVIEW INTELLIGENCE
# ==============================================================================

COMPANY_INTEL: Dict[str, Dict[str, Any]] = {
    "swiggy": {
        "name": "Swiggy",
        "badge": "FoodTech Unicorn",
        "difficulty": "Medium - Hard",
        "rounds": [
            {"round": "Round 1", "type": "Online Assessment (OA)", "focus": "2 DSA problems (Sliding Window, Trees) + 10 CS Fundamentals MCQs."},
            {"round": "Round 2", "type": "Machine Coding / Core Tech", "focus": "Design an in-memory delivery fee calculator or rate limiter in 90 minutes. Focus on clean OOP, interfaces, and unit tests."},
            {"round": "Round 3", "type": "Low-Level System Design (LLD)", "focus": "Design an Order Management System or Delivery Partner Assignment engine. DB schemas, Concurrency & Locking."},
            {"round": "Round 4", "type": "HM & Behavioral", "focus": "Customer-first mindset, handling failure in production, project deep-dive."}
        ],
        "what_they_grill": [
            "Real-time event streaming & WebSockets for live driver tracking",
            "Database transactions & race conditions (e.g. 2 users claiming the last item)",
            "Redis caching with TTLs and distributed locks (Redlock)",
            "Clean Architecture, SOLID principles, and modular microservices"
        ],
        "repeated_questions": [
            "How would you design a delivery partner matching algorithm based on location proximity?",
            "Explain how to prevent duplicate payment debits when order placement times out.",
            "Write an in-memory LRU Cache with O(1) get and put operations.",
            "Difference between optimistic vs pessimistic locking in relational databases."
        ],
        "insider_tips": "In the machine coding round, focus on runnable, modular code over perfection. Write clean test cases before time runs out."
    },

    "natwest": {
        "name": "NatWest Digital X",
        "badge": "Banking & FinTech Enterprise",
        "difficulty": "Medium",
        "rounds": [
            {"round": "Round 1", "type": "Coding & Tech Aptitude", "focus": "DSA (Arrays, Strings, HashMaps) and SQL queries (Joins, Aggregations)."},
            {"round": "Round 2", "type": "Core Framework & Problem Solving", "focus": "Deep-dive into Node.js/Python or Java, REST API design, Microservices, and Async programming."},
            {"round": "Round 3", "type": "Architecture & Cloud", "focus": "AWS cloud foundations, Docker, CI/CD pipelines, and secure API handling (OAuth2/JWT)."},
            {"round": "Round 4", "type": "Hiring Manager", "focus": "Financial compliance, risk mindset, Agile methodologies, team collaboration."}
        ],
        "what_they_grill": [
            "Secure API authentication, JWT token refresh mechanisms, and role-based access control (RBAC)",
            "ACID properties in banking systems, idempotent webhook processing",
            "Cloud-native deployment: Docker, AWS ECS/Lambda, microservices logging & monitoring",
            "Clean code, comprehensive automated testing (Jest, PyTest), and Git workflows"
        ],
        "repeated_questions": [
            "How do you design a bank account transfer system ensuring transactions never fail halfway?",
            "Explain how JWT authentication works and where you store tokens securely in a frontend application.",
            "Write a SQL query to find the 2nd highest salary / balance across departments.",
            "What is a Deadlock in multithreading/database, and how do you detect and resolve it?"
        ],
        "insider_tips": "Highlight security awareness (sanitizing inputs, preventing SQL injection, secrets management) — banking tech leads prioritize stability and security over flashy code."
    },

    "google": {
        "name": "Google",
        "badge": "Big Tech / Product Giant",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Online Coding Challenge", "focus": "2 complex algorithmic challenges (Graph traversal, DP, Binary Search)."},
            {"round": "Round 2 & 3", "type": "Data Structures & Algorithms", "focus": "Problem solving with high emphasis on time/space complexity, edge cases, and clean code on Google Docs."},
            {"round": "Round 4", "type": "System Design / Core Architecture", "focus": "Scalability, distributed caching, sharding, throughput vs latency calculations."},
            {"round": "Round 5", "type": "Googliness & Leadership", "focus": "Navigating ambiguity, constructive disagreement, mentoring, ethics."}
        ],
        "what_they_grill": [
            "Strict asymptotic complexity analysis (Big-O time and space)",
            "Edge case anticipation (empty inputs, integer overflow, extreme limits)",
            "Clean, communicative thought process (explaining before writing code)",
            "Distributed systems primitives: MapReduce, GFS, Consistent Hashing"
        ],
        "repeated_questions": [
            "Design Google Autocomplete / Typeahead suggestion system.",
            "Find the Median of Two Sorted Arrays in O(log(min(N, M))).",
            "Given a directed graph, detect if it contains a cycle and return the topological order.",
            "Design a URL Shortener with 100M URLs generated per day."
        ],
        "insider_tips": "Never jump straight into coding. Spend 5 minutes clarifying constraints, edge cases, and stating your brute-force approach first."
    },

    "amazon": {
        "name": "Amazon",
        "badge": "E-Commerce & Cloud Giant",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Online Assessment (OA)", "focus": "2 Coding problems + Amazon Work Simulation / Leadership Principles test."},
            {"round": "Round 2 & 3", "type": "Technical Coding + LP", "focus": "Trees, Graphs, DP, Heaps + 2 Leadership Principle questions per interviewer."},
            {"round": "Round 4", "type": "System Design & Object-Oriented Design", "focus": "Design Amazon Locker, Parking Lot, or TinyURL. Low-level classes and high-level scale."},
            {"round": "Round 5", "type": "Bar Raiser", "focus": "Toughest behavioral evaluation with an independent Amazon interviewer."}
        ],
        "what_they_grill": [
            "Amazon 16 Leadership Principles (Customer Obsession, Ownership, Bias for Action, Deliver Results)",
            "STAR method behavioral answers with quantified metrics (e.g. 'Reduced latency by 35%')",
            "Heap, Trie, BFS/DFS, and dynamic programming patterns",
            "Object-Oriented Design: Polymorphism, Design Patterns (Factory, Strategy, Observer)"
        ],
        "repeated_questions": [
            "Design an Amazon Shopping Cart with real-time stock reservation.",
            "Merge K Sorted Linked Lists in O(N log K) using a Min-Heap.",
            "Course Schedule II (Topological Sort with Kahn's Algorithm).",
            "Tell me about a time you had a disagreement with your team lead and how you handled it."
        ],
        "insider_tips": "Half of your interview score at Amazon is behavioral (LP). Have 4-5 solid STAR-method stories prepared from your past projects."
    },

    "nvidia": {
        "name": "NVIDIA",
        "badge": "AI & Semiconductor Titan",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Coding & Core CS Test", "focus": "Data structures, memory management, C++/Python internals, pointers."},
            {"round": "Round 2", "type": "Technical Deep Dive", "focus": "Multithreading, concurrency, GPU concepts, OS fundamentals (Paging, Virtual Memory)."},
            {"round": "Round 3", "type": "System Engineering & Algorithms", "focus": "Bit manipulation, cache coherence, pipeline optimization, matrix multiplication."},
            {"round": "Round 4", "type": "Managerial", "focus": "Passion for AI acceleration, performance profiling, problem-solving persistence."}
        ],
        "what_they_grill": [
            "Low-level memory optimization: cache locality, memory leaks, pointers vs references",
            "Multithreading: Mutexes, Semaphores, Race conditions, Thread pools",
            "C++17/20 or modern Python performance profiling (NumPy vectorization, PyTorch tensors)",
            "Operating Systems: Virtual memory, TLB, Page faults, Context switching"
        ],
        "repeated_questions": [
            "Explain how Virtual Memory and Page Tables work in modern operating systems.",
            "Implement a thread-safe Queue in C++ or Python.",
            "What is False Sharing in CPU caches and how do you prevent it?",
            "Optimize matrix multiplication for cache locality (Row-major vs Column-major traversal)."
        ],
        "insider_tips": "NVIDIA interviewers care intensely about hardware awareness — know why cache misses happen and how memory bandwidth affects execution time."
    },

    "startup": {
        "name": "Fast-Paced Startup (YC / Seed / Series A)",
        "badge": "High-Growth Startup",
        "difficulty": "Medium",
        "rounds": [
            {"round": "Round 1", "type": "Take-Home Assignment / Live Pair Programming", "focus": "Build a real mini-feature (e.g. Kanban board, file uploader with presigned URLs, authentication) within 48 hours."},
            {"round": "Round 2", "type": "Code Review & Grilling", "focus": "Founder or CTO grills you on your take-home code choices, edge cases, error handling, and architecture."},
            {"round": "Round 3", "type": "System & Practical Problem Solving", "focus": "How would you debug a 500 error in production? How do you scale MongoDB when queries slow down?"},
            {"round": "Round 4", "type": "Founder / Culture Fit", "focus": "Can you ship independently? Do you have high agency? Speed of execution."}
        ],
        "what_they_grill": [
            "Ability to ship end-to-end features without babysitting",
            "Real-world debugging (Chrome DevTools, Postman, server logs, network requests)",
            "Pragmatic tech choices over over-engineering (shipping in days vs months)",
            "Full Stack breadth (connecting React frontend to Express/FastAPI with a DB)"
        ],
        "repeated_questions": [
            "How do you handle file uploads directly to S3/Cloud Storage using Presigned URLs?",
            "A query is taking 8 seconds in MongoDB/PostgreSQL in production. What exact steps do you take to fix it?",
            "Walk me through your most complex project: what was the hardest bug you personally resolved?",
            "How do you implement optimistic UI updates in React so the app feels instant?"
        ],
        "insider_tips": "Startups care about execution and initiative. Talk about things you built, deployed, and broke, and demonstrate that you don't need handholding."
    },

    "microsoft": {
        "name": "Microsoft",
        "badge": "Enterprise & Cloud Giant",
        "difficulty": "Medium - Hard",
        "rounds": [
            {"round": "Round 1", "type": "Online Assessment (OA)", "focus": "2 algorithmic problems (Strings, Arrays, Dynamic Programming)."},
            {"round": "Round 2 & 3", "type": "Technical Coding", "focus": "Trees, Graphs, Hash Maps, OOP design, and code maintainability."},
            {"round": "Round 4", "type": "System Design / Core Architecture", "focus": "Designing Azure-scale systems, telemetry, caching, and resiliency."},
            {"round": "Round 5", "type": "As-Appropriate (AA) / Manager", "focus": "Growth mindset, handling customer feedback, technical deep-dive."}
        ],
        "what_they_grill": [
            "Data structures: Binary Trees, Hash Tables, and string parsing algorithms",
            "OOP principles, clean interfaces, and robust error handling",
            "Scalability, microservices isolation, and fault tolerance",
            "Growth mindset and learning from past architectural failures"
        ],
        "repeated_questions": [
            "Design a distributed rate limiter or URL shortener at scale.",
            "Two Sum & Subarray Sum Equals K.",
            "Reverse Words in a String with in-place pointer manipulation.",
            "Number of Islands with multi-grid DFS/BFS."
        ],
        "insider_tips": "Microsoft loves modular, production-ready code with good variable naming and clean unit test mentality."
    },

    "meta": {
        "name": "Meta (Facebook)",
        "badge": "Social & AI Superpower",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Technical Phone Screen", "focus": "2 coding problems in 45 minutes on CoderPad. Speed and clean execution are paramount."},
            {"round": "Round 2 & 3", "type": "Onsite Coding (Ninja)", "focus": "BFS/DFS, Tree Traversals, Two Pointers, and Binary Search with 0 bugs."},
            {"round": "Round 4", "type": "System Design (Pirate)", "focus": "Design Messenger, Newsfeed, or Instagram Stories. Focus on high write throughput & fanout."},
            {"round": "Round 5", "type": "Behavioral (Jedi)", "focus": "Move fast, resolve conflicts, and drive high-impact initiatives."}
        ],
        "what_they_grill": [
            "Coding speed: You must solve 2 medium/hard problems bug-free in 45 minutes",
            "Binary Tree Vertical Order Traversal and Lowest Common Ancestor",
            "Subarray Sum Equals K (Prefix sum hash table pattern)",
            "System Design: Fanout on write vs Fanout on read, distributed caching"
        ],
        "repeated_questions": [
            "Binary Tree Vertical Order Traversal.",
            "Minimum Remove to Make Valid Parentheses.",
            "Subarray Sum Equals K.",
            "Design Instagram Stories or Newsfeed Timeline."
        ],
        "insider_tips": "At Meta, coding speed and 0 syntax bugs are non-negotiable. Aim to finish the first question in 18 minutes."
    },

    "apple": {
        "name": "Apple",
        "badge": "Hardware & Ecosystem Titan",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Recruiter & Tech Screen", "focus": "Language internals (C++/Swift/Python/Java), pointers, memory."},
            {"round": "Round 2 & 3", "type": "Domain Coding & Algorithms", "focus": "LRU Cache, Matrix simulation, concurrency, low-level optimization."},
            {"round": "Round 4", "type": "Architecture & System Engineering", "focus": "Low-latency API design, local caching, client-server sync."},
            {"round": "Round 5", "type": "Team & Cross-Functional Fit", "focus": "Obsession with detail, user privacy, and product perfection."}
        ],
        "what_they_grill": [
            "Deep language fundamentals: memory allocation, concurrency, race conditions",
            "Clean algorithmic reasoning: LRU Cache, Spiral Matrix, Linked Lists",
            "Security & privacy by design",
            "Attention to edge cases and defensive programming"
        ],
        "repeated_questions": [
            "Implement an LRU Cache with strict O(1) performance.",
            "Traverse a matrix in Spiral Order.",
            "Reverse a Linked List in-place with iterative pointers.",
            "Explain how client-side encryption protects user data."
        ],
        "insider_tips": "Apple teams are highly autonomous. Tailor your answers directly to the specific team's product domain."
    },

    "netflix": {
        "name": "Netflix",
        "badge": "Streaming & Chaos Engineering Pioneer",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Technical Screening", "focus": "High-throughput data streaming, concurrency, and async architecture."},
            {"round": "Round 2", "type": "Deep System Design", "focus": "Video transcoding pipelines, CDN origin shielding, and Chaos Monkey resiliency."},
            {"round": "Round 3", "type": "Advanced Coding", "focus": "Two Heaps, Sliding Window Max, Monotonic Queues, and O(1) Data Structures."},
            {"round": "Round 4", "type": "Culture & Leadership", "focus": "Netflix Culture Memo: Freedom & Responsibility, Context not Control."}
        ],
        "what_they_grill": [
            "Fault tolerance: How does your system survive when AWS us-east-1 goes down?",
            "Sliding Window Maximum and Two-Heap stream median tracking",
            "CDN edge caching, HLS video chunking, and adaptive bitrate streaming",
            "High autonomy and ownership in production"
        ],
        "repeated_questions": [
            "Find Median from Continuous Data Stream.",
            "Sliding Window Maximum using Monotonic Deque.",
            "Design an Adaptive Bitrate Video Streaming Pipeline.",
            "How do you design a circuit breaker to prevent cascading microservice outages?"
        ],
        "insider_tips": "Netflix only hires senior engineers. Focus on operational excellence, fault tolerance, and self-healing systems."
    },

    "uber": {
        "name": "Uber",
        "badge": "Mobility & Logistics Tech",
        "difficulty": "Hard",
        "rounds": [
            {"round": "Round 1", "type": "Coding OA", "focus": "2 Graph / Grid problems (BFS, Shortest Path)."},
            {"round": "Round 2 & 3", "type": "Data Structures & Algorithms", "focus": "Multi-source BFS, Priority Queues, Interval Merging."},
            {"round": "Round 4", "type": "System Design", "focus": "Proximity location indexing, Geohashing, real-time dispatch engine."},
            {"round": "Round 5", "type": "Engineering Manager", "focus": "High-scale outage resolution, cross-team collaboration."}
        ],
        "what_they_grill": [
            "Geospatial indexing: Geohash vs Google S2 vs QuadTree",
            "Multi-source BFS (e.g. As Far from Land as Possible)",
            "Real-time driver location ingestion and WebSockets",
            "Microservices resilience and distributed tracing (Jaeger)"
        ],
        "repeated_questions": [
            "Design a real-time driver dispatch service matching riders in <1s.",
            "As Far from Land as Possible (Multi-source BFS).",
            "Meeting Rooms II (Min-Heap greedy interval sorting).",
            "Copy List with Random Pointer."
        ],
        "insider_tips": "Understand why relational DBs fail for 2.5M GPS pings/sec and how in-memory Redis Geohashes solve spatial lookups."
    },

    "flipkart": {
        "name": "Flipkart",
        "badge": "E-Commerce Tech Leader",
        "difficulty": "Medium - Hard",
        "rounds": [
            {"round": "Round 1", "type": "Machine Coding Round", "focus": "Design an in-memory inventory management or flash sale queue in 90 mins."},
            {"round": "Round 2", "type": "Data Structures & Algorithms", "focus": "Merge Intervals, LRU Cache, Binary Search, DP."},
            {"round": "Round 3", "type": "System Design", "focus": "Flash Sale architecture (Big Billion Days), order checkout consistency."},
            {"round": "Round 4", "type": "Hiring Manager", "focus": "Customer obsession, high-traffic crisis handling."}
        ],
        "what_they_grill": [
            "Handling 100x flash sale traffic spikes without inventory overselling",
            "Clean OOP and modular machine coding with unit tests",
            "Distributed locks and database isolation levels",
            "Kafka event streaming and asynchronous payment webhooks"
        ],
        "repeated_questions": [
            "Design a Flash Sale system preventing inventory overselling.",
            "Merge Intervals & Trapping Rain Water.",
            "Write an in-memory LRU Cache.",
            "How do you ensure message delivery in Kafka during broker crashes?"
        ],
        "insider_tips": "In the machine coding round, modular class separation, clean variable names, and working test cases count for 70% of the score."
    }
}


def get_company_intel(company_name: str) -> Dict[str, Any]:
    """
    Look up company interview intelligence.
    If company is not pre-indexed, generates a smart, tailored profile based on company type.
    Always enriches with real LeetCode problems (from liquidslr dataset) and ByteByteGo System Design cases.
    """
    comp_clean = (company_name or "").lower().strip()
    data: Dict[str, Any] = {}

    # Exact or alias match
    found = False
    for key, val in COMPANY_INTEL.items():
        if key in comp_clean or comp_clean in key:
            data = dict(val)
            found = True
            break

    if not found:
        # Check for known tech conglomerates / keywords
        if any(k in comp_clean for k in ["bank", "capital", "financial", "insurance", "credit"]):
            data = {
                "name": company_name.title(),
                "badge": "Banking & FinTech Enterprise",
                "difficulty": "Medium",
                "rounds": COMPANY_INTEL["natwest"]["rounds"],
                "what_they_grill": COMPANY_INTEL["natwest"]["what_they_grill"],
                "repeated_questions": COMPANY_INTEL["natwest"]["repeated_questions"],
                "insider_tips": "Focus on data security, SQL transaction integrity, and robust error handling."
            }
        else:
            # Default to High-Growth Tech Startup template
            data = {
                "name": company_name.title(),
                "badge": "Technology & Product Company",
                "difficulty": "Medium",
                "rounds": COMPANY_INTEL["startup"]["rounds"],
                "what_they_grill": COMPANY_INTEL["startup"]["what_they_grill"],
                "repeated_questions": COMPANY_INTEL["startup"]["repeated_questions"],
                "insider_tips": COMPANY_INTEL["startup"]["insider_tips"]
            }

    # Enrich with real LeetCode problems (open free links) and ByteByteGo system design
    data["leetcode_problems"] = get_company_leetcode_problems(company_name)
    data["system_design_cases"] = list_system_design_cases()[:3]
    return data


def list_prep_tracks() -> List[Dict[str, Any]]:
    """Returns list of all available master prep tracks."""
    return [
        {
            "id": t["id"],
            "title": t["title"],
            "badge": t["badge"],
            "icon": t["icon"],
            "color": t["color"],
            "description": t["description"],
            "playlists_count": len(t["playlists"]),
            "questions_count": len(t["top_questions"])
        }
        for t in PREP_TRACKS.values()
    ]


def list_featured_companies() -> List[Dict[str, Any]]:
    """Returns list of pre-configured company intelligence profiles."""
    return [
        {
            "key": k,
            "name": v["name"],
            "badge": v["badge"],
            "difficulty": v["difficulty"],
            "rounds_count": len(v["rounds"]),
            "questions_count": len(v["repeated_questions"])
        }
        for k, v in COMPANY_INTEL.items()
    ]
