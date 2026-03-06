#!/bin/sh
set -e

API_URL="${API_URL:-http://api:8000}"
SEED_COUNT="${SEED_COUNT:-10}"
LOOP_DELAY="${LOOP_DELAY:-0.3}"
LOOP_DURATION="${LOOP_DURATION:-0}"

priorities="low medium high"
statuses="todos in_progress done"

rand_pick() {
  echo "$1" | tr ' ' '\n' | shuf -n 1
}

echo "Waiting for API to be ready..."
until curl -sf "${API_URL}/" > /dev/null 2>&1; do
  sleep 2
done
echo "API is ready."

# --- Phase 1: Seed tasks ---
echo "Seeding ${SEED_COUNT} tasks..."
for i in $(seq 1 "$SEED_COUNT"); do
  priority=$(rand_pick "$priorities")
  curl -sf -X POST "${API_URL}/api/v1/tasks/" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"Task ${i}\", \"description\": \"Auto-generated task ${i}\", \"priority\": \"${priority}\"}" \
    > /dev/null
done
echo "Seeded ${SEED_COUNT} tasks."

# --- Phase 2: Exercise all endpoints ---
echo "Exercising endpoints..."

# List with filters
curl -sf "${API_URL}/api/v1/tasks/" > /dev/null
curl -sf "${API_URL}/api/v1/tasks/?priority_filter=high" > /dev/null
curl -sf "${API_URL}/api/v1/tasks/?status_filter=todos" > /dev/null

# Get individual tasks (populates cache)
for i in $(seq 1 "$SEED_COUNT"); do
  curl -sf "${API_URL}/api/v1/tasks/${i}" > /dev/null 2>&1 || true
done
# Hit again for cache hits
for i in $(seq 1 "$SEED_COUNT"); do
  curl -sf "${API_URL}/api/v1/tasks/${i}" > /dev/null 2>&1 || true
done

# Update some tasks
for i in $(seq 1 3); do
  s=$(rand_pick "$statuses")
  p=$(rand_pick "$priorities")
  curl -sf -X PATCH "${API_URL}/api/v1/tasks/${i}" \
    -H "Content-Type: application/json" \
    -d "{\"status\": \"${s}\", \"priority\": \"${p}\"}" \
    > /dev/null 2>&1 || true
done

# Trigger a report
curl -sf -X POST "${API_URL}/api/v1/tasks/report" > /dev/null 2>&1 || true

# 404 traffic
curl -sf "${API_URL}/api/v1/tasks/99999" > /dev/null 2>&1 || true

echo "Endpoint exercise complete."

# --- Phase 3: Continuous load loop ---
if [ "$LOOP_DURATION" = "0" ]; then
  echo "LOOP_DURATION=0, running load loop indefinitely..."
else
  echo "Running load loop for ${LOOP_DURATION}s..."
fi

end_time=0
if [ "$LOOP_DURATION" != "0" ]; then
  end_time=$(($(date +%s) + LOOP_DURATION))
fi

while true; do
  if [ "$end_time" -ne 0 ] && [ "$(date +%s)" -ge "$end_time" ]; then
    break
  fi

  # Mix of requests
  curl -sf "${API_URL}/api/v1/tasks/" > /dev/null 2>&1 &
  task_id=$((RANDOM % SEED_COUNT + 1))
  curl -sf "${API_URL}/api/v1/tasks/${task_id}" > /dev/null 2>&1 &
  curl -sf "${API_URL}/" > /dev/null 2>&1 &
  wait
  sleep "$LOOP_DELAY"
done

echo "Traffic generation complete."
