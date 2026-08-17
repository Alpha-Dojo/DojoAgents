from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.harnesses.capabilities import IdentitySpec, ToolProviderSpec
from dojoagents.tools.registry import ToolSpec


async def _echo(arguments):
    return {"echo": arguments.get("text", "")}


class MinimalHarness:
    descriptor = HarnessDescriptor("minimal", "1.0.0", "Minimal Harness")

    def configure(self, builder, context):
        builder.set_identity(IdentitySpec("minimal.identity", "harness:minimal", identity="Minimal agent"))
        builder.add_tool_provider(
            ToolProviderSpec(
                "minimal.tools",
                "harness:minimal",
                provider=(
                    ToolSpec(
                        "echo",
                        "Echo text",
                        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                        _echo,
                    ),
                ),
                tool_names=("echo",),
            )
        )

    async def startup(self, context):
        return None

    async def shutdown(self, context):
        return None


def create_harness(config, context):
    return MinimalHarness()
