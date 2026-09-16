from runtime.compute.colab import SyncMCPBridge
bridge = SyncMCPBridge()
bridge.start()
print(bridge.list_tools())
bridge.stop()
