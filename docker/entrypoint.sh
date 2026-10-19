#!/usr/bin/env bash
#
# Runs manapool once at startup, then daily at RUN_AT_UTC, writing the latest
# JSON to $WEB_ROOT/index.html. nginx serves that directory on port 80, along
# with the same result as Prometheus text metrics at /metrics.

set -euo pipefail

WEB_ROOT="${WEB_ROOT:-/var/www/html}"
RUN_AT_UTC="${RUN_AT_UTC:-01:00}"

mkdir -p "$WEB_ROOT"

# Answer immediately, before the first run finishes. Both placeholders go
# through the same rendering path as a real run, so the served bodies are
# always valid JSON / Prometheus exposition.
if [[ ! -f "$WEB_ROOT/index.html" ]]; then
    printf '%s\n' '{"status":"pending","message":"first run has not completed yet"}' \
        > "$WEB_ROOT/index.html"
fi
if [[ ! -f "$WEB_ROOT/metrics" ]]; then
    manapool-metrics "$WEB_ROOT/index.html" > "$WEB_ROOT/metrics"
fi

write_metrics() {
    # Derive /metrics from the JSON we just published, so the day's single
    # manapool run (and its claim) feeds both endpoints.
    if manapool-metrics "$WEB_ROOT/index.html" > "$WEB_ROOT/metrics.tmp" \
        2> "$WEB_ROOT/.metrics-stderr"; then
        mv "$WEB_ROOT/metrics.tmp" "$WEB_ROOT/metrics"
    else
        rm -f "$WEB_ROOT/metrics.tmp"
        echo "[utc $(date -u +%FT%TZ)] manapool-metrics failed; keeping previous /metrics" >&2
        cat "$WEB_ROOT/.metrics-stderr" >&2 || true
    fi
    rm -f "$WEB_ROOT/.metrics-stderr"
}

run_once() {
    local tmp="$WEB_ROOT/index.html.tmp"
    local code=0

    echo "[utc $(date -u +%FT%TZ)] refreshing manapool status" >&2
    manapool --json > "$tmp" 2> "$WEB_ROOT/.stderr" || code=$?

    # --json always emits one JSON object; keep it even when the exit code is
    # non-zero (already claimed / not eligible / claim failure are all useful
    # to publish). Only fall back to the previous copy if nothing was written.
    if [[ -s "$tmp" ]]; then
        mv "$tmp" "$WEB_ROOT/index.html"
        write_metrics
    else
        rm -f "$tmp"
        echo "[utc $(date -u +%FT%TZ)] no output produced (exit ${code}); keeping previous copy" >&2
    fi

    if [[ $code -ne 0 ]]; then
        echo "[utc $(date -u +%FT%TZ)] manapool exited with ${code}" >&2
        cat "$WEB_ROOT/.stderr" >&2 || true
    fi
    rm -f "$WEB_ROOT/.stderr"
}

seconds_until() {
    # Seconds from now until the next occurrence of $1 (HH:MM, UTC).
    local target="$1"
    local now next
    now=$(date -u +%s)
    next=$(date -u -d "$target" +%s)
    if (( next <= now )); then
        next=$(date -u -d "tomorrow $target" +%s)
    fi
    echo $(( next - now ))
}

nginx -g 'daemon off;' &
nginx_pid=$!

shutdown() {
    kill -TERM "$nginx_pid" 2>/dev/null || true
    wait "$nginx_pid" 2>/dev/null || true
    exit 0
}
trap shutdown TERM INT

while true; do
    run_once
    delay=$(seconds_until "$RUN_AT_UTC")
    echo "[utc $(date -u +%FT%TZ)] next run in ${delay}s (at ${RUN_AT_UTC} UTC)" >&2
    sleep "$delay" &
    wait $! || true
done
