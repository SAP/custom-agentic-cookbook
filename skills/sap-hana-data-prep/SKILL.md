---
name: sap-hana-data-prep
description: Use this skill when preparing customer or business data for SAP HANA Cloud ingestion before using sap-hana-vector or sap-hana-triple. Trigger for document preprocessing, CSV/Excel cleanup, JSON/API normalization, chunking for vector search, entity/relation extraction for HANA triple store, relational schema planning, metadata design, PII handling, and creating a reusable ingestion contract for an agent.
---

# SAP HANA Data Prep — ingestion-ready datasets for agents

This skill turns messy source data into reviewed, HANA-ingestion-ready artifacts. It does **not** provision HANA, create embeddings, load data into HANA, or write agent query code. Its job is to decide how data should be shaped, produce clean artifacts, and hand off to `sap-hana-vector`, `sap-hana-triple`, or a relational HANA loader.

Use this flow:

```text
raw files / exports / API data
  -> inspect and classify
  -> normalize and enrich metadata
  -> choose vector, triple, relational, or hybrid target
  -> produce ingestion contract + prepared artifacts
  -> hand off to sap-hana-vector / sap-hana-triple / relational loader
```

## First decision: target shape

Choose the target from the questions the agent must answer, not from the file extension alone.

| Agent need | Recommended shape | Handoff |
|---|---|---|
| Semantic search over policies, guides, tickets, PDFs, pages | HANA vector | `sap-hana-vector` |
| Relationship traversal, lineage, ownership, dependencies, network-like data | HANA triple store / KG | `sap-hana-triple` |
| Exact lookup, filters, joins, reporting over structured records | Relational HANA table | CAP/API or `hdbcli` loader |
| Search text, then filter by structured fields or traverse relationships | Hybrid vector + relational/KG metadata | `sap-hana-vector` plus `sap-hana-triple` or relational loader |

If the target is unclear, create a short recommendation with tradeoffs and ask for confirmation before preparing irreversible ingestion scripts.

## Inspect inputs

Profile the data before transforming it. Record findings in the ingestion contract.

Check:

- source type: PDF, DOCX, HTML, Markdown, CSV, Excel, JSON, API response, DB export, S/4 extract
- data shape: unstructured text, semi-structured records, structured rows, graph-like entities
- sensitive fields: personal data, secrets, credentials, tenant/customer identifiers, regulated data
- source references to preserve: file name, URL, page, row number, record ID, system ID, timestamp
- expected agent questions: semantic, exact lookup, relationship traversal, analytics, or mixed

Useful inspection commands:

```bash
find <input-dir> -maxdepth 2 -type f | sort
python -m json.tool <file.json> >/dev/null
python - <<'PY'
import csv, sys
with open(sys.argv[1], newline='', encoding='utf-8-sig') as f:
    sample = f.read(4096)
    print(csv.Sniffer().sniff(sample).delimiter)
PY <file.csv>
```

## Ingestion contract

Always produce an `ingestion-contract.yaml` or equivalent section in the final answer. This contract is the stable handoff between arbitrary source data and HANA-specific ingestion skills.

```yaml
dataset_name: <short-kebab-name>
source_type: <pdf|docx|html|markdown|csv|xlsx|json|api|db_export|mixed>
target_shape: <hana_vector|hana_triple|relational_hana|hybrid>
business_purpose: <what the agent should answer>
data_classification: <public|internal|confidential|restricted|unknown>
pii_handling: <none_detected|mask_before_embedding|exclude_fields|needs_review>
source_references:
  preserve: [source_file, page, row_number, record_id, url, extracted_at]
text_fields: []
metadata_fields: []
entity_fields: []
relationship_fields: []
chunking_strategy: <none|fixed_tokens|section_based|row_as_document|record_summary>
dedupe_strategy: <none|exact_text_hash|business_key|source_record_id>
embedding_model: <model-or-tbd>
prepared_artifacts:
  - <path/to/artifact>
handoff_skill: <sap-hana-vector|sap-hana-triple|relational-loader|hybrid>
open_questions: []
```

## Prepare documents for vector ingestion

Use vector prep when source data is mostly natural language and the agent needs semantic retrieval.

1. Extract text with page/section references intact.
2. Normalize whitespace, headers, footers, broken hyphenation, and boilerplate.
3. Split into chunks that preserve meaning. Prefer section-based chunking for policies and manuals; use fixed-token chunking only when structure is absent.
4. Attach metadata that users will later need for filtering or citations.
5. Remove duplicates and near-empty chunks.
6. Mask or exclude PII before embedding when required.

Vector artifact format:

```jsonl
{"id":"policy-001-p03-c02","text":"Employees may claim...","metadata":{"source_file":"policy.pdf","page":3,"section":"Claims","country":"SG"}}
```

Recommended outputs:

```text
prepared/chunks.jsonl
prepared/ingestion-contract.yaml
prepared/sample-review.md
```

Then hand off to `sap-hana-vector` for schema, embedding, HNSW index, and query patterns.

## Prepare tabular data

Use tabular prep when source data is CSV, Excel, API records, or exported tables.

1. Profile columns, types, null rates, duplicate keys, and category values.
2. Normalize dates, numbers, booleans, IDs, currencies, and language/country codes.
3. Decide whether each row is a relational record, a vector document, an entity, or a relationship.
4. Preserve business keys and source row references.
5. Split fields into text, metadata, entity, and relationship groups.

Choose output by target:

```text
relational_hana -> schema.sql + cleaned_rows.csv
hana_vector     -> row_documents.jsonl with text + metadata
hana_triple     -> entity_mapping.yaml + triples.ttl
hybrid          -> cleaned_rows.csv + row_documents.jsonl + entity_mapping.yaml
```

For row-as-document vector prep, build text that reads naturally but keeps structured metadata separate:

```jsonl
{"id":"course-LRN-1001","text":"Course: SAP HANA Basics. Level: Beginner. Description: ...","metadata":{"course_id":"LRN-1001","level":"beginner","region":"global"}}
```

## Prepare JSON or API data

Use JSON/API prep when data arrives from business services or external systems.

1. Identify stable IDs, nested arrays, timestamps, status fields, and links to related objects.
2. Flatten only what is needed for the chosen target; keep raw payload samples for audit.
3. Convert nested object links into relationships if KG traversal is useful.
4. Convert descriptive text fields into vector documents if semantic search is useful.
5. Keep API endpoint, query parameters, extraction time, and tenant/system identifiers as metadata when allowed.

Recommended outputs:

```text
prepared/normalized_records.jsonl
prepared/entity_mapping.yaml
prepared/relationship_mapping.yaml
prepared/ingestion-contract.yaml
```

## Prepare knowledge graph data

Use KG prep when the agent must answer questions like “who owns this”, “what depends on this”, “how are these connected”, or “what changed upstream”.

1. Define entity classes with domain experts: `Customer`, `Contract`, `Policy`, `System`, `Course`, `Role`, etc.
2. Define relationships as verbs: `owns`, `dependsOn`, `approvedBy`, `locatedIn`, `hasPolicy`, `requiresSkill`.
3. Decide IRI rules. Use stable business IDs, not display names.
4. Create a minimal ontology first; do not model every possible field.
5. Generate sample triples and review them before bulk conversion.

Mapping artifact example:

```yaml
base_iri: https://example.sap/agent-data/hr#
entities:
  Employee:
    id_field: employee_id
    label_field: display_name
  Course:
    id_field: course_id
    label_field: title
relationships:
  - subject: Employee.employee_id
    predicate: completedCourse
    object: Course.course_id
```

Then hand off to `sap-hana-triple` for SPARQL workspace, loading, and query patterns.

## Guardrails

- Do not embed secrets, credentials, access tokens, private keys, or raw regulated personal data.
- For sovereign or restricted regions, confirm allowed embedding models and data residency before recommending an embedding path.
- Keep source references in every prepared record so agent answers can cite where retrieved evidence came from.
- Prefer deterministic transformations for ingestion prep. If using an LLM for entity extraction or summarization, mark generated fields and keep the original source reference.
- Do not give the downstream agent arbitrary SQL/SPARQL access as the only interface; design narrow retrieval tools or APIs after ingestion.

## Quality checks

Before handing off, verify:

```bash
wc -l prepared/*.jsonl
python - <<'PY'
from pathlib import Path
contract = Path('prepared/ingestion-contract.yaml')
required = ['dataset_name:', 'target_shape:', 'prepared_artifacts:', 'handoff_skill:']
text = contract.read_text(encoding='utf-8')
missing = [key for key in required if key not in text]
if missing:
    raise SystemExit(f'missing contract keys: {missing}')
PY
head -n 3 prepared/chunks.jsonl
```

Review at least five representative prepared records. Confirm each has:

- stable `id`
- non-empty `text` or valid entity/relationship fields
- useful metadata for filtering and citation
- source reference
- no obvious secrets or unapproved PII
- target shape and handoff skill recorded in the contract

## Handoff

End with a concise handoff note:

```text
Prepared target: hana_vector
Artifacts: prepared/chunks.jsonl, prepared/ingestion-contract.yaml
Next skill: sap-hana-vector
Next action: create vector table and load chunks with selected embedding model
```
