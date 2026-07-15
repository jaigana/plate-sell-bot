CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT,
    balance_available BIGINT NOT NULL DEFAULT 0 CHECK (balance_available >= 0),
    balance_frozen BIGINT NOT NULL DEFAULT 0 CHECK (balance_frozen >= 0),
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    last_activity TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plates (
    id BIGSERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL,
    plate_number VARCHAR(15) NOT NULL UNIQUE,
    state VARCHAR(20) NOT NULL CHECK (state IN ('STATE_SALE', 'OWNED', 'FIXED_SALE', 'AUCTION')),
    owner_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    reserved_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    reserved_until TIMESTAMPTZ,
    minted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((state = 'STATE_SALE') OR owner_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS plates_number_trgm_idx ON plates USING GIN (plate_number gin_trgm_ops);
CREATE INDEX IF NOT EXISTS plates_owner_idx ON plates(owner_id, state);
CREATE INDEX IF NOT EXISTS plates_state_idx ON plates(state, updated_at DESC);
CREATE INDEX IF NOT EXISTS plates_reservation_idx ON plates(reserved_until) WHERE reserved_until IS NOT NULL;

CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    plate_id BIGINT NOT NULL REFERENCES plates(id),
    seller_id BIGINT NOT NULL REFERENCES users(telegram_id),
    price BIGINT NOT NULL CHECK (price BETWEEN 1 AND 99999),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')),
    buyer_id BIGINT REFERENCES users(telegram_id),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS sales_one_active_plate_idx ON sales(plate_id) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS sales_active_idx ON sales(status, price, created_at DESC);

CREATE TABLE IF NOT EXISTS auctions (
    id BIGSERIAL PRIMARY KEY,
    plate_id BIGINT NOT NULL REFERENCES plates(id),
    seller_id BIGINT NOT NULL REFERENCES users(telegram_id),
    starting_price BIGINT NOT NULL CHECK (starting_price BETWEEN 1 AND 99999),
    current_price BIGINT NOT NULL CHECK (current_price >= 0),
    highest_bidder_id BIGINT REFERENCES users(telegram_id),
    ends_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'FINISHED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS auctions_one_active_plate_idx ON auctions(plate_id) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS auctions_active_ends_idx ON auctions(status, ends_at);

CREATE TABLE IF NOT EXISTS bids (
    id BIGSERIAL PRIMARY KEY,
    auction_id BIGINT NOT NULL REFERENCES auctions(id),
    bidder_id BIGINT NOT NULL REFERENCES users(telegram_id),
    amount BIGINT NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bids_auction_idx ON bids(auction_id, amount DESC, created_at ASC);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    counterparty_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    plate_id BIGINT REFERENCES plates(id) ON DELETE SET NULL,
    amount BIGINT NOT NULL,
    transaction_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('PENDING', 'COMPLETED', 'CANCELLED')),
    external_ref TEXT UNIQUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS transactions_user_idx ON transactions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ownership_history (
    id BIGSERIAL PRIMARY KEY,
    plate_id BIGINT NOT NULL REFERENCES plates(id),
    previous_owner_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    new_owner_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL,
    amount BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ownership_history_plate_idx ON ownership_history(plate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS blacklisted_series (
    id BIGSERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL,
    series VARCHAR(10) NOT NULL,
    created_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(country_code, series)
);

CREATE TABLE IF NOT EXISTS platform_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO platform_settings(key, value) VALUES
    ('mint_price', '1'),
    ('commission_percent', '10'),
    ('auction_min_increment', '5'),
    ('auction_anti_snipe_minutes', '5'),
    ('auction_extension_minutes', '5'),
    ('inactive_days', '365'),
    ('inactive_warning_days', '30')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS bot_cards (
    card_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    image_file_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO bot_cards(card_id, title, description) VALUES
    ('home', 'CPM2 Plates Market', 'Маркетплейс виртуальных игровых номеров Car Parking Multiplayer 2.'),
    ('legal', 'Виртуальные игровые активы', 'Номера существуют только внутри игры и не являются государственными регистрационными знаками.')
ON CONFLICT (card_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS banners (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_file_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    created_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    notification_type VARCHAR(40) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    delivered_at TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notifications_pending_idx ON notifications(next_attempt_at) WHERE delivered_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_logs_created_idx ON audit_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS backups (
    id BIGSERIAL PRIMARY KEY,
    requested_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('STARTED', 'SENT', 'FAILED')),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    granted_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_blocks (
    user_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    blocked_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_sessions (
    bot_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL DEFAULT 0,
    business_connection_id TEXT NOT NULL DEFAULT '',
    destiny TEXT NOT NULL DEFAULT 'default',
    screen_stack JSONB NOT NULL DEFAULT '[]'::jsonb,
    fsm_state TEXT,
    fsm_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
);
