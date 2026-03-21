from langchain.tools import tool

@tool("connect_to_mcp")
def connect_to_mcp(url):
  """
  A tool that connects the agent to an MCP server for tool extraction
  """
  import requests
  response = requests.get(url)
  if response.status_code == 200:
      return response.json()
  else:
      return f"Failed to retrieve tools. Status code: {response.status_code}"


MCP_TOOLS=[connect_to_mcp]