-- Strava OAuth schema (reference; tables are created via SQLAlchemy init_db)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name VARCHAR(255) NOT NULL,
    firstname VARCHAR(128),
    lastname VARCHAR(128),
    username VARCHAR(128),
    avatar_url VARCHAR(512),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME
);

CREATE TABLE IF NOT EXISTS strava_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    athlete_id BIGINT NOT NULL UNIQUE,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    token_type VARCHAR(32) NOT NULL DEFAULT 'Bearer',
    scope VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_strava_accounts_athlete_id ON strava_accounts (athlete_id);
