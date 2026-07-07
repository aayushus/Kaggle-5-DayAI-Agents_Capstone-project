Northstar enforces several production-grade security postures designed to prevent abuse and protect host resources:

## 1. Inbound Request Bounding & Rate Limiting
- **Request Size Limiting:** A strict request body size limit is enforced at **5MB** via `RequestSizeLimitMiddleware` to prevent denial-of-service (DoS) attacks via oversized payloads.
- **Endpoint Rate Limiting:** Rate limits are enforced on high-cost routes (such as `/api/run`, advisory board/war room simulations, and PDF exports) on a per-IP basis using a rolling window middleware.

## 2. Path Traversal & Sandbox Protection
- **Workspace Sandboxing:** The filesystem MCP tool resolves all paths against the workspace root, explicitly blocking path-traversal attacks (e.g., `../..`) by validating target paths stay within approved directories.
- **Container Sandboxing:** The app runs inside Docker, isolating file access and ambient authority from the host machine.
