"""S-78 · the vault: a guest's own accesses, encrypted per item, never seen by the model (docs/sasha/S-78-vault.md).

`vault.use()` (crypto.py) is the only way a secret is ever opened."""
from .crypto import use  # noqa: F401
