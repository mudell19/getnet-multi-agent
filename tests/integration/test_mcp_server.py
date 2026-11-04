"""The MCP server, exercised by a real MCP client over stdio in a subprocess."""
import asyncio
import subprocess
import sys

from mcp import Client, StdioServerParameters

from getnet_multi_agent.mcp_server import build_server
from getnet_multi_agent.tools.merchant import MerchantData

MODULE = "getnet_multi_agent.mcp_server"


def launch(user_id: str) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", MODULE, "--user-id", user_id])


def call(params, tool: str, arguments: dict | None = None):
    async def run():
        async with Client(params) as client:
            return await client.call_tool(tool, arguments or {})

    return asyncio.run(run())


def test_mcp_tools_expose_no_user_id_parameter():
    async def run():
        async with Client(build_server("cliente1988")) as client:
            return (await client.list_tools()).tools

    tools = {tool.name: tool for tool in asyncio.run(run())}
    assert set(tools) == {"get_receivables", "get_terminal_status"}
    for tool in tools.values():
        assert tool.input_schema.get("properties", {}) == {}


def test_mcp_stdio_returns_the_data_of_the_merchant_fixed_at_launch():
    data = MerchantData()
    for user_id in ("cliente1988", "cliente2000"):
        for tool, expected in (
            ("get_receivables", data.get_receivables(user_id)),
            ("get_terminal_status", data.get_terminal_status(user_id)),
        ):
            result = call(launch(user_id), tool)
            assert not result.is_error
            assert result.structured_content == expected


def test_mcp_user_id_argument_cannot_select_another_merchant():
    result = call(launch("cliente1988"), "get_receivables", {"user_id": "cliente2000"})
    assert not result.is_error
    assert result.structured_content == MerchantData().get_receivables("cliente1988")
    assert result.structured_content != MerchantData().get_receivables("cliente2000")


def test_mcp_unknown_merchant_gets_not_found():
    result = call(launch("nobody_here"), "get_receivables")
    assert result.structured_content == {"status": "not_found"}


def test_mcp_tool_failure_logs_do_not_break_the_stdio_protocol():
    script = (
        "from pathlib import Path\n"
        "from getnet_multi_agent.mcp_server import build_server, use_stderr_for_logs\n"
        "from getnet_multi_agent.tools.merchant import MerchantData\n"
        "use_stderr_for_logs()\n"
        "build_server('cliente1988', MerchantData(Path('/nonexistent.json'))).run('stdio')\n"
    )
    params = StdioServerParameters(command=sys.executable, args=["-c", script])
    result = call(params, "get_receivables")
    assert result.structured_content == {"status": "error", "error": "merchant_data_unavailable"}


def test_mcp_server_refuses_to_start_without_a_merchant():
    for args in ([], ["--user-id", "  "]):
        done = subprocess.run([sys.executable, "-m", MODULE, *args], capture_output=True, text=True)
        assert done.returncode == 2
        assert "user-id" in done.stderr
