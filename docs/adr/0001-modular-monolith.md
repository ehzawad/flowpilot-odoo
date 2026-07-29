# ADR 0001: modular monolith plus independent workers

**Status:** accepted

The domain is still evolving, so API, worker, agent, retrieval, and integration code share one Python
package and schema. API, worker, web, and MCP are separate processes because their scaling,
permissions, and failure modes differ. New microservices require measured pressure or independent
ownership, not résumé signalling.
