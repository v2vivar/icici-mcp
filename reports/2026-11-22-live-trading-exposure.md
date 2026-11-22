# Security finding: live trading tool exposure

Date: 2026-11-22  
Source commit: `bc8c96e834b8c21322e799d1eba56da02aaf707a`  
Severity: HIGH; confidence: 10/10

## Evidence

At the source commit, `src/icici_mcp/server.py:247` and the subsequent
decorators register `place_order`, `modify_order`, `cancel_order`, and
`square_off` as MCP tools. Each invokes its corresponding Breeze API method.
The server does not enforce caller authorization, order-specific explicit
approval, comprehensive risk limits, or a kill switch. Trade audit logging
exists, but does not provide those controls.

## Impact and conditions

Anyone or anything able to invoke these tools on an authenticated server can
submit or change live orders and positions without those server-side safeguards.
Exposure and impact depend on who can access the server and its credentials.

## Scope and remediation

This is a partial review of the specified finding, not a finding that the rest
of the system is vulnerability-free. Remove live trading tools from MCP
exposure until authorization, order-specific explicit approval, risk validation,
audit logging, and a kill switch are implemented.
