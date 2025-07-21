# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Entry point for the timer triggered Azure Function."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import structlog

from azure_collect import AzureResourceGraphCollector
from analysis.cost_azure import AzureCostCollector
from analysis.security_azure import AzureSecurityCollector

logger = structlog.get_logger()


async def run(security: bool = False) -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(os.getenv("LOG_LEVEL", "INFO")))
    config_path = os.getenv("AZURE_CONFIG", "config/azure_subscriptions.json")
    collector = AzureResourceGraphCollector(config_path)
    resources = await collector.collect()
    logger.info("inventory_collected", count=len(resources))

    cosmos_url = os.environ["COSMOS_URL"]
    for sub in collector.subscriptions:
        cost = AzureCostCollector(sub, cosmos_url)
        await cost.collect_and_store()
        if security:
            sec = AzureSecurityCollector(sub, cosmos_url)
            await sec.collect_and_store()


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Azure inventory and cost runner")
    parser.add_argument("--security", action="store_true", help="Collect policy compliance")
    args = parser.parse_args()
    await run(security=args.security)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
