#!/usr/bin/env bash
# fetch_gold.sh — fetch spot gold price from goldapi.io
# Requires: curl, jq
# Set GOLDAPI_KEY in the script or via environment

GOLDAPI_KEY="your_key"  # replace with your key
CACHE="/tmp/gold_cache.json"
LOCK="/tmp/gold_fetch.lock"
MAX_AGE=55   # seconds

log() { echo "[gold] $*" >&2; }

# Check if cache is fresh
cache_fresh() {
    [[ -f "$CACHE" ]] || return 1
    local age=$(( $(date +%s) - $(stat -c %Y "$CACHE" 2>/dev/null || echo 0) ))
    [[ $age -lt $MAX_AGE ]]
}

# Fetch gold from API
fetch_gold() {
    curl -sf --max-time 8 \
        -H "x-access-token: ${GOLDAPI_KEY}" \
        -H "Content-Type: application/json" \
        "https://www.goldapi.io/api/XAU/EUR"
}

# Serve cache if fresh
if cache_fresh; then
    cat "$CACHE"
    exit 0
fi

# Lock to prevent parallel fetches
if [[ -f "$LOCK" ]]; then
    [[ -f "$CACHE" ]] && cat "$CACHE" && exit 0
    sleep 2
fi
touch "$LOCK"
trap 'rm -f "$LOCK"' EXIT

raw=$(fetch_gold)
if [[ $? -ne 0 ]] || [[ -z "$raw" ]]; then
    log "Failed to fetch XAU"
    [[ -f "$CACHE" ]] && cat "$CACHE" || echo "{}"
    exit 1
fi

# Parse JSON with jq
parsed=$(echo "$raw" | jq -c '{
    sym: "AU",
    name: "GOLD",
    price: (.price | tonumber),
    delta_eur: ((.price | tonumber) - (.prev_close_price | tonumber)),
    delta_pct: (.chp | tonumber)
}')

echo "$parsed" > "$CACHE"
cat "$CACHE"
