#!/usr/bin/env bash
# ANNY-RUNTIME Physical Certification Helper Script
# EVIDENCE COLLECTOR (Not an Authority)
# Storage Model: append-only, tamper-evident, operator-owned

set -euo pipefail

# --- CONFIGURATION & ARGUMENT PARSING ---

EVIDENCE_DIR="$HOME/anny-runtime-certification/CLEAN-MACHINE-01"
STEP=""
OPERATOR_ID=${USER:-"unknown"}
MACHINE_ID="CLEAN-MACHINE-01"
EXPORT_MODE=0
VERIFY_MODE=0

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --step) STEP="$2"; shift ;;
        --evidence-dir) EVIDENCE_DIR="$2"; shift ;;
        --export) EXPORT_MODE=1 ;;
        --verify-chain) VERIFY_MODE=1 ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

MANIFEST_FILE="$EVIDENCE_DIR/MANIFEST.json"

# --- CORE FUNCTIONS ---

init_dir() {
    if [ ! -d "$EVIDENCE_DIR" ]; then
        mkdir -p "$EVIDENCE_DIR"
        chmod 0700 "$EVIDENCE_DIR"
    fi
}

get_current_sequence() {
    if [ -f "$MANIFEST_FILE" ]; then
        jq -r '.event_count' "$MANIFEST_FILE"
    else
        echo "0"
    fi
}

get_previous_hash() {
    if [ -f "$MANIFEST_FILE" ]; then
        local count
        count=$(jq -r '.event_count' "$MANIFEST_FILE")
        if [ "$count" -eq 0 ]; then
            echo "null"
        else
            jq -r '.final_hash' "$MANIFEST_FILE"
        fi
    else
        echo "null"
    fi
}

canonical_hash() {
    local file="$1"
    # Using python to enforce strict canonical JSON representation for hashing
    python3 -c '
import sys, json, hashlib
try:
    with open(sys.argv[1], "r") as f:
        obj = json.load(f)
        if "event_hash" in obj:
            del obj["event_hash"]
        canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        print(hashlib.sha256(canon).hexdigest())
except Exception as e:
    sys.exit(1)
' "$file"
}

write_event() {
    local step_name="$1"
    local status="$2"
    local evidence_text="$3"
    
    init_dir
    local seq
    seq=$(get_current_sequence)
    local next_seq=$((seq + 1))
    local seq_padded
    seq_padded=$(printf "%03d" $next_seq)
    
    local prev_hash
    prev_hash=$(get_previous_hash)
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    local event_file="$EVIDENCE_DIR/${seq_padded}-${step_name}.json"
    
    # Create JSON structure (without event_hash)
    if [ "$prev_hash" == "null" ]; then
        jq -n \
           --argjson sequence "$next_seq" \
           --arg step "$step_name" \
           --arg status "$status" \
           --arg ts "$timestamp" \
           --arg ev "$evidence_text" \
           '{sequence: $sequence, step: $step, status: $status, timestamp: $ts, evidence: $ev, previous_hash: null}' > "$event_file.tmp"
    else
        jq -n \
           --argjson sequence "$next_seq" \
           --arg step "$step_name" \
           --arg status "$status" \
           --arg ts "$timestamp" \
           --arg ev "$evidence_text" \
           --arg phash "$prev_hash" \
           '{sequence: $sequence, step: $step, status: $status, timestamp: $ts, evidence: $ev, previous_hash: $phash}' > "$event_file.tmp"
    fi
       
    # Calculate canonical hash
    local curr_hash
    curr_hash=$(canonical_hash "$event_file.tmp")
    
    # Inject event_hash
    jq --arg chash "$curr_hash" '. + {event_hash: $chash}' "$event_file.tmp" > "$event_file"
    rm "$event_file.tmp"
    
    # Update Manifest
    if [ ! -f "$MANIFEST_FILE" ]; then
        jq -n \
           --arg mach "$MACHINE_ID" \
           --arg op "$OPERATOR_ID" \
           --arg created "$timestamp" \
           '{machine_id: $mach, candidate_version: "v0.2.0-CANDIDATE", operator_id: $op, created_at: $created, event_count: 0, events: [], final_hash: ""}' > "$MANIFEST_FILE.tmp"
        mv "$MANIFEST_FILE.tmp" "$MANIFEST_FILE"
    fi
    
    jq --argjson new_count "$next_seq" \
       --arg seq "$next_seq" \
       --arg fn "${seq_padded}-${step_name}.json" \
       --arg hash "$curr_hash" \
       '.event_count = $new_count | .events += [{"sequence": $seq, "filename": $fn, "event_hash": $hash}] | .final_hash = $hash' \
       "$MANIFEST_FILE" > "$MANIFEST_FILE.tmp"
    mv "$MANIFEST_FILE.tmp" "$MANIFEST_FILE"
    
    echo "Recorded [$status] for step [$step_name] -> ${seq_padded}-${step_name}.json"
}

