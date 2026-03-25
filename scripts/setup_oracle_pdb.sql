-- Quartermaster Oracle PDB Setup
-- Run as SYSDBA from the CDB root:
--   sqlplus / as sysdba @scripts/setup_oracle_pdb.sql

-- Create PDB
CREATE PLUGGABLE DATABASE quartermaster_pdb
  ADMIN USER qm_admin IDENTIFIED BY CHANGE_ME_ADMIN
  FILE_NAME_CONVERT = ('/pdbseed/', '/quartermaster_pdb/');

ALTER PLUGGABLE DATABASE quartermaster_pdb OPEN;
ALTER PLUGGABLE DATABASE quartermaster_pdb SAVE STATE;

-- Connect to the new PDB
ALTER SESSION SET CONTAINER = quartermaster_pdb;

-- Create application schema user
CREATE USER qm IDENTIFIED BY CHANGE_ME_QM
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION TO qm;
GRANT CREATE TABLE TO qm;
GRANT CREATE SEQUENCE TO qm;
GRANT CREATE PROCEDURE TO qm;

-- Create Phase 1 tables
-- Conversation history
CREATE TABLE qm.conversations (
    conversation_id   RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    transport         VARCHAR2(20) NOT NULL,
    external_chat_id  VARCHAR2(100) NOT NULL,
    created_at        TIMESTAMP DEFAULT systimestamp,
    last_active_at    TIMESTAMP DEFAULT systimestamp,
    metadata          JSON
);

CREATE INDEX qm.idx_conv_chat_id ON qm.conversations(external_chat_id);
CREATE INDEX qm.idx_conv_last_active ON qm.conversations(last_active_at);

-- Individual turns in a conversation
CREATE TABLE qm.turns (
    turn_id           RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    conversation_id   RAW(16) NOT NULL REFERENCES qm.conversations,
    role              VARCHAR2(20) NOT NULL,
    content           CLOB,
    tool_calls        JSON,
    tool_results      JSON,
    llm_backend       VARCHAR2(50),
    tokens_in         NUMBER,
    tokens_out        NUMBER,
    estimated_cost    NUMBER(12,6),
    created_at        TIMESTAMP DEFAULT systimestamp
);

CREATE INDEX qm.idx_turns_conv ON qm.turns(conversation_id, created_at);

-- Plugin state (generic key-value per plugin)
CREATE TABLE qm.plugin_state (
    plugin_name       VARCHAR2(50) NOT NULL,
    state_key         VARCHAR2(100) NOT NULL,
    state_value       JSON,
    updated_at        TIMESTAMP DEFAULT systimestamp,
    CONSTRAINT pk_plugin_state PRIMARY KEY (plugin_name, state_key)
);

-- Scheduled tasks
CREATE TABLE qm.schedules (
    schedule_id       RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    plugin_name       VARCHAR2(50) NOT NULL,
    task_name         VARCHAR2(100) NOT NULL,
    cron_expression   VARCHAR2(100) NOT NULL,
    enabled           NUMBER(1) DEFAULT 1,
    last_run_at       TIMESTAMP,
    next_run_at       TIMESTAMP,
    last_status       VARCHAR2(20),
    config            JSON
);

-- API usage tracking
CREATE TABLE qm.usage_log (
    usage_id          RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    provider          VARCHAR2(30) NOT NULL,
    model             VARCHAR2(50),
    tokens_in         NUMBER,
    tokens_out        NUMBER,
    estimated_cost    NUMBER(12,6),
    purpose           VARCHAR2(100),
    plugin_name       VARCHAR2(50),
    created_at        TIMESTAMP DEFAULT systimestamp
);

CREATE INDEX qm.idx_usage_created ON qm.usage_log(created_at);
CREATE INDEX qm.idx_usage_provider ON qm.usage_log(provider, created_at);

-- Approval queue
CREATE TABLE qm.approvals (
    approval_id       RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    plugin_name       VARCHAR2(50) NOT NULL,
    tool_name         VARCHAR2(100) NOT NULL,
    draft_content     CLOB,
    action_payload    JSON,
    status            VARCHAR2(20) DEFAULT 'pending',
    transport         VARCHAR2(20),
    external_msg_id   VARCHAR2(100),
    requested_at      TIMESTAMP DEFAULT systimestamp,
    resolved_at       TIMESTAMP,
    resolved_by       VARCHAR2(50)
);

CREATE INDEX qm.idx_approvals_status ON qm.approvals(status, requested_at);

COMMIT;

-- Verify
SELECT table_name FROM all_tables WHERE owner = 'QM' ORDER BY table_name;

EXIT;
