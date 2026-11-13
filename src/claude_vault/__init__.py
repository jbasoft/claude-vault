"""claude-vault: secrets for AI coding agents.

The agent learns the *name* of a credential. The human types the *value* into a
dialog this package draws. The value is injected into child processes and
scrubbed out of their output, so it never enters the agent's context window,
transcript, or the request sent to the model provider.
"""

__version__ = "0.3.0"
__all__ = ["__version__"]
