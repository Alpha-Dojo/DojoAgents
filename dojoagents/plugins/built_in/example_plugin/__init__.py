import json
import logging
from typing import Dict, Any

LOGGER = logging.getLogger("dojo_plugins.built_in.example_plugin")

def example_tool_handler(param: str) -> str:
    """这是一个示例工具处理器"""
    LOGGER.info(f"Executing example tool with param: {param}")
    return json.dumps({"status": "success", "result": f"Processed {param}"}, ensure_ascii=False)


def register(ctx) -> None:
    # 1. 注册自定义工具，供大模型在决策时主动调用
    tool_schema = {
        "name": "example_tool",
        "description": "这是一个供演示使用的示例工具",
        "parameters": {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "传入的测试参数"
                }
            },
            "required": ["param"]
        }
    }
    ctx.register_tool(
        name="example_tool",
        schema=tool_schema,
        handler=lambda args, **kwargs: example_tool_handler(args.get("param", ""))
    )

    # 2. 注入 pre_llm_call 钩子，可在大模型生成对话前附加临时上下文
    def on_pre_llm(session_id: str, user_message: str) -> str:
        return "提示：插件已挂载并开始监听本轮对话。"
    
    ctx.register_hook("pre_llm_call", on_pre_llm)

    # 3. 注入 transform_llm_output 钩子，可在最终文本返回用户前修改内容
    def on_transform_output(response_text: str, session_id: str) -> str:
        suffix = "\n\n*提示：此消息已通过插件处理机制。*"
        if suffix not in response_text:
            return response_text + suffix
        return response_text

    ctx.register_hook("transform_llm_output", on_transform_output)
