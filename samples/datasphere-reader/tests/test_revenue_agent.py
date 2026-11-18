"""Optional A2A revenue consumer boundaries and deterministic business answer."""

import json

import pytest

from revenue_agent import RevenueAgent, summarize_revenue


async def test_revenue_agent_calls_only_bounded_region_tool():
    calls = []

    async def caller(region, limit):
        calls.append((region, limit))
        return {
            "rows": [{"Region": "EMEA", "Revenue": "12.50"}, {"Region": "EMEA", "Revenue": "7.50"}],
            "source": "configured Datasphere revenue view",
            "limit": limit,
        }

    answer = json.loads(await RevenueAgent(caller=caller, fixture=True).invoke("revenue EMEA"))
    assert calls == [("EMEA", 50)]
    assert answer == {
        "region": "EMEA",
        "row_count": 2,
        "revenue": "20.00",
        "limit": 50,
        "bounded": True,
        "source": "synthetic OAuth/OData fixture; no tenant proof",
    }


@pytest.mark.parametrize("text", ["", "revenue", "show all data", "revenue " + "x" * 129])
async def test_invalid_question_never_contacts_mcp(text):
    async def forbidden(*_):
        pytest.fail("invalid input contacted MCP")

    assert "revenue <region>" in await RevenueAgent(caller=forbidden).invoke(text)


@pytest.mark.parametrize("value", [None, True, "NaN", "Infinity", "1e100", "1e-100000", "x"])
def test_invalid_revenue_rejected_without_echo(value):
    with pytest.raises(ValueError, match="invalid revenue"):
        summarize_revenue(
            {
                "rows": [{"Region": "EMEA", "Revenue": value}],
                "source": "configured Datasphere revenue view",
                "limit": 50,
            },
            "EMEA",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "rows": [{"Region": "APJ", "Revenue": 12}],
            "source": "configured Datasphere revenue view",
            "limit": 50,
        },
        {"rows": [], "source": "https://private.example/", "limit": 50},
        {"rows": [], "source": "configured Datasphere revenue view", "limit": 51},
        {
            "rows": [{"Region": "EMEA", "Revenue": 1}] * 51,
            "source": "configured Datasphere revenue view",
            "limit": 50,
        },
    ],
)
def test_changed_mcp_scope_rejected(payload):
    with pytest.raises(ValueError):
        summarize_revenue(payload, "EMEA")


@pytest.mark.parametrize(
    "url",
    [
        "http://outside.example:8091/sse",
        "https://user:secret@example:443/sse",
        "http://127.0.0.1:8091/sse?secret=x",
        "http://127.0.0.1:8091/sse#x",
        "https://example:70000/sse",
        "https://example:notaport/sse",
        "http://127.0.0.1/sse",
        "file:///sse",
        "https://example/other",
    ],
)
def test_mcp_endpoint_validation_does_not_echo_bad_address(url):
    from revenue_agent import validated_mcp_url

    with pytest.raises(ValueError) as error:
        validated_mcp_url(url)
    assert url not in str(error.value)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8091/sse", "https://example/sse"])
def test_mcp_endpoint_accepts_configured_https_or_loopback(url):
    from revenue_agent import validated_mcp_url

    assert validated_mcp_url(url) == url
