CREATE TABLE IF NOT EXISTS accounts (
    id uuid PRIMARY KEY,
    email text UNIQUE NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    key_hash text UNIQUE NOT NULL,
    label text NOT NULL DEFAULT 'default',
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id text PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    mode text NOT NULL DEFAULT 'agent',
    status text NOT NULL CHECK (status IN ('active', 'ended', 'error')),
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz NULL,
    turns integer NOT NULL DEFAULT 0,
    images_sent integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kyc_results (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    decision text NOT NULL CHECK (decision IN ('pass', 'fail', 'needs_review')),
    checks jsonb NOT NULL,
    extracted jsonb NOT NULL,
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sessions_account_id_idx ON sessions(account_id);
CREATE INDEX IF NOT EXISTS kyc_results_account_id_idx ON kyc_results(account_id);

