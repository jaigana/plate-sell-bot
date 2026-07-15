-- These restrictions are maintained by the application, not through the admin UI.
CREATE TABLE IF NOT EXISTS official_forbidden_plate_series (
    country_code VARCHAR(2) NOT NULL,
    series VARCHAR(10) NOT NULL,
    source TEXT NOT NULL DEFAULT 'official_rule_set',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (country_code, series)
);

INSERT INTO official_forbidden_plate_series(country_code, series) VALUES
    ('KZ', 'SEX'),
    ('KZ', 'ASS'),
    ('KZ', 'XXX'),
    ('KZ', 'BLY'),
    ('KZ', 'XER'),
    ('KZ', 'GEI')
ON CONFLICT DO NOTHING;

-- The old user-editable list is intentionally removed: only the fixed rules above apply.
DROP TABLE IF EXISTS blacklisted_series;
