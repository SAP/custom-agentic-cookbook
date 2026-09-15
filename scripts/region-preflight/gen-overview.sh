#!/usr/bin/env bash
# gen-overview.sh — render the availability tables for regions-overview.md.
#
# Fetches the live Discovery Center service catalog, then prints:
#   - Four regional availability tables (Europe / Americas / APAC / Sovereign)
#   - A coverage-summary table (services × regions listed / gaps)
#
# Pipe the output into regions-overview.md between the section markers, and
# bump the "Fetched" date at the top of that file. Do not hand-edit cells —
# regenerate.
#
# Requires curl and jq. No BTP login (public endpoint).

set -euo pipefail

DC_API='https://discovery-center.cloud.sap/servicecatalog/api/v1/services'
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

CATALOG="$TMPDIR/catalog.json"
curl -sf "$DC_API" -o "$CATALOG"

# The doc's universe: every region where CF Runtime is listed. This excludes
# Neo-only landscapes, which the cookbook doesn't target.
UNIVERSE="$TMPDIR/universe.txt"
jq -r '.[] | select(.name == "SAP BTP, Cloud Foundry Runtime") | .regionDataCenter' "$CATALOG" \
  | tr ',' '\n' | sed -E 's/^ +| +$//g' | awk 'NF' | sort -u > "$UNIVERSE"

# Cookbook services — keep aligned with region-preflight.sh.
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
# Display names (the ATM service is renamed for column width).
short=(
  "SAP BTP, Cloud Foundry Runtime"
  "SAP BTP, Kyma runtime"
  "SAP AI Core"
  "SAP AI Launchpad"
  "SAP HANA Cloud"
  "SAP Destination Service"
  "SAP Connectivity Service"
  "SAP Cloud Logging"
  "SAP Authorization and Trust Management"
  "SAP Audit Log Service"
)

# Regions where a given service is listed, intersected with the CF universe.
svc_regions_in_universe() {
  local svc="$1"
  jq -r --arg s "$svc" '.[] | select(.name == $s) | .regionDataCenter' "$CATALOG" \
    | tr ',' '\n' | sed -E 's/^ +| +$//g' | awk 'NF' | sort -u > "$TMPDIR/_svc.tmp"
  comm -12 "$TMPDIR/_svc.tmp" "$UNIVERSE"
}

# Render one geographic-group table. Args come in header/region pairs so the
# column header can be a short chip while the lookup uses the exact Discovery
# Center label.
render_group() {
  local title="$1"; shift
  local -a header_labels=()
  local -a regions=()
  while [[ $# -gt 0 ]]; do
    header_labels+=("$1"); regions+=("$2"); shift 2
  done

  printf '### %s\n\n' "$title"
  local hdr="| Service"
  local sep="|---"
  for h in "${header_labels[@]}"; do
    hdr+=" | $h"
    sep+="|:-:"
  done
  hdr+=" |"
  sep+="|"
  printf '%s\n%s\n' "$hdr" "$sep"

  for i in "${!services[@]}"; do
    svc_regions_in_universe "${services[$i]}" > "$TMPDIR/_svc_uni.tmp"
    local row="| ${short[$i]}"
    for r in "${regions[@]}"; do
      if grep -Fxq "$r" "$TMPDIR/_svc_uni.tmp"; then
        row+=" | ✅"
      else
        row+=" | —"
      fi
    done
    row+=" |"
    printf '%s\n' "$row"
  done
  printf '\n'
}

render_group "Europe" \
  "Frankfurt (\`eu10\`)"                  "Europe (Frankfurt)" \
  "Frankfurt EU Access (\`eu11\`)"        "Europe (Frankfurt) EU Access" \
  "Frankfurt SAP EU Access (\`eu30\`)"    "Europe (Frankfurt) SAP EU Access" \
  "Netherlands (\`eu20\`)"                "Europe (Netherlands)" \
  "Milan"                                 "Europe (Milan)" \
  "Rot SAP EU Access"                     "Europe (Rot) SAP Cloud Infrastructure EU Access" \
  "Switzerland EU Access (\`ch20\`)"      "Switzerland (EU Access)"

render_group "Americas" \
  "US East VA (\`us10\`)"       "US East (VA)" \
  "US Central IA (\`us20\`)"    "US Central (IA)" \
  "US West WA (\`us21\`)"       "US West (WA)" \
  "US West Oregon"              "US West (Oregon)" \
  "US West Colorado"            "US West (Colorado)" \
  "US Sterling (\`us30\`)"      "US (Sterling)" \
  "Canada Montreal (\`ca10\`)"  "Canada (Montreal)" \
  "Canada Toronto (\`ca20\`)"   "Canada (Toronto)" \
  "Brazil São Paulo (\`br10\`)" "Brazil (São Paulo)" \
  "Brazil South (\`br20\`)"     "Brazil South"

render_group "Asia-Pacific" \
  "Singapore (\`ap10\`)"                  "Singapore" \
  "Japan Tokyo (\`ap20\`/\`jp10\`)"       "Japan (Tokyo)" \
  "Japan Osaka (\`jp20\`)"                "Japan (Osaka)" \
  "South Korea Seoul (\`ap21\`)"          "South Korea (Seoul)" \
  "Australia Sydney (\`ap11\`)"           "Australia (Sydney)" \
  "Australia SE Sydney (\`ap12\`)"        "Australia Southeast (Sydney)" \
  "India Mumbai (\`in30\`)"               "India (Mumbai)"

render_group "Sovereign / regulated" \
  "UAE Dubai (\`ae10\`)"                        "UAE (Dubai)" \
  "Israel Tel Aviv (\`il30\`)"                  "Israel (Tel Aviv)" \
  "KSA Dammam Regulated (\`sa30\`)"             "KSA (Dammam – KSA Regulated Customers)" \
  "KSA Dammam Non-Reg. (\`sa31\`)"              "KSA (Dammam – KSA Non-Regulated Customers)" \
  "China Shanghai (\`cn40\`)"                   "China (Shanghai)" \
  "China North 3 (\`cn41\`)"                    "China (North 3)"

# Coverage summary — count and gaps per service across the 30-region universe.
total=$(wc -l < "$UNIVERSE" | tr -d ' ')
printf '## Coverage summary\n\n'
printf 'Cookbook services across the %s multi-cloud data centers listed above (Neo-only landscapes excluded):\n\n' "$total"
printf '| Service | Regions | Gaps |\n|---|:-:|---|\n'
for i in "${!services[@]}"; do
  svc_regions_in_universe "${services[$i]}" > "$TMPDIR/_svc_uni.tmp"
  count=$(wc -l < "$TMPDIR/_svc_uni.tmp" | tr -d ' ')
  missing=$(comm -23 "$UNIVERSE" "$TMPDIR/_svc_uni.tmp" \
    | tr '\n' '§' | sed -E 's/§$//; s/§/; /g')
  [[ -z "$missing" ]] && missing="—"
  printf '| %s | %s / %s | %s |\n' "${short[$i]}" "$count" "$total" "$missing"
done
