import pytest
from promptview.model2.postgres.sql.compiler import Compiler
from promptview.model2.postgres.sql.expressions import And, Like, In, Between, Eq, Gt, Value, Or, Not, Function, Coalesce, IsNull
from promptview.model2.postgres.sql.queries import Column, SelectQuery, Table

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





def test_select_with_coalesce_and_json_agg():        

    # Tables
    users = Table("users", "u")
    posts = Table("posts", "p")
    likes = Table("likes", "l")

    # Columns
    u_id = Column("id", users)
    u_name = Column("name", users)
    u_age = Column("age", users)
    u_created = Column("created_at", users)
    u_address = Column("address", users)

    p_id = Column("id", posts)
    p_user_id = Column("user_id", posts)
    p_created = Column("created_at", posts)
    p_title = Column("title", posts)
    p_content = Column("content", posts)

    l_id = Column("id", likes)
    l_created = Column("created_at", likes)
    l_post_id = Column("post_id", likes)

    # Subquery for likes
    likes_obj = Function(
        "jsonb_build_object",
        Value("id"), l_id,
        Value("created_at"), l_created,
        Value("post_id"), l_post_id
    )

    likes_subq = SelectQuery()
    likes_subq.columns = [Function("json_agg", likes_obj)]
    likes_subq.from_table = likes
    likes_subq.where_clause = Eq(l_post_id, p_id)

    likes_coalesced = Coalesce(likes_subq, Value("[]"))

    # Posts aggregation
    post_obj = Function(
        "jsonb_build_object",
        Value("id"), p_id,
        Value("created_at"), p_created,
        Value("title"), p_title,
        Value("content"), p_content,
        Value("user_id"), p_user_id,
        Value("likes"), likes_coalesced
    )

    posts_agg = Function(
        "json_agg", post_obj,
        distinct=True,
        filter_where=Not(IsNull(p_id))
    )

    posts_coalesced = Coalesce(posts_agg, Value("[]"), alias="posts")

    # Final query
    query = SelectQuery()
    query.columns = [u_id, u_created, u_name, u_age, u_address, posts_coalesced]
    query.from_table = users
    query.join(posts, Eq(u_id, p_user_id))
    query.join(likes, Eq(p_id, l_post_id))
    query.group_by = [u_id]



    compiler = Compiler()
    sql, params = compiler.compile(query)   
    
    assert sql == """SELECT u.id, u.created_at, u.name, u.age, u.address, COALESCE(json_agg(DISTINCT jsonb_build_object('id', p.id, 'created_at', p.created_at, 'title', p.title, 'content', p.content, 'user_id', p.user_id, 'likes', COALESCE((SELECT json_agg(jsonb_build_object('id', l.id, 'created_at', l.created_at, 'post_id', l.post_id))
FROM likes AS l
WHERE (l.post_id = p.id)), '[]'))) FILTER (WHERE (NOT (p.id IS NULL))), '[]') AS posts
FROM users AS u
INNER JOIN posts AS p ON (u.id = p.user_id) INNER JOIN likes AS l ON (p.id = l.post_id)
GROUP BY u.id"""







def test_where_clause():
    users = Table("users", "u")
    u_id = Column("id", users)
    u_name = Column("name", users)
    u_age = Column("age", users)
    u_address = Column("address", users)
    u_created = Column("created_at", users)

    # WHERE clause
    where_expr = And(
        Or(
            And(
                Gt(u_age, Value(21)),
                Like(u_name, Value("J%"))
            ),
            Not(IsNull(u_address))
        ),
        In(u_id, [1, 2, 3]),
        Between(u_created, Value("2023-01-01"), Value("2023-12-31"))
    )

    # Build the query
    query = SelectQuery()
    query.columns = [u_id, u_name, u_age, u_address, u_created]
    query.from_table = users
    query.where_clause = where_expr

    # Compile
    compiler = Compiler()
    sql, params = compiler.compile(query)

    # Print for debugging (optional)
    
    # Basic assertions
    assert "WHERE" in sql
    assert "AND" in sql
    assert "OR" in sql
    assert "LIKE" in sql
    assert "BETWEEN" in sql
    assert "IN ($" in sql or "IN (" in sql  # Depending on your param rendering
    assert len(params) == 7
    assert params == [21, "J%", 1, 2, 3, "2023-01-01", "2023-12-31"][:len(params)]
