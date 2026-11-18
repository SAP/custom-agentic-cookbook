"""Explicit synthetic backend. It never replaces a failed HANA connection."""

import math

DOCS = [
    {
        "id": "doc-1",
        "content": "An unconfirmed assembly operation can cause a delay.",
        "source": "https://example.com/source/doc-1",
        "topic": "manufacturing",
        "embedding": [1.0, 0.0, 0.0],
    },
    {
        "id": "doc-2",
        "content": "Confirm inspection before shipment.",
        "source": "https://example.com/source/doc-2",
        "topic": "manufacturing",
        "embedding": [0.4, 0.9, 0.0],
    },
    {
        "id": "doc-3",
        "content": "A revenue report uses posted transactions.",
        "source": "https://example.com/source/doc-3",
        "topic": "finance",
        "embedding": [0.0, 0.0, 1.0],
    },
]


class FixtureRepository:
    def vector(self, embedding, topic, limit):
        scored = []
        for row in DOCS:
            if row["topic"] == topic:
                vector = row["embedding"]
                score = sum(a * b for a, b in zip(embedding, vector, strict=True)) / (
                    math.sqrt(sum(a * a for a in embedding)) * math.sqrt(sum(a * a for a in vector))
                )
                scored.append(
                    {key: value for key, value in row.items() if key != "embedding"}
                    | {"score": score}
                )
        return sorted(scored, key=lambda row: row["score"], reverse=True)[:limit]

    def graph(self, subject, limit):
        if subject != "customer-42":
            return []
        return [
            {
                "contact": "urn:cookbook:entity:contact-7",
                "source": "https://example.com/source/customer-42",
            }
        ][:limit]
