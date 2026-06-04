# Architectural Choices

## Decision 1 — Detection Model: YOLOv8s

# Options Considered
- YOLOv8n (nano) — fastest, least accurate
- YOLOv8s (small) — balanced speed and accuracy
- YOLOv8m (medium) — most accurate, too slow on CPU
- RT-DETR — transformer based, requires GPU
- MediaPipe — good for mobile, less accurate for retail

# What AI Suggested
Claude suggested YOLOv8s as a starting point for CPU-only
inference in retail environments, noting it achieves ~37 mAP
on COCO while running at acceptable speed without a GPU.
It also suggested considering RT-DETR for better accuracy
but noted the GPU requirement would be a problem.

# What I Chose and Why
YOLOv8s. The machine running this has 8GB RAM and no GPU.
YOLOv8n was considered but its accuracy drops noticeably
in crowded scenes and partial occlusion cases. YOLOv8s
gives a good tradeoff — fast enough on CPU with
frame skipping, accurate enough for retail crowd density.

# What Would Change My Decision
If a GPU was available I would use YOLOv8m or RT-DETR for
better handling of partial occlusion and group entry cases.

---

# Decision 2 — Event Schema Design

# Options Considered
- Flat schema — all fields at top level
- Nested schema — metadata in separate object
- Minimal schema — only required fields
- Extended schema — include raw bbox coordinates

# What AI Suggested
Claude suggested the nested metadata approach from the
problem statement, noting it allows extending the schema
without breaking existing consumers. It also suggested
including raw bbox in metadata for debugging purposes.

# What I Chose and Why
I followed the problem statement schema exactly with one
addition — I did not include raw bbox coordinates in
production events. Bbox data would double the event file
size and is not needed by any API endpoint. Confidence
score already captures detection quality sufficiently.

# Tradeoff
Without bbox data, debugging specific detection errors
requires re-running the pipeline. With bbox data, you
could replay and visualize exactly what the model saw.
Given the 48 hour constraint I prioritized event volume
efficiency over debuggability.

---

# Decision 3 — API Storage: SQLite vs PostgreSQL

# Options Considered
- SQLite — embedded, zero config, single file
- PostgreSQL — production grade, requires container
- Redis — fast but no persistent complex queries
- MongoDB — flexible schema but overkill for this

# What AI Suggested
Claude strongly suggested PostgreSQL for production
readiness, noting it handles concurrent writes better
and scales to 40 stores. It provided a complete
docker-compose setup with a postgres container.

# What I Chose and Why
SQLite. I disagreed with the AI suggestion for this
specific challenge for three reasons:

1. Single store, single day data — SQLite handles
   millions of rows comfortably
2. Removing the postgres container simplifies the
   docker-compose setup — one less thing to break
   during reviewer evaluation
3. The acceptance gate requires docker compose up
   to work on a clean machine — SQLite has zero
   external dependencies

# What Would Change My Decision
At 40 live stores sending events in real time,
SQLite would hit write contention issues. PostgreSQL
with connection pooling would be the right choice
at that scale. For this challenge SQLite is the
pragmatic choice.

---

## Decision 4 — Tracker: IOU vs ByteTrack

### Options Considered
- ByteTrack — state of the art multi object tracker
- DeepSORT — appearance + motion based tracking
- StrongSORT — improved DeepSORT
- Custom IOU tracker — simple distance based

### What AI Suggested
Claude suggested ByteTrack as the industry standard
for retail person tracking, noting it handles occlusion
and crowded scenes better than IOU tracking. It provided
a complete ByteTrack integration example.

### What I Chose and Why
Custom IOU tracker. ByteTrack was evaluated but not
chosen for three reasons:

1. The challenge footage had relatively low crowd
   density — IOU tracking is sufficient when people
   are not densely packed
2. Limited development time — IOU tracker is simpler
   to debug and explain in follow-up questions
3. 2 minute clips mean fewer long term tracking
   challenges that ByteTrack solves

### What Would Change My Decision
For production deployment at 40 stores with high
crowd density, ByteTrack combined with OSNet
appearance based ReID would be the right choice.
ByteTrack handles occlusion and ID switching better
which matters when stores are busy.

---

## Decision 5 — Re-entry Detection Strategy

### Options Considered
- Full ReID model (OSNet/torchreid)
- Bounding box similarity + time window
- Appearance embedding comparison
- Position based matching only

### What AI Suggested
Claude suggested using OSNet for appearance based
ReID, noting it provides the most accurate re-entry
detection by comparing visual features of people.

### What I Chose and Why
Bounding box similarity + 5 minute time window.
For 2 minute clips, full ReID adds significant
complexity without proportional benefit. Our approach:

1. Store exit bounding box and timestamp
2. When new person appears at entry
3. Compare bounding box size and position
4. If similar within 5 minutes → REENTRY event

This is explainable, debuggable, and sufficient
for the clip duration provided.

### Tradeoff
Full ReID would handle cases where the same person
re-enters from a different angle. Our approach may
miss these. For production, OSNet ReID would be
the right investment.