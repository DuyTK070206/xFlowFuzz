# Policy Fix

The path-guided runner was already executing the intended source-to-sink path,
but dynamic sinks without an explicit YAML `effects` list could be evaluated as
safe. Dynamic benchmark sinks are now treated as security-sensitive boundaries.
A tainted XFlowFuzz canary reaching any declared sink confirms a violation and
produces a witness, while explicit suspicious destinations remain supported.

Regression status: 15 tests passed.
