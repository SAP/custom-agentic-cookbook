#!/usr/bin/env bash
# region-preflight.sh — check Discovery Center service availability for a BTP region.
#
# Accepts loose input and resolves it to one or more canonical Discovery Center
# region labels:
#   - BTP CLI landscape codes:   eu10, eu11, eu13, eu20, eu30, us01, us02, us10,
#                                us11, us20, us21, us30, ap10, ap11, ap12, ap20,
#                                ap21, ap30, jp10, jp20, jp30, ca10, ca20, br10,
#                                br20, in30, cn20, cn40, sa30, sa31, ch20, il30,
#                                ae01
#   - Short aliases:             eu, europe, us, america, usa, asia, ap, china,
#                                cn, prc, ksa, sa, saudi, japan, jp, india, in,
#                                brazil, br, canada, ca, australia, au, korea,
#                                kr, singapore, sg, israel, il, uae, ae, dubai,
#                                switzerland, ch
#   - Substring matches:         frankfurt, sterling, shanghai, dammam, mumbai…
#   - Verbatim Discovery Center label, e.g. "Europe (Frankfurt) EU Access"
#
# Portable to bash 3.2 (macOS default) — no associative arrays.
#
# Usage:
#   bash scripts/region-preflight/region-preflight.sh <region>
#   bash scripts/region-preflight/region-preflight.sh europe
#   bash scripts/region-preflight/region-preflight.sh eu10
#   bash scripts/region-preflight/region-preflight.sh "Europe (Frankfurt)"
set -euo pipefail

REGION_INPUT="${1:-}"

if [[ -z "$REGION_INPUT" ]]; then
  cat >&2 <<EOF
Usage: $0 <region>

Examples:
  $0 europe                       # all Europe (*) data centers
  $0 eu10                         # → Europe (Frankfurt)
  $0 china                        # all China (*) data centers
  $0 ksa                          # both KSA (Dammam …) data centers
  $0 frankfurt                    # substring → Europe (Frankfurt) + variants
  $0 "Europe (Frankfurt)"         # verbatim Discovery Center label

Run without args to see this help.
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
# Service list — the ones every sovereign-AI recipe in this cookbook cares
# about. Keep aligned with scripts/region-preflight/regions-overview.md and
# skills/sap-sovereign-regions/references/btp-regional-availability.md.
# ---------------------------------------------------------------------------
services=(
  "SAP BTP, Cloud Foundry Runtime"
  "SAP BTP, Kyma runtime"
  "SAP AI Core"
  "SAP AI Launchpad"
  "SAP HANA Cloud"
  "SAP Destination Service"
  "SAP Connectivity Service"
  "SAP Cloud Logging"
  "SAP Authorization and Trust Management Service"
  "SAP Audit Log Service"
)

# Lowercase, trim.
norm_input="$(printf '%s' "$REGION_INPUT" | tr '[:upper:]' '[:lower:]' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"

# ---------------------------------------------------------------------------
# Landscape-shortcut → exact Discovery Center label.
# Sources: the landscape-code ↔ physical-region pairing comes from SAP Help
# "Regions and API Endpoints Available for the Cloud Foundry Environment" (the
# code is the CF API-endpoint subdomain, so each row is self-identifying); the
# label string is the verbatim Discovery Center RegionDataCenter key, so the
# availability lookup below matches with grep -Fxq. When SAP adds landscapes,
# extend this case.
# ---------------------------------------------------------------------------
landscape_to_label() {
  case "$1" in
    eu10) echo "Europe (Frankfurt)" ;;
    eu11) echo "Europe (Frankfurt) EU Access" ;;
    eu13) echo "Europe (Milan)" ;;
    eu20) echo "Europe (Netherlands)" ;;
    eu30) echo "Europe (Frankfurt) SAP EU Access" ;;
    us01) echo "US (Sterling)" ;;
    us02) echo "US West (Colorado)" ;;
    us10) echo "US East (VA)" ;;
    us11) echo "US West (Oregon)" ;;
    us20) echo "US West (WA)" ;;
    us21) echo "US East (VA)" ;;
    us30) echo "US Central (IA)" ;;
    ap10) echo "Australia (Sydney)" ;;
    ap11) echo "Singapore" ;;
    ap12) echo "South Korea (Seoul)" ;;
    ap20) echo "Australia (Sydney)" ;;
    ap21) echo "Singapore" ;;
    ap30) echo "Australia Southeast (Sydney)" ;;
    jp10) echo "Japan (Tokyo)" ;;
    jp20) echo "Japan (Tokyo)" ;;
    jp30) echo "Japan (Osaka)" ;;
    ca10) echo "Canada (Montreal)" ;;
    ca20) echo "Canada (Toronto)" ;;
    br10) echo "Brazil (São Paulo)" ;;
    br20) echo "Brazil South" ;;
    in30) echo "India (Mumbai)" ;;
    cn20) echo "China (North 3)" ;;
    cn40) echo "China (Shanghai)" ;;
    sa30) echo "KSA (Dammam – KSA Regulated Customers)" ;;
    sa31) echo "KSA (Dammam – KSA Non-Regulated Customers)" ;;
    ch20) echo "Switzerland (EU Access)" ;;
    il30) echo "Israel (Tel Aviv)" ;;
    ae01) echo "UAE (Dubai)" ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Short alias → substring pattern (extended regex, case-insensitive) matched