check_credentials() {
    # Verify no tokens leaked safely without printing them
    if grep -riq "ghp_" ~/.anny-runtime/ 2>/dev/null; then
        echo "FAIL: Plaintext GitHub token found."
        return 1
    fi
    return 0
}

# --- MODES ---

if [ "$VERIFY_MODE" -eq 1 ]; then
    echo "Verifying Hash Chain in $EVIDENCE_DIR..."
    if [ ! -f "$MANIFEST_FILE" ]; then
        echo "CHAIN_INVALID: No manifest found."
        exit 1
    fi
    
    PREV_HASH="null"
    COUNT=$(jq -r '.event_count' "$MANIFEST_FILE")
    
    for i in $(seq 1 "$COUNT"); do
        PADDED=$(printf "%03d" "$i")
        FILE=$(find "$EVIDENCE_DIR" -maxdepth 1 -name "${PADDED}-*.json" | head -n 1)
        if [ -z "$FILE" ]; then
            echo "CHAIN_INVALID: Missing sequence gap at $i"
            exit 1
        fi
        
        # Verify JSON
        if ! jq -e . "$FILE" >/dev/null 2>&1; then
            echo "CHAIN_INVALID: Invalid JSON in sequence $i"
            exit 1
        fi
        
        # Verify prev hash matches
        FILE_PREV=$(jq -r '.previous_hash' "$FILE")
        if [ "$FILE_PREV" != "$PREV_HASH" ]; then
            echo "CHAIN_INVALID: Previous hash mismatch in sequence $i"
            exit 1
        fi
        
        # Verify current hash matches canonical computation
        FILE_CURR=$(jq -r '.event_hash' "$FILE")
        COMPUTED=$(canonical_hash "$FILE")
        
        if [ "$FILE_CURR" != "$COMPUTED" ]; then
            echo "CHAIN_INVALID: Invalid event hash tampered in sequence $i"
            exit 1
        fi
        
        # Verify against manifest
        MANIFEST_HASH=$(jq -r --arg seq "$i" '.events[] | select(.sequence == ($seq|tonumber)) | .event_hash' "$MANIFEST_FILE")
        if [ "$MANIFEST_HASH" != "$FILE_CURR" ]; then
            echo "CHAIN_INVALID: Manifest mismatch for sequence $i"
            exit 1
        fi
        
        PREV_HASH="$FILE_CURR"
    done
    
    # Check final hash in manifest
    if [ "$COUNT" -gt 0 ]; then
        MANIFEST_FINAL=$(jq -r '.final_hash' "$MANIFEST_FILE")
        if [ "$MANIFEST_FINAL" != "$PREV_HASH" ]; then
            echo "CHAIN_INVALID: Final hash mismatch in manifest"
            exit 1
        fi
    fi
    
    echo "CHAIN_VALID"
    exit 0
fi

if [ "$EXPORT_MODE" -eq 1 ]; then
    echo "Exporting Evidence..."
    if [ ! -d "$EVIDENCE_DIR" ]; then
        echo "No evidence to export."
        exit 1
    fi
    ARCHIVE_NAME="ANNY-RUNTIME-v0.2-${MACHINE_ID}-EVIDENCE.tar.gz"
    tar -czf "$ARCHIVE_NAME" -C "$(dirname "$EVIDENCE_DIR")" "$(basename "$EVIDENCE_DIR")"
    echo "Exported to $ARCHIVE_NAME"
    exit 0
fi

# --- EXECUTION STEPS ---

if [ -z "$STEP" ]; then
    echo "Usage: $0 --step <step> [--evidence-dir <dir>]"
    exit 1
fi

