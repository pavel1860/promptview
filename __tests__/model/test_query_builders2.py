import pytest
from promptview.model2.postgres.compiler import Compiler
from promptview.model2.postgres.expressions import Eq, Gt, Value, Or, Not
from promptview.model2.postgres.query_builders3 import Column, SelectQuery, Table

def test_simple_select_with_where_and_join():
    users = Table("users", alias="u")
    posts = Table("posts", alias="p")

    query = SelectQuery()
    query.from_table = users
    query.columns = [Column("id", users), Column("title", posts)]
    query.inner_join(
        posts,
        Eq(Column("id", users), Column("user_id", posts))
    )
    query.where_clause = Gt(Column("age", users), Value(21))

    compiler = Compiler()
    sql, params = compiler.compile(query)

    expected_sql = (
        "SELECT u.id, p.title\n"
        "FROM users AS u\n"
        "INNER JOIN posts AS p ON (u.id = p.user_id)\n"
        "WHERE (u.age > $1)"
    )

    assert sql.strip() == expected_sql.strip()
    assert params == [21]

def test_select_with_multiple_conditions_and():
    users = Table("users", alias="u")

    query = SelectQuery()
    query.from_table = users
    query.columns = [Column("id", users)]
    query.where_clause = (
        Gt(Column("age", users), Value(21)) &
        Eq(Column("is_active", users), Value(True))
    )

    compiler = Compiler()
    sql, params = compiler.compile(query)

    expected_sql = (
        "SELECT u.id\n"
        "FROM users AS u\n"
        "WHERE ((u.age > $1) AND (u.is_active = $2))"
    )

    assert sql.strip() == expected_sql.strip()
    assert params == [21, True]

def test_select_with_or_and_not():
    users = Table("users", alias="u")

    

    query = SelectQuery()
    query.from_table = users
    query.columns = [Column("id", users)]
    query.where_clause = Not(
        Or(
            Eq(Column("role", users), Value("admin")),
            Eq(Column("role", users), Value("moderator")),
        )
    )

    compiler = Compiler()
    sql, params = compiler.compile(query)

    expected_sql = (
        "SELECT u.id\n"
        "FROM users AS u\n"
        "WHERE (NOT ((u.role = $1) OR (u.role = $2)))"
    )

    assert sql.strip() == expected_sql.strip()
    assert params == ["admin", "moderator"]
