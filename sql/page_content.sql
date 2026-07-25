-- page_content.sql - Database schema for page content management

-- Main pages table
CREATE TABLE IF NOT EXISTS page_content (
    id SERIAL PRIMARY KEY,
    page_url TEXT UNIQUE NOT NULL,
    full_html TEXT,
    editable_html TEXT NOT NULL,
    non_editable_html TEXT,
    last_fetched TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_page_content_url ON page_content(page_url);

-- Version history for page content
CREATE TABLE IF NOT EXISTS page_versions (
    id SERIAL PRIMARY KEY,
    page_url TEXT NOT NULL,
    editable_html TEXT NOT NULL,
    keywords JSONB,
    miratext_task_id TEXT,
    llm_model_used TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (page_url) REFERENCES page_content(page_url) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_page_versions_url ON page_versions(page_url);
CREATE INDEX IF NOT EXISTS idx_page_versions_created ON page_versions(created_at DESC);

-- SEO tasks queue
CREATE TABLE IF NOT EXISTS seo_tasks (
    id SERIAL PRIMARY KEY,
    page_url TEXT NOT NULL,
    cluster_id INTEGER,
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending',
        'analyzing',
        'analyzed',
        'rewriting',
        'rewritten',
        'saved',
        'failed'
    )),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    FOREIGN KEY (page_url) REFERENCES page_content(page_url) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_seo_tasks_status ON seo_tasks(status);
CREATE INDEX IF NOT EXISTS idx_seo_tasks_created ON seo_tasks(created_at);

-- Cluster to page mapping
CREATE TABLE IF NOT EXISTS page_cluster_mapping (
    id SERIAL PRIMARY KEY,
    page_url TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    keywords JSONB,
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'analyzing', 'analyzed', 'rewriting', 'rewritten', 'saved', 'failed'
    )),
    miratext_task_id TEXT,
    llm_version_id INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE(page_url, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_mapping_page ON page_cluster_mapping(page_url);
CREATE INDEX IF NOT EXISTS idx_mapping_cluster ON page_cluster_mapping(cluster_id);
CREATE INDEX IF NOT EXISTS idx_mapping_status ON page_cluster_mapping(status);