# Security Policy

The **Beyond the Basics** project is an educational collection of mini-projects designed for learning and experimentation. While these projects are intended for demonstration, security remains important.

## Reporting a Vulnerability

If you discover a security vulnerability in any of the projects within this repository, **please do not open a public issue.**

Instead, please report it via GitHub's private vulnerability reporting feature:
1. Navigate to the main page of the repository.
2. Click on the **Security** tab.
3. Select **Vulnerability reports** in the left sidebar.
4. Click **New report**.

### What to include in your report:
* **Project Name:** Which folder/project is affected?
* **Description:** A summary of the vulnerability.
* **Steps to Reproduce:** How can the vulnerability be triggered?
* **Impact:** What is the potential risk?

## Security Model
* **Educational Intent:** These projects are meant to demonstrate concepts (like 2FA, rate limiting, etc.). They are **not** production-ready systems and may lack enterprise-grade hardening.
* **Dependency Management:** We use `uv` to manage isolated dependencies. We encourage contributors to keep dependencies updated and check for vulnerabilities using tools like `safety` or `pip-audit`.
* **No Secret Commit Policy:** Please ensure that no real-world API keys, passwords, or personal credentials are included in your contributions. Use placeholders or environment variable documentation instead.

## Our Commitment
We will investigate all reports of security vulnerabilities promptly. We thank you for your commitment to keeping this learning resource safe for the community.
