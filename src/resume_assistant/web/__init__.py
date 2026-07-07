"""Web adapter package: a thin Flask front door over the same ``core/`` engine.

Mirrors ``server/`` (the MCP adapter): it validates input, calls ``core/`` via
``service.py``, and renders templates. No business logic lives here (see
docs/ARCHITECTURE.md, rule 4). The web layer never imports ``mcp`` and ``core/``
never imports Flask.
"""