# against the live RegionDataCenter labels. Patterns deliberately fan out:
# "europe" matches all Europe (*) DCs, "us" matches all US* DCs, etc.
# ---------------------------------------------------------------------------
alias_to_pattern() {
  case "$1" in
    eu|europe)                    echo "Europe" ;;
    us|usa|america)               echo "(^US |^US\$|US East|US West|US Central|US \\()" ;;
    ap|asia)                      echo "(Singapore|Australia|Japan|Korea|India)" ;;
    china|cn|prc)                 echo "China" ;;
    ksa|sa|saudi)                 echo "KSA" ;;
    japan|jp)                     echo "Japan" ;;
    india|in)                     echo "India" ;;
    brazil|br)                    echo "Brazil" ;;
    canada|ca)                    echo "Canada" ;;
    australia|au)                 echo "Australia" ;;
    korea|kr)                     echo "Korea" ;;
    singapore|sg)                 echo "Singapore" ;;
    israel|il)                    echo "Israel" ;;
    uae|ae|dubai)                 echo "UAE" ;;
    switzerland|ch)               echo "Switzerland" ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Discovery Center API. Migrated Nov 2025 from the legacy OData path
#   https://discovery-center.cloud.sap/servicecatalog/Services  (?$filter=…)
# which now 404s, to the current REST endpoint
#   https://discovery-center.cloud.sap/servicecatalog/api/v1/services
# which returns a bare JSON array of every service. Field names went
# from PascalCase to camelCase (Name → name, RegionDataCenter →
# regionDataCenter). The RegionDataCenter string is still comma-joined.
# ---------------------------------------------------------------------------
DC_API='https://discovery-center.cloud.sap/servicecatalog/api/v1/services'

# One-shot fetch of the whole catalog; every subsequent lookup filters this
# cached blob locally. Beats the old per-service call storm.
CATALOG_JSON=""
fetch_catalog() {
  if [[ -z "$CATALOG_JSON" ]]; then
    CATALOG_JSON="$(curl -sf "$DC_API")" || {
      echo "error: could not reach Discovery Center at $DC_API" >&2
      exit 3
    }
    if ! printf '%s' "$CATALOG_JSON" | jq -e 'type == "array"' >/dev/null 2>&1; then
      echo "error: Discovery Center returned non-array JSON — API shape changed?" >&2
      exit 3
    fi
  fi
  printf '%s' "$CATALOG_JSON"
}

# All Discovery Center labels (deduped) from the broadest service
# (Cloud Foundry Runtime, present in every BTP region).
fetch_all_labels() {
  fetch_catalog \
  | jq -r '.[] | select(.name == "SAP BTP, Cloud Foundry Runtime") | .regionDataCenter' \
  | tr ',' '\n' \
  | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' \
  | awk 'NF' \
  | sort -u
}

# Resolve input to one or more canonical labels. Strategy:
#   1. Landscape-shortcut exact hit → single label
#   2. Short alias → regex pattern over the live label set
#   3. Verbatim label match → that one label
#   4. Fallback: case-insensitive substring match over the live label set
resolve_labels() {
  local input_norm="$1"
  local raw_input="$2"

  local label
  if label="$(landscape_to_label "$input_norm" 2>/dev/null)"; then
    printf '%s\n' "$label"
    return
  fi

  local all_labels
  all_labels="$(fetch_all_labels)"

  local pattern
  if pattern="$(alias_to_pattern "$input_norm" 2>/dev/null)"; then
    printf '%s\n' "$all_labels" | grep -E -i "$pattern" || true
    return
  fi

  if printf '%s\n' "$all_labels" | grep -Fxq "$raw_input"; then
    printf '%s\n' "$raw_input"
    return
  fi

  printf '%s\n' "$all_labels" | grep -F -i -- "$raw_input" || true
}

# bash 3.2 has no `mapfile`; read line-by-line into an array instead.
MATCHED_LABELS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && MATCHED_LABELS+=("$line")
done < <(resolve_labels "$norm_input" "$REGION_INPUT")

if [[ "${#MATCHED_LABELS[@]}" -eq 0 ]]; then
  cat >&2 <<EOF
No Discovery Center region matched "$REGION_INPUT".

Try a landscape code (eu10, cn40, sa30, …), a short alias (europe, china,
ksa, japan, …), a city substring (frankfurt, shanghai, dammam, …), or paste
the verbatim Discovery Center label.

Live label list:
EOF
  fetch_all_labels | sed 's/^/  - /' >&2
  exit 2
fi

printf 'Input:        %s\n' "$REGION_INPUT"
printf 'Resolved to:  %d region(s)\n' "${#MATCHED_LABELS[@]}"
for label in "${MATCHED_LABELS[@]}"; do
  printf '  - %s\n' "$label"
done
printf '\n'

# ---------------------------------------------------------------------------
# For each resolved region, look up per-service availability in the cached
# catalog and print a table.
# ---------------------------------------------------------------------------
CATALOG="$(fetch_catalog)"

for region in "${MATCHED_LABELS[@]}"; do
  printf '═══ %s ═══\n' "$region"
  printf '%-52s %s\n' "Service" "Discovery Center"
  printf '%-52s %s\n' "-------" "----------------"

  for service in "${services[@]}"; do
    # Discovery Center stores regionDataCenter as a comma-joined string.
    # Split, trim, and look for an *exact* element match — substring would
    # wrongly match "Europe (Frankfurt)" against "Europe (Frankfurt) EU Access".
    # `first(...)` short-circuits after the first hit so we don't scan the
    # whole 82-service array once we've found our row.
    if printf '%s' "$CATALOG" | jq -e \
      --arg service "$service" --arg region "$region" '
        first(.[] | select(.name == $service))
        | (.regionDataCenter // "")
        | split(",")
        | map(gsub("^\\s+|\\s+$"; ""))
        | index($region) != null
      ' >/dev/null 2>&1; then
      status="available"
    else
      status="not listed"
    fi

    printf '%-52s %s\n' "$service" "$status"
  done
  printf '\n'
done
