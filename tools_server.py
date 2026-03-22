"""MCP Tool Server — serves all tools via HTTP for remote agent consumption.

Hosted at https://tools.eric-merritt.com via nginx proxy to localhost:5100.

GET  /                   — list all tools with full schemas
GET  /<name>             — get one tool's schema
POST /<name>             — execute a tool with JSON params, returns tool_result
"""

import json
from flask import Flask, request, jsonify
from tools import ALL_TOOLS
from tools._output import tool_result

tools_app = Flask(__name__)
PORT = 5100

# Build lookup dict once at startup
_TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def _tool_schema(t) -> dict:
    """Extract full schema from a LangChain tool for agent consumption."""
    schema = t.args_schema.schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = schema.get("required", [])

    params = {}
    for pname, pinfo in props.items():
        param = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
        if "default" in pinfo:
            param["default"] = pinfo["default"]
        if "enum" in pinfo:
            param["enum"] = pinfo["enum"]
        params[pname] = param

    return {
        "name": t.name,
        "description": t.description or "",
        "params": params,
    }


@tools_app.route("/", methods=["GET"])
def list_tools():
    """List all available tools with full schemas."""
    tools = [_tool_schema(t) for t in ALL_TOOLS]
    return jsonify({"count": len(tools), "tools": tools})


@tools_app.route("/<name>", methods=["GET"])
def get_tool(name):
    """Get a single tool's schema by name."""
    t = _TOOL_MAP.get(name)
    if not t:
        return jsonify({"error": f"Unknown tool: {name}"}), 404
    return jsonify(_tool_schema(t))


@tools_app.route("/<name>", methods=["POST"])
def call_tool(name):
    """Execute a tool. Body: JSON object of params. Returns tool_result JSON."""
    t = _TOOL_MAP.get(name)
    if not t:
        return jsonify({"status": "error", "data": None, "error": f"Unknown tool: {name}"}), 404

    params = request.get_json(force=True, silent=True) or {}

    try:
        result = t.invoke(params)
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if "status" in parsed and "data" in parsed:
                    return tools_app.response_class(
                        response=result,
                        mimetype="application/json",
                    )
            except (json.JSONDecodeError, TypeError):
                pass
            return jsonify({"status": "success", "data": result, "error": ""})
        else:
            return jsonify({"status": "success", "data": result, "error": ""})
    except Exception as e:
        return jsonify({"status": "error", "data": None, "error": str(e)}), 500


def main():
    print(f"Starting MCP server on http://localhost:{PORT}")
    print(f"  {len(ALL_TOOLS)} tools loaded")
    print(f"  GET  /              — list all tools")
    print(f"  GET  /<name>        — get tool schema")
    print(f"  POST /<name>        — execute tool")
    tools_app.run(host="0.0.0.0", port=PORT, debug=True)


if __name__ == "__main__":
    main()
