"""
Bootstrap Inventory Discovery — Phase G.

Dynamically discovers the declared, enabled, and authorized state
of all operational components during bootstrap:
  - Capabilities
  - Tools
  - Models
  - Workers
  - Connectors

RULE: Nothing is assumed from cached state. Every field is resolved
      fresh from the live registries.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ComponentInventory:
    """The Phase G snapshot of a single component class."""
    declared: List[str] = field(default_factory=list)
    configured: List[str] = field(default_factory=list)
    enabled: List[str] = field(default_factory=list)
    authorized: List[str] = field(default_factory=list)
    available: List[str] = field(default_factory=list)
    functional: List[str] = field(default_factory=list)
    tested: List[str] = field(default_factory=list)
    verified: List[str] = field(default_factory=list)


@dataclass
class BootstrapInventory:
    """Complete Phase G inventory of all operational components."""
    capabilities: ComponentInventory = field(default_factory=ComponentInventory)
    tools: ComponentInventory = field(default_factory=ComponentInventory)
    models: ComponentInventory = field(default_factory=ComponentInventory)
    workers: ComponentInventory = field(default_factory=ComponentInventory)
    connectors: ComponentInventory = field(default_factory=ComponentInventory)
    error: Optional[str] = None


class InventoryDiscovery:
    """
    Runs Phase G of the deterministic bootstrap.

    Iterates over live registries (not config files, not memory) and
    returns a BootstrapInventory. Any component that cannot be enumerated
    yields an error — the caller decides if this is BLOCKED.
    """

    def __init__(
        self,
        capability_registry=None,
        tool_registry=None,
        model_registry=None,
        worker_manager=None,
        connectors: Optional[List[str]] = None,
        fabric_contract=None,
    ):
        self._cap_registry = capability_registry
        self._tool_registry = tool_registry
        self._model_registry = model_registry
        self._worker_manager = worker_manager
        self._static_connectors = connectors or []
        self._fabric_contract = fabric_contract

    def discover(self) -> BootstrapInventory:
        """
        Execute Phase G: fresh inventory of all operational components.

        Returns a BootstrapInventory with declared, enabled, and authorized lists.
        """
        inv = BootstrapInventory()
        errors = []

        try:
            inv.capabilities = self._discover_capabilities()
        except Exception as e:
            logger.error("Phase G: capability discovery failed: %s", e)
            errors.append(f"capabilities: {e}")

        try:
            inv.tools = self._discover_tools()
        except Exception as e:
            logger.error("Phase G: tool discovery failed: %s", e)
            errors.append(f"tools: {e}")

        try:
            inv.models = self._discover_models()
        except Exception as e:
            logger.error("Phase G: model discovery failed: %s", e)
            errors.append(f"models: {e}")

        try:
            inv.workers = self._discover_workers()
        except Exception as e:
            logger.error("Phase G: worker discovery failed: %s", e)
            errors.append(f"workers: {e}")

        try:
            inv.connectors = self._discover_connectors()
        except Exception as e:
            logger.error("Phase G: connector discovery failed: %s", e)
            errors.append(f"connectors: {e}")

        if errors:
            inv.error = "; ".join(errors)

        return inv

    def _discover_capabilities(self) -> ComponentInventory:
        inv = ComponentInventory()

        if self._cap_registry is None:
            from runtime.execution.capability import CapabilityRegistry
            self._cap_registry = CapabilityRegistry()

        all_caps = self._cap_registry.list_all()

        granted = set()
        revoked = set()
        if self._fabric_contract:
            granted = set(self._fabric_contract.granted_capabilities)
            revoked = set(self._fabric_contract.revoked_capabilities)

        for cap in all_caps:
            inv.declared.append(cap.capability_id)
            if cap.enabled:
                inv.enabled.append(cap.capability_id)
                cid = cap.capability_id
                if (not granted or cid in granted) and cid not in revoked:
                    inv.authorized.append(cid)

        return inv

    def _discover_tools(self) -> ComponentInventory:
        inv = ComponentInventory()

        # A registry must be supplied by the runtime wiring. There is no
        # safe generic ToolRegistry fallback because register_builtins() has
        # required execution dependencies and cannot be initialized here.
        if self._tool_registry is None:
            raise RuntimeError("tool registry not wired into bootstrap")

        for manifest in self._tool_registry.list_tools():
            inv.declared.append(manifest.name)
            inv.enabled.append(manifest.name)
            inv.authorized.append(manifest.name)

        # Also inventory MCP tools when the MCP registry is available.
        try:
            from runtime.mcp.registry import ToolRegistry as MCPRegistry
            mcp_reg = MCPRegistry()
            for tool in mcp_reg.list_tools():
                full_id = f"mcp.{tool.tool_id}"
                if full_id not in inv.declared:
                    inv.declared.append(full_id)
                    inv.enabled.append(full_id)
                    inv.authorized.append(full_id)
        except (ImportError, AttributeError):
            pass

        return inv

    def _discover_models(self) -> ComponentInventory:
        inv = ComponentInventory()

        if self._model_registry is None:
            from runtime.execution.registry import ModelRegistry
            self._model_registry = ModelRegistry()

        for model in self._model_registry.list_models():
            inv.declared.append(model.model_id)
            from runtime.execution.models import ModelState
            if model.state == ModelState.AVAILABLE:
                inv.enabled.append(model.model_id)
                inv.authorized.append(model.model_id)
            elif model.state not in (
                ModelState.DISABLED,
                ModelState.QUARANTINED,
                ModelState.DEPRECATED,
            ):
                inv.enabled.append(model.model_id)

        return inv

    def _discover_workers(self) -> ComponentInventory:
        inv = ComponentInventory()

        L2_WORKERS = [
            "ANNA",   # DESIGN (Marketing)
            "IRIS",   # PRISM (Product)
            "KIRA",   # FORGE (Engineering)
            "KLARA",  # SENTINEL (Security & Trust)
            "RUTH",   # LEX (Legal & Compliance)
            "MINA",   # SCOUT (Customer & Market)
            "STELLA", # WATCH (Operations)
            "ZARA",   # LEDGER (Finance & Economics)
        ]
        inv.declared = list(L2_WORKERS)
        inv.enabled = list(L2_WORKERS)
        inv.authorized = list(L2_WORKERS)

        if self._worker_manager is not None:
            try:
                active = self._worker_manager.list_active()
                for w in active:
                    wid = getattr(w, "worker_id", str(w))
                    if wid not in inv.declared:
                        inv.declared.append(wid)
                        inv.enabled.append(wid)
            except Exception:
                pass

        return inv

    def _discover_connectors(self) -> ComponentInventory:
        inv = ComponentInventory()

        connector_checks = [
            ("github", "runtime.github.client", "GitHubClient"),
            ("fabric.github", "runtime.fabric.github_adapter", "GitHubFabricAdapter"),
            ("compute.colab", "runtime.compute.colab", "ColabComputeProvider"),
            ("browser.cdp", "runtime.browser.broker_server", "BrowserBrokerServer"),
            ("api.bridge", "runtime.api.bridge", "router"),
        ]

        for connector_id, module_path, symbol in connector_checks:
            inv.declared.append(connector_id)
            try:
                mod = __import__(module_path, fromlist=[symbol])
                if hasattr(mod, symbol):
                    inv.enabled.append(connector_id)
                    inv.authorized.append(connector_id)
            except ImportError:
                pass

        for cid in self._static_connectors:
            if cid not in inv.declared:
                inv.declared.append(cid)

        return inv
