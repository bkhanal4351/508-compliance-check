# AGENTS.md

Guidance for future Codex work on `508-scanner-local`:

- Do not use paid APIs, SaaS dependencies, cloud services, external databases, or hosted infrastructure.
- Keep the tool local-first and runnable on a developer workstation.
- Do not add authentication or cloud deployment unless explicitly requested.
- Do not weaken SSRF protections in the crawler. Private/internal IP blocking is intentional.
- Do not claim legal certification or complete compliance validation.
- Describe results as automated and semi-automated Section 508/WCAG issue detection.
- Prefer explicit tests for crawler, scope, safety, document scanning, and reporting behavior.
- Keep generated report HTML accessible: semantic headings, captions, table headers, skip link, and good contrast.
- Keep dependencies minimal and open source.
