-- Versioned MySQL Schema for seo-auto-cluster
-- This script initializes all required tables for the system.

CREATE DATABASE IF NOT EXISTS seo_auto DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE seo_auto;

-- Users
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    balance DECIMAL(10, 2) DEFAULT 0.00,
    yandex_token TEXT,
    is_blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User Settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INT PRIMARY KEY,
    yandex_region_id INT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Sites
CREATE TABLE IF NOT EXISTS sites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    domain VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_site (user_id, domain)
);

-- Yandex Queries
CREATE TABLE IF NOT EXISTS yandex_queries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    query VARCHAR(255) NOT NULL,
    hits INT DEFAULT 0,
    clicks INT DEFAULT 0,
    ctr DECIMAL(5,2) DEFAULT 0.00,
    avg_position DECIMAL(5,2) DEFAULT 0.00,
    clustered BOOLEAN DEFAULT FALSE,
    minus_word BOOLEAN DEFAULT FALSE,
    frequency INT DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_query_per_site (user_id, site_url, query)
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    progress INT DEFAULT 0,
    payload JSON,
    result JSON,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Billing History
CREATE TABLE IF NOT EXISTS billing_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    description TEXT,
    type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Payment History (Tegro)
CREATE TABLE IF NOT EXISTS payment_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'RUB',
    order_id VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Settings (Tariffs etc)
CREATE TABLE IF NOT EXISTS settings (
    `key` VARCHAR(100) PRIMARY KEY,
    `value` TEXT NOT NULL
);

-- Insert default tariffs
INSERT IGNORE INTO settings (`key`, `value`) VALUES
('position_new_rate', '0.25'),
('position_step_rate', '0.05'),
('cluster_rate', '0.10'),
('analysis_rate', '5.00');

-- SERP Cache
CREATE TABLE IF NOT EXISTS serp_cache (
    cache_key VARCHAR(255) PRIMARY KEY,
    urls JSON,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Cluster Names
CREATE TABLE IF NOT EXISTS cluster_names (
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    cluster_id VARCHAR(100) NOT NULL,
    cluster_name VARCHAR(255) DEFAULT '',
    is_favorite BOOLEAN DEFAULT FALSE,
    is_pinned BOOLEAN DEFAULT FALSE,
    pinned_order INT DEFAULT 0,
    PRIMARY KEY (user_id, site_url, cluster_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Cluster Mappings
CREATE TABLE IF NOT EXISTS cluster_mappings (
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    cluster_id VARCHAR(100) NOT NULL,
    target_url VARCHAR(255) NOT NULL,
    PRIMARY KEY (user_id, site_url, cluster_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Cluster Analysis
CREATE TABLE IF NOT EXISTS cluster_analysis (
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    cluster_id VARCHAR(100) NOT NULL,
    analysis_data JSON,
    PRIMARY KEY (user_id, site_url, cluster_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Cluster SEO History
CREATE TABLE IF NOT EXISTS cluster_seo_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    cluster_id VARCHAR(100) NOT NULL,
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    intent_type VARCHAR(50),
    seo_plan_content TEXT,
    optimized_html TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Cluster LSI
CREATE TABLE IF NOT EXISTS cluster_lsi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    cluster_id VARCHAR(100) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    frequency INT DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_lsi (user_id, site_url, cluster_id, keyword)
);

-- Query History (positions tracking)
CREATE TABLE IF NOT EXISTS query_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    site_url VARCHAR(255) NOT NULL,
    query VARCHAR(255) NOT NULL,
    cluster_id VARCHAR(100) DEFAULT '',
    position INT DEFAULT 0,
    engine VARCHAR(50) DEFAULT 'yandex',
    device VARCHAR(50) DEFAULT 'desktop',
    found_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_history_lookup (user_id, site_url, query, created_at),
    INDEX idx_query_history_lookup (user_id, site_url, engine, device)
);

-- Token Blacklist (for JWT revocation)
CREATE TABLE IF NOT EXISTS token_blacklist (
    jti VARCHAR(64) PRIMARY KEY,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_expires_at (expires_at)
);

-- Wordstat Settings
CREATE TABLE IF NOT EXISTS wordstat_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    device VARCHAR(50) DEFAULT 'desktop',
    region VARCHAR(50) DEFAULT '213',
    region_name VARCHAR(255) DEFAULT 'Москва',
    is_default BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
