from flask import Flask

from tools.__init__ import ALL_TOOLS

tools_app = Flask(__name__)
PORT = 5100

@tools_app.route('/')
def list_tools():
  tools = { tool.name: tool.description for tool in ALL_TOOLS}
  return tools

def main():
  print(f"Starting MCP server on http://localhost:5100")
  tools_app.run(host="0.0.0.0", port=5100, debug=True)

if __name__ == "__main__":
  main()