import asyncio
from pathlib import Path

from fastmcp import Client

BASE_DIR = Path(__file__).resolve().parent


async def main():

    client = Client(
        str(BASE_DIR / "server.py"),
        roots=[
            (BASE_DIR).as_uri(),
            (BASE_DIR / "resources").as_uri(),
        ],
    )

    async with client:

        tools = await client.list_tools()

        print("=== TOOLS ===")

        for tool in tools:
            print(tool.name)

        resources = await client.list_resources()

        print("\n=== RESOURCES ===")

        for resource in resources:
            print(resource.uri)

        prompts = await client.list_prompts()

        print("\n=== PROMPTS ===")

        for prompt in prompts:
            print(prompt.name)


if __name__ == "__main__":
    asyncio.run(main())
