-- Run as the database owner and replace passwords/role names through your secret manager.
CREATE ROLE flowpilot_migrator LOGIN;
CREATE ROLE flowpilot_api LOGIN;
CREATE ROLE flowpilot_worker LOGIN;

GRANT CONNECT ON DATABASE flowpilot TO flowpilot_api, flowpilot_worker;
GRANT USAGE ON SCHEMA public TO flowpilot_api, flowpilot_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO flowpilot_api, flowpilot_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO flowpilot_api, flowpilot_worker;

ALTER DEFAULT PRIVILEGES FOR ROLE flowpilot_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO flowpilot_api, flowpilot_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE flowpilot_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO flowpilot_api, flowpilot_worker;

-- Do not grant BYPASSRLS. Migrations are owned by flowpilot_migrator; application roles remain
-- subject to the forced row-level-security policies in the initial migration.
