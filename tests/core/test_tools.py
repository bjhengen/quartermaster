"""Tests for the Tool Registry."""

import pytest

from quartermaster.core.tools import ApprovalTier, ToolRegistry


@pytest.mark.asyncio
async def test_register_and_get_tool() -> None:
    registry = ToolRegistry()

    async def my_handler(params: dict) -> dict:
        return {"result": "ok"}

    registry.register(
        name="test.hello",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Who to greet"},
            },
            "required": ["name"],
        },
        handler=my_handler,
        approval_tier=ApprovalTier.AUTONOMOUS,
    )

    tool = registry.get("test.hello")
    assert tool is not None
    assert tool.name == "test.hello"
    assert tool.description == "A test tool"
    assert tool.approval_tier == ApprovalTier.AUTONOMOUS


@pytest.mark.asyncio
async def test_execute_tool() -> None:
    registry = ToolRegistry()

    async def add_handler(params: dict) -> dict:
        return {"sum": params["a"] + params["b"]}

    registry.register(
        name="math.add",
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        handler=add_handler,
    )

    result = await registry.execute("math.add", {"a": 2, "b": 3})
    assert result == {"sum": 5}


@pytest.mark.asyncio
async def test_execute_nonexistent_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(KeyError, match=r"no\.such\.tool"):
        await registry.execute("no.such.tool", {})


def test_list_tools() -> None:
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="a.tool", description="A", parameters={}, handler=handler)
    registry.register(name="b.tool", description="B", parameters={}, handler=handler)

    tools = registry.list_tools()
    names = [t.name for t in tools]
    assert "a.tool" in names
    assert "b.tool" in names


def test_get_schemas_for_llm() -> None:
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(
        name="test.tool",
        description="Test",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": [],
        },
        handler=handler,
    )

    schemas = registry.get_tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "test.tool"
    assert schemas[0]["type"] == "function"


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="dup", description="First", parameters={}, handler=handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(name="dup", description="Second", parameters={}, handler=handler)


@pytest.mark.asyncio
async def test_tool_execution_error_returns_error_dict() -> None:
    registry = ToolRegistry()

    async def failing_handler(params: dict) -> dict:
        raise RuntimeError("connection refused")

    registry.register(name="fail.tool", description="Fails", parameters={}, handler=failing_handler)

    result = await registry.execute("fail.tool", {})
    assert "error" in result
    assert "connection refused" in result["error"]
