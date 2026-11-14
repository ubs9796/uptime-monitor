# Project Rules: bsloopstudio Uptime Monitor

- Language: Python 3 standard library first (`urllib.request`, `ssl`, `socket`, `sqlite3`).
- Hardware Target: Raspberry Pi 3B (1 GB RAM max, ARM CPU) and Chromebook (8 GB RAM). Keep memory under 60 MB.
- Code Style: Write short functions with type hints. Validate all URL and port inputs.
- Security: Never hardcode API keys or webhook URLs. Load secrets from environment variables.
- Testing: Run `pytest` before every commit. Test boundary conditions and network failures.
- Git: Work only on feature branches (`feat/<slug>`). Use Conventional Commits.