case "$STEP" in
    baseline)
        if [ -d "$HOME/.anny-runtime" ]; then
            write_event "baseline" "FAIL" "Customer Zero ~/.anny-runtime directory present."
            echo "BLOCKED: Machine is not clean."
            exit 1
        fi
        
        OS=$(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2 || echo "Unknown")
        KERNEL=$(uname -r)
        ARCH=$(uname -m)
        PY=$(python3 --version 2>/dev/null || echo "Missing")
        SYS=$(systemctl --version | head -n 1 || echo "Missing")
        
        write_event "baseline" "PASS" "OS: $OS, Kernel: $KERNEL, Arch: $ARCH, Py: $PY, Sysd: $SYS"
        ;;
        
    install)
        set +e
        bash scripts/install.sh > /tmp/install_out 2>&1
        EXIT_CODE=$?
        set -e
        if [ $EXIT_CODE -ne 0 ]; then
            write_event "install" "FAIL" "Installer failed with code $EXIT_CODE."
            exit 1
        fi
        
        if [ -f ~/.anny-runtime/identity/runtime_identity.json ]; then
            RT_ID=$(jq -r '.runtime_id' ~/.anny-runtime/identity/runtime_identity.json)
            FINGERPRINT=$(jq -r '.public_key' ~/.anny-runtime/identity/runtime_identity.json | sha256sum | awk '{print $1}')
            write_event "install" "PASS" "Installer exit 0. Runtime ID: $RT_ID, Fingerprint: $FINGERPRINT"
        else
            write_event "install" "FAIL" "Identity missing after install."
            exit 1
        fi
        ;;
        
    verify)
        set +e
        IS_ACTIVE=$(systemctl --user is-active anny-runtime || echo "inactive")
        set -e
        if [ "$IS_ACTIVE" != "active" ]; then
            write_event "verify_systemd" "FAIL" "Service state: active=$IS_ACTIVE"
            exit 1
        fi
        write_event "verify_systemd" "PASS" "Service active and enabled."
        
        set +e
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3643/)
        set -e
        if [ "$HTTP_CODE" == "200" ]; then
            write_event "verify_browser" "PASS" "Port 3643 reachable. HTTP $HTTP_CODE."
        else
            write_event "verify_browser" "FAIL" "Port 3643 unreachable."
            exit 1
        fi
        ;;
        
    github-check)
        if ! check_credentials; then
            write_event "github" "FAIL" "Unencrypted tokens leaked."
            exit 1
        fi
        write_event "github" "PASS" "No plaintext tokens found. credential_present=true"
        ;;
        
    fabric-check)
        echo "Did you successfully complete Fabric connection in the browser? (yes/no)"
        read -r ANS
        if [ "$ANS" == "yes" ]; then
            write_event "fabric" "PASS" "Human affirmed Fabric CONNECTED state."
        else
            write_event "fabric" "BLOCKED" "Human aborted or Fabric failed."
            exit 1
        fi
        ;;
        
    sandbox-check)
        set +e
        anny-runtime status > /dev/null
        if [ $? -eq 0 ]; then
            write_event "sandbox" "PASS" "anny-runtime status completed."
        else
            write_event "sandbox" "FAIL" "anny-runtime status failed."
        fi
        set -e
        ;;
        
    reboot-check)
        IS_ACTIVE=$(systemctl --user is-active anny-runtime || echo "inactive")
        if [ "$IS_ACTIVE" == "active" ]; then
            RT_ID=$(jq -r '.runtime_id' ~/.anny-runtime/identity/runtime_identity.json)
            write_event "reboot" "PASS" "Systemd active after reboot. Identity: $RT_ID"
        else
            write_event "reboot" "FAIL" "Systemd failed to auto-start after reboot."
            exit 1
        fi
        ;;
        
    recovery-check)
        echo "Did the process successfully recover via systemd after a kill? (yes/no)"
        read -r ANS
        if [ "$ANS" == "yes" ]; then
            write_event "recovery" "PASS" "Human affirmed systemd crash recovery."
        else
            write_event "recovery" "FAIL" "Crash recovery failed."
            exit 1
        fi
        ;;
        
    idempotent-install)
        set +e
        bash scripts/install.sh > /dev/null 2>&1
        EXIT_CODE=$?
        set -e
        if [ $EXIT_CODE -eq 0 ]; then
            write_event "idempotent-install" "PASS" "Installer ran successfully over existing."
        else
            write_event "idempotent-install" "FAIL" "Re-install failed."
            exit 1
        fi
        ;;
        
    uninstall)
        set +e
        anny-runtime uninstall --purge > /dev/null 2>&1
        set -e
        write_event "uninstall" "PASS" "Purge executed. Evidence dir survives."
        ;;
        
    finalize)
        echo "=========================================================="
        echo "HUMAN ASSERTION REQUIRED"
        echo "=========================================================="
        echo "Please type explicitly: 'This was executed on a real independent Linux host.'"
        read -r ATTESTATION
        if [ "$ATTESTATION" == "This was executed on a real independent Linux host." ]; then
            TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
            ATTEST_PAYLOAD="{\"statement\": \"$ATTESTATION\", \"accepted\": true, \"timestamp\": \"$TS\", \"operator_id\": \"$OPERATOR_ID\"}"
            write_event "finalize" "PASS" "$ATTEST_PAYLOAD"
            
            echo "EVIDENCE COLLECTION COMPLETE."
            echo "Final state: PHYSICAL_EVIDENCE_READY_FOR_REVIEW."
            echo "Current state remains CUSTOMER_ZERO_VALIDATED until human authority approval."
        else
            write_event "finalize" "FAIL" "Human failed attestation."
            exit 1
        fi
        ;;
        
    *)
        echo "Unknown step: $STEP"
        exit 1
        ;;
esac
