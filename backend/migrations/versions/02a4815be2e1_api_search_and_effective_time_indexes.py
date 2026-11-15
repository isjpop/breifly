"""api: search and effective-time indexes

Hand-written: Alembic autogenerate cannot render expression or GIN indexes. The expressions
must match app/models/article.py and app/models/summary.py exactly, or PostgreSQL will not use
the indexes for the API's queries (tests/test_api_search.py checks the query plan).

Revision ID: 02a4815be2e1
Revises: 429e73afdb54
"""
from alembic import op

revision = '02a4815be2e1'
down_revision = '429e73afdb54'
branch_labels = None
depends_on = None

ARTICLE_DOCUMENT = (
    "coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(content, '')"
)
SUMMARY_DOCUMENT = (
    "coalesce(headline, '') || ' ' || coalesce(why_it_matters, '') || ' ' || "
    "CAST(bullet_points AS TEXT) || ' ' || CAST(key_entities AS TEXT)"
)


def upgrade():
    op.execute(
        "CREATE INDEX ix_articles_effective_time ON articles (coalesce(published_at, created_at))"
    )
    op.execute(
        "CREATE INDEX ix_articles_search ON articles "
        f"USING gin (to_tsvector('english'::regconfig, {ARTICLE_DOCUMENT}))"
    )
    op.execute(
        "CREATE INDEX ix_summaries_search ON summaries "
        f"USING gin (to_tsvector('english'::regconfig, {SUMMARY_DOCUMENT}))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_summaries_search")
    op.execute("DROP INDEX IF EXISTS ix_articles_search")
    op.execute("DROP INDEX IF EXISTS ix_articles_effective_time")
