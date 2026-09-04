"""Regression tests for repairing databases created by the legacy DDL files."""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect, text


class SchemaSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        # Delay app imports until test execution so this module cannot change
        # DATABASE_URL while pytest is collecting the other DB test modules.
        from app.core.db import Base
        from app import models  # noqa: F401 register every mapped table
        from app.schema_sync import inspect_schema, sync_schema

        self.metadata = Base.metadata
        self.inspect_schema = inspect_schema
        self.sync_schema = sync_schema

    def tearDown(self) -> None:
        self.engine.dispose()

    def _create_legacy_tables(self) -> None:
        """Representative structures produced by the conflicting old scripts."""
        statements = [
            """
            CREATE TABLE models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                model_code VARCHAR(200) NOT NULL,
                provider_type VARCHAR(20) NOT NULL,
                model_type VARCHAR(20) NOT NULL,
                vendor VARCHAR(30) NOT NULL,
                endpoint VARCHAR(255),
                price_per_call BIGINT NOT NULL DEFAULT 0,
                max_duration_sec BIGINT,
                status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                config_json TEXT,
                description VARCHAR(500),
                capability_tags JSON,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                status SMALLINT NOT NULL DEFAULT 1,
                real_auth_status SMALLINT NOT NULL DEFAULT 0,
                school VARCHAR(100),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE consumption_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id BIGINT NOT NULL,
                task_id BIGINT,
                model_id BIGINT,
                amount BIGINT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id BIGINT NOT NULL,
                name VARCHAR(100) NOT NULL,
                key_prefix VARCHAR(16) NOT NULL,
                key_hash VARCHAR(64) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                use_count BIGINT NOT NULL DEFAULT 0,
                expires_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id BIGINT,
                action VARCHAR(50) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id BIGINT,
                detail_json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def test_legacy_schema_is_repaired_and_idempotent(self) -> None:
        self._create_legacy_tables()

        before = self.inspect_schema(self.engine, self.metadata)
        self.assertIn("models.api_key", before.missing_columns)
        self.assertIn("users.updated_at", before.missing_columns)
        self.assertIn("consumption_records.balance_before", before.missing_columns)
        self.assertIn("api_keys.updated_at", before.missing_columns)
        self.assertIn("operation_logs.ip", before.missing_columns)
        self.assertIn("invoices", before.missing_tables)

        report = self.sync_schema(self.engine, self.metadata)
        self.assertIn("models.api_key", report.added_columns)
        self.assertIn("users.updated_at", report.added_columns)
        self.assertIn("consumption_records.balance_before", report.added_columns)
        self.assertIn("api_keys.updated_at", report.added_columns)
        self.assertIn("operation_logs.ip", report.added_columns)
        self.assertIn("invoices", report.created_tables)

        inspector = inspect(self.engine)
        self.assertIn("api_key", {item["name"] for item in inspector.get_columns("models")})
        self.assertIn("updated_at", {item["name"] for item in inspector.get_columns("users")})
        self.assertIn("balance_after", {item["name"] for item in inspector.get_columns("consumption_records")})
        self.assertIn("updated_at", {item["name"] for item in inspector.get_columns("api_keys")})
        self.assertIn("ip", {item["name"] for item in inspector.get_columns("operation_logs")})

        second = self.sync_schema(self.engine, self.metadata)
        self.assertEqual(second.added_columns, [])
        self.assertEqual(second.created_indexes, [])
        self.assertFalse(self.inspect_schema(self.engine, self.metadata).has_unresolved_drift)


if __name__ == "__main__":
    unittest.main()
