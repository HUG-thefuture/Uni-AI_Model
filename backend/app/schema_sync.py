"""Database schema inspection and additive synchronization.

The project intentionally does not use Alembic yet, but ``create_all`` alone
cannot repair a table that was created by an older DDL script. This module
keeps the ORM metadata as the runtime source of truth and performs only safe,
additive changes: missing tables, columns, indexes, and named unique keys.

Existing columns are never dropped or rewritten. Incompatible legacy columns
are reported by ``--check`` for an explicit, reviewed migration.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, MetaData, UniqueConstraint, inspect, text
from sqlalchemy.schema import CreateColumn


@dataclass
class SchemaSyncReport:
    """Changes and remaining compatibility information from one sync run."""

    created_tables: list[str] = field(default_factory=list)
    added_columns: list[str] = field(default_factory=list)
    created_indexes: list[str] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    missing_indexes: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created_tables or self.added_columns or self.created_indexes)

    @property
    def has_unresolved_drift(self) -> bool:
        return bool(self.missing_tables or self.missing_columns or self.missing_indexes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created_tables": self.created_tables,
            "added_columns": self.added_columns,
            "created_indexes": self.created_indexes,
            "missing_tables": self.missing_tables,
            "missing_columns": self.missing_columns,
            "missing_indexes": self.missing_indexes,
            "extra_columns": self.extra_columns,
        }


def _quote(engine: Engine, identifier: str) -> str:
    return engine.dialect.identifier_preparer.quote(identifier)


def _column_sql(engine: Engine, column) -> str:
    """Compile a metadata column for an ALTER TABLE ADD COLUMN statement."""
    return str(CreateColumn(column).compile(dialect=engine.dialect))


def _index_signature(item: dict[str, Any]) -> tuple[tuple[str, ...], bool]:
    return tuple(item.get("column_names") or ()), bool(item.get("unique", False))


def _existing_index_signatures(connection, table_name: str) -> set[tuple[tuple[str, ...], bool]]:
    inspector = inspect(connection)
    signatures = {
        _index_signature(index)
        for index in inspector.get_indexes(table_name)
    }
    for constraint in inspector.get_unique_constraints(table_name):
        signatures.add((tuple(constraint.get("column_names") or ()), True))
    return signatures


def inspect_schema(engine: Engine, metadata: MetaData) -> SchemaSyncReport:
    """Return a read-only report of missing and legacy schema elements."""
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(metadata.tables)
    report = SchemaSyncReport(missing_tables=sorted(expected_tables - actual_tables))

    for table_name in sorted(expected_tables & actual_tables):
        expected = metadata.tables[table_name]
        actual_columns = {item["name"] for item in inspector.get_columns(table_name)}
        report.missing_columns.extend(
            f"{table_name}.{column.name}"
            for column in expected.columns
            if column.name not in actual_columns
        )
        report.extra_columns.extend(
            f"{table_name}.{column}"
            for column in sorted(actual_columns - set(expected.columns.keys()))
        )
        actual_signatures = {
            _index_signature(index) for index in inspector.get_indexes(table_name)
        }
        actual_signatures.update(
            (tuple(constraint.get("column_names") or ()), True)
            for constraint in inspector.get_unique_constraints(table_name)
        )
        for index in expected.indexes:
            signature = (tuple(column.name for column in index.columns), bool(index.unique))
            if signature not in actual_signatures:
                report.missing_indexes.append(f"{table_name}.{index.name}")
        for constraint in expected.constraints:
            if not isinstance(constraint, UniqueConstraint):
                continue
            signature = (tuple(column.name for column in constraint.columns), True)
            if signature not in actual_signatures:
                name = constraint.name or f"uk_{table_name}_{'_'.join(column.name for column in constraint.columns)}"
                report.missing_indexes.append(f"{table_name}.{name}")

    return report


def sync_schema(engine: Engine, metadata: MetaData) -> SchemaSyncReport:
    """Create and additively align all tables represented by ``metadata``.

    Running this function a second time against the same database is a no-op.
    """
    before_tables = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        metadata.create_all(bind=connection)
        after_tables = set(inspect(connection).get_table_names())
        report = SchemaSyncReport(created_tables=sorted(after_tables - before_tables))

        for table_name in sorted(metadata.tables):
            if table_name not in after_tables:
                continue
            table = metadata.tables[table_name]
            actual_columns = {
                item["name"] for item in inspect(connection).get_columns(table_name)
            }
            for column in table.columns:
                if column.name in actual_columns:
                    continue
                statement = (
                    f"ALTER TABLE {_quote(engine, table_name)} ADD COLUMN "
                    f"{_column_sql(engine, column)}"
                )
                connection.execute(text(statement))
                report.added_columns.append(f"{table_name}.{column.name}")
                actual_columns.add(column.name)

        for table_name in sorted(metadata.tables):
            table = metadata.tables[table_name]
            existing_signatures = _existing_index_signatures(connection, table_name)
            for index in list(table.indexes):
                signature = (tuple(column.name for column in index.columns), bool(index.unique))
                if signature in existing_signatures:
                    continue
                index.create(bind=connection, checkfirst=True)
                existing_signatures.add(signature)
                report.created_indexes.append(f"{table_name}.{index.name}")
            for constraint in table.constraints:
                if not isinstance(constraint, UniqueConstraint):
                    continue
                signature = (tuple(column.name for column in constraint.columns), True)
                if signature in existing_signatures:
                    continue
                index_name = constraint.name or (
                    f"uk_{table_name}_{'_'.join(column.name for column in constraint.columns)}"
                )
                column_sql = ", ".join(
                    _quote(engine, column.name) for column in constraint.columns
                )
                connection.execute(text(
                    f"CREATE UNIQUE INDEX {_quote(engine, index_name)} "
                    f"ON {_quote(engine, table_name)} ({column_sql})"
                ))
                existing_signatures.add(signature)
                report.created_indexes.append(f"{table_name}.{index_name}")

    # Keep non-destructive legacy columns visible to callers, while the change
    # lists above remain limited to actions performed by this invocation.
    remaining = inspect_schema(engine, metadata)
    report.extra_columns = remaining.extra_columns
    return report


def _load_metadata():
    # Importing the package registers every mapped table, including Invoice and
    # the support tables that older init_db versions omitted explicitly.
    from .core.db import Base
    from . import models  # noqa: F401

    return Base.metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查或增量对齐 AI Portal 数据库结构")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="仅检查，不修改数据库")
    mode.add_argument("--apply", action="store_true", help="执行增量结构对齐")
    args = parser.parse_args(argv)

    from .core.db import engine

    metadata = _load_metadata()
    if args.check:
        report = inspect_schema(engine, metadata)
        print(report.as_dict())
        if report.extra_columns:
            print("[schema] 检测到历史冗余字段，按安全策略保留，不自动删除")
        return 1 if report.has_unresolved_drift else 0

    report = sync_schema(engine, metadata)
    print(f"[schema] 对齐完成: 新表 {len(report.created_tables)}，"
          f"新增列 {len(report.added_columns)}，新增索引 {len(report.created_indexes)}")
    if report.extra_columns:
        print(f"[schema] 保留历史冗余字段 {len(report.extra_columns)} 个(未删除)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
