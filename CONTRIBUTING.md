# Contributing to Beyond the Basics

Thank you for your interest in contributing! This project is an experimental lab for deep-diving into software engineering concepts. Whether you're fixing a bug, improving documentation, or adding a brand-new project, your help is appreciated.

## How to Contribute

### 1. Adding a New Project
We love new mini-projects! To add a new one, please ensure it fits the project's philosophy:
* **Standalone:** Must be in its own folder with its own `pyproject.toml` and `.venv`.
* **Minimalist:** Use standard libraries or minimal dependencies.
* **Pedagogical:** Code should be heavily commented. Explain *why* things work, not just *what* they do.
* **Runnable:** Must include clear instructions on how to run it.

**Steps:**
1. Create a new folder for your project.
2. Ensure you use `uv` for dependency management.
3. Include a `README.md` inside your project folder explaining the concept and how to run it.
4. Add your project to the table in the main `README.md`.

### 2. Improving Existing Projects
If you notice a way to make an existing implementation clearer, more efficient, or better documented:
* Open an issue first to discuss the change if it's significant.
* Submit a Pull Request with a clear explanation of your improvements.

### 3. Reporting Issues
* Use the [Issues](https://github.com/AlwaysSany/beyond-the-besics/issues) tab to report bugs, suggest new projects, or ask questions about the implementations.

## Development Workflow

1. **Fork** the repository.
2. **Clone** your fork locally: `git clone https://github.com/YOUR_USERNAME/beyond-the-besics.git`
3. **Install `uv`**: Follow the instructions at [astral.sh/uv](https://docs.astral.sh/uv/).
4. **Create a branch**: `git checkout -b feature/your-feature-name`
5. **Commit your changes**: Follow conventional commit messages (e.g., `feat: add rate-limiter project`).
6. **Push and Submit a Pull Request**.

## Code Style
* Keep code modular and readable.
* Use type hints where possible to help others understand the data structures.
* Ensure code is documented with comments, as this is a learning resource.

---
*By contributing to this repository, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).*
