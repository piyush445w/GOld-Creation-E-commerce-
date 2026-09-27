import os
os.environ['DATABASE_URL'] = 'mysql+pymysql://root:@localhost/test_migration_db'
os.environ['SECRET_KEY'] = 'test'
from app import create_app
from sqlalchemy import text, inspect

app = create_app()
with app.app_context():
    from app import db
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print('Tables:', tables)
    for table in tables:
        print(f'\nTable: {table}')
        columns = inspector.get_columns(table)
        for col in columns:
            print(f'  Column: {col["name"]} ({col["type"]})')
        fks = inspector.get_foreign_keys(table)
        for fk in fks:
            print(f'  FK: {fk["name"]} -> {fk["referred_table"]}.{fk["referred_columns"]}')
        uqs = inspector.get_unique_constraints(table)
        for uq in uqs:
            print(f'  Unique: {uq["name"]} -> {uq["column_names"]}')
        pks = inspector.get_pk_constraint(table)
        print(f'  PK: {pks["name"]} -> {pks["constrained_columns"]}')
