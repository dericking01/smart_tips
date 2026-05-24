CREATE SCHEMA IF NOT EXISTS smart_tips;

CREATE TABLE IF NOT EXISTS smart_tips.topics (
    id BIGSERIAL PRIMARY KEY,
    topic_code VARCHAR(100) UNIQUE NOT NULL,
    topic_name VARCHAR(100),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS smart_tips.classification_logs (
    id BIGSERIAL PRIMARY KEY,
    msisdn VARCHAR(20),
    raw_messages TEXT,
    language VARCHAR(10),
    topics JSONB,
    classifier_model VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS smart_tips.generated_tips (
    id BIGSERIAL PRIMARY KEY,
    msisdn VARCHAR(20),
    topics JSONB,
    language VARCHAR(10),
    generated_tip TEXT,
    tip_hash VARCHAR(64),
    validation_status VARCHAR(20),
    retry_count INTEGER DEFAULT 0,
    delivery_status VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS smart_tips.sms_logs (
    id BIGSERIAL PRIMARY KEY,
    msisdn VARCHAR(20),
    message_text TEXT,
    status VARCHAR(50),
    port VARCHAR(10),
    response_code INTEGER,
    error TEXT,
    attempt INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);
