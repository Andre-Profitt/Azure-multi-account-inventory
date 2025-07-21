import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from src.azure_collect import AzureResourceGraphCollector


@pytest.mark.asyncio
async def test_collect_single_page(tmp_path: Path) -> None:
    cfg = tmp_path / "subs.json"
    cfg.write_text(json.dumps({
        "subscriptions": {"test": {"subscription_id": "sub1"}},
        "resource_types": ["Microsoft.Compute/virtualMachines"]
    }))

    mock_data = {
        "data": [
            {
                "id": "/subscriptions/sub1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
                "name": "vm1",
                "type": "Microsoft.Compute/virtualMachines",
                "location": "eastus",
                "tags": {"env": "prod"},
                "subscriptionId": "sub1"
            }
        ]
    }

    with respx.mock(base_url="https://management.azure.com") as mock:
        mock.post("/providers/Microsoft.ResourceGraph/resources", params={"api-version": "2021-03-01"}).respond(200, json=mock_data)
        with patch("src.azure_collect.DefaultAzureCredential", return_value=AsyncMock()):
            collector = AzureResourceGraphCollector(str(cfg))
            resources = await collector.collect()

    assert len(resources) == 1
    item = resources[0]
    assert item["resource_name"] == "vm1"
    assert item["account_id"] == "sub1"
