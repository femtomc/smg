#!/usr/bin/env bash
# parity_check.sh -- verify SMG's compact-format structural invariants.
# Run from a directory with an initialised .smg/ project.
set -euo pipefail

FAIL=0
pass() { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1"; FAIL=1; }

echo "=== SMG parity check ==="

# Ensure we have a project
if [ ! -d .smg ]; then
    echo "Error: no .smg/ directory. Run 'smg init && smg scan src/' first."
    exit 1
fi

# Seed a few nodes if graph is empty
NODE_COUNT=$(smg status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['nodes'])" 2>/dev/null || echo "0")
if [ "$NODE_COUNT" = "0" ]; then
    echo "Warning: empty graph. Add nodes with 'smg scan' for a meaningful check."
fi

# --- Listing commands to check ---
LISTING_CMDS=(
    "smg list --limit 5"
    "smg status"
)

for CMD in "${LISTING_CMDS[@]}"; do
    LABEL="$CMD"

    # 1. No box-drawing characters
    if $CMD 2>/dev/null | grep -qP '[┏━┃┗┓┛┡┩│┐└┬┼─]'; then
        fail "$LABEL: box-drawing characters found"
    else
        pass "$LABEL: no box-drawing"
    fi

    # 2. No ANSI escape sequences
    if $CMD 2>/dev/null | grep -qP '\x1b\['; then
        fail "$LABEL: ANSI escapes found"
    else
        pass "$LABEL: no ANSI escapes"
    fi

    # 3. No trailing spaces
    if $CMD 2>/dev/null | grep -qP ' $'; then
        fail "$LABEL: trailing spaces found"
    else
        pass "$LABEL: no trailing spaces"
    fi
done

# 4. Header row is lowercase (check first line of smg list)
HEADER=$(smg list --limit 1 2>/dev/null | head -1)
if echo "$HEADER" | grep -qP '[A-Z]'; then
    fail "smg list: header contains uppercase"
else
    pass "smg list: header is lowercase"
fi

# 5. Separator row pattern (second line of smg list)
SEPARATOR=$(smg list --limit 1 2>/dev/null | sed -n '2p')
if echo "$SEPARATOR" | grep -qP '^[-\s]+$'; then
    pass "smg list: separator is dashes and spaces"
else
    fail "smg list: separator has unexpected chars"
fi

# 6. Flag surface: --json, --limit, --full
for FLAG in "--json" "--limit" "--full"; do
    if smg list --help 2>/dev/null | grep -q -- "$FLAG"; then
        pass "smg list --help: $FLAG present"
    else
        fail "smg list --help: $FLAG missing"
    fi
done

# 7. Footer wording (force truncation)
FOOTER=$(smg list --limit 1 2>/dev/null | tail -1)
if echo "$FOOTER" | grep -qF 'use --limit 0 for all, --json for machine-readable'; then
    pass "smg list: footer wording correct"
else
    # May not have enough nodes to trigger footer
    if [ "$NODE_COUNT" -le "1" ]; then
        pass "smg list: footer not applicable (<=1 node)"
    else
        fail "smg list: footer wording incorrect: $FOOTER"
    fi
fi

# 8. Search surface
if smg search --help 2>/dev/null | grep -q -- "--json"; then
    pass "smg search --help: --json present"
else
    fail "smg search --help: --json missing"
fi
if smg search --help 2>/dev/null | grep -q -- "--limit"; then
    pass "smg search --help: --limit present"
else
    fail "smg search --help: --limit missing"
fi
if smg search --help 2>/dev/null | grep -q -- "--full"; then
    pass "smg search --help: --full present"
else
    fail "smg search --help: --full missing"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "All checks passed."
else
    echo "Some checks failed."
    exit 1
fi
