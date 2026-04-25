# Feature Flag Project — Control Flow Documentation

This document outlines the execution paths and data flow for both the Backend (Python) and the Frontend (Web UI).

---

## 🏗️ Backend Control Flow

The backend follows a layered architecture: **API → Manager → Engine → Storage**.

### 1. Initialization Flow
When the server starts (`api/server.py:main`):
1. **Store Initialization**: `JsonFileStore` is created, pointing to `configs/flags.json`.
2. **Manager Initialization**: `FlagManager` is created with the store.
   - It calls `store.load()` immediately to populate its memory snapshot.
   - It starts a background thread (`store.watch`) to listen for file changes.
3. **App Creation**: FastAPI app is created, and the `FlagManager` instance is injected into the routes.

### 2. Evaluation Request Flow
When a client (SDK or Web UI) calls `POST /flags/{key}/eval`:
1. **FastAPI Route**: Receives the `EvalContextSchema`.
2. **Context Creation**: Converts the schema into a `core.models.EvaluationContext` object.
3. **Manager.evaluate()**:
   - Retrieves the `FeatureFlag` object from the current memory snapshot.
   - If the flag is missing, returns `None`.
   - Calls the **Engine**.
4. **Engine.evaluate()**:
   - Runs the **7-step pipeline**: Kill switch → Env gate → User target → Group target → Rule groups → Rollout % → Default.
   - Calculates deterministic buckets using `hashlib.sha256`.
   - Assigns a **Variant** if configured for A/B testing.
   - Returns an `EvaluationResult`.
5. **Audit Logging**: The Manager records the result in its local audit log buffer.
6. **Response**: FastAPI serializes the `EvaluationResult` to JSON.

### 3. Update/Write Flow
When a user calls `PUT /flags/{key}`:
1. **Manager.put()**:
   - Acquires a **Write Lock** (`threading.Lock`).
   - Creates a new dictionary snapshot (Copy-on-Write).
   - Calls `store.save()` to persist the change to `flags.json`.
   - Replaces the `_snapshot` reference atomically.
   - Notifies any registered **Observers**.
2. **File Hot-Reload**: If `flags.json` is edited manually on disk, the `JsonFileStore` watcher detects the mtime change and triggers `manager.reload()`.

---

## 🎨 Frontend Control Flow

The frontend is a **Single Page Application (SPA)** using **Vanilla JavaScript** and **fetch()**.

### 1. Page Load Flow
1. **DOM Content Loaded**:
   - Calls `fetchFlags()`: Hits `GET /flags`, stores data in global `allFlags`, and calls `renderFlags()`.
   - Calls `checkHealth()`: Hits `GET /health` and updates the pulse indicator in the header.
2. **Interval Timer**: Every 15 seconds, `checkHealth()` is re-executed to ensure the backend is alive.

### 2. Rendering Flow
`renderFlags()` performs the following:
1. Clears the `#flags-container`.
2. Loops through the `allFlags` object.
3. Generates HTML cards using template literals.
4. Logic handles:
   - Status badge colors (Enabled/Disabled).
   - Flag type pills (Release/Experiment/etc.).
   - Rollout bar percentage width.
   - Special badges for Rules or A/B variants.

### 3. Interactive Actions Flow (User-Driven)

#### Toggle Flag (Enable/Disable)
- User clicks the **Toggle Switch**.
- `toggleFlag(key)` finds the flag in the local state, flips the `enabled` boolean.
- Sends `PUT /flags/{key}` with the full updated object.
- On success, re-fetches all flags to sync state and shows a Success Toast.

#### Evaluate Flag (Testing)
- User clicks the **Lightning Bolt (⚡)** icon.
- `openEvalModal(key)` pops up the modal.
- User clicks "Evaluate" → `handleEvalSubmit(event)`.
- Sends `POST /flags/{key}/eval` with User ID, Env, and Attributes.
- The response is displayed in the "Evaluation Result" section of the modal (Reason, Variant, Payload).

#### Create/Edit Flag
- User submits the **Create Form**.
- `handleFlagSubmit(e)` parses inputs.
- Validates the **Variants JSON** if provided.
- Sends either `POST /flags` (for new) or `PUT /flags/{key}` (for edits).
- On success, closes the modal and refreshes the dashboard.

#### Audit Log
- User clicks the **List (📋)** icon.
- `openAuditModal(key)` hits `GET /flags/{key}/audit`.
- Backend returns a list of evaluation history.
- Frontend renders the results chronologically in the modal.

---

## 🔄 Data Synchronization Summary
- **Backend → Disk**: Immediate via `store.save()` on any write.
- **Disk → Backend**: Auto-reloads via file polling on any manual change.
- **Backend → Frontend**: Manual refresh via `Reload` button, or automatic refresh after any Dashboard-driven Write operation.
- **Frontend → Backend**: Real-time via REST endpoints.
