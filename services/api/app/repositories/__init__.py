"""Repository layer: all database access goes through these classes.

Repositories take an `AsyncSession` and never commit — transaction boundaries
belong to the caller (the request-scoped session dependency, or a test).
"""
