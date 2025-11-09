# Development Notes for Claude Code

## Running Tests

When running on NixOS, use the following command to run tests:

```bash
nix-shell test/tests-shell.nix --run "source .venv/bin/activate && python -m pytest"
```

On other systems, use the standard pytest command:

```bash
python -m pytest
```
