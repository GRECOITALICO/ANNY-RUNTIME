import time
from runtime.compute.colab import SyncMCPBridge

bridge = SyncMCPBridge()
bridge.start()

print("Initial tools:", [t.name for t in bridge.list_tools().tools])

# Call open_colab_browser_connection, but don't connect UI
res = bridge.call_tool("open_colab_browser_connection", {})
print("Tool returned:", res)

print("Tools after tool call:", [t.name for t in bridge.list_tools().tools])

bridge.stop()
