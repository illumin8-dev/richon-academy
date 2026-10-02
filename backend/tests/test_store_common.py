"""Shared DB row helper and store ownership boundaries."""
import ast
from pathlib import Path

from store_common import fetch_rows

ROOT=Path(__file__).parents[1]


class Column:
    def __init__(self,name):
        self.name=name


class Cursor:
    description=(Column('alpha'),Column('beta'))

    def fetchall(self):
        return [(1,'x'),(2,'y')]


def test_fetch_rows_preserves_columns_and_values():
    assert fetch_rows(Cursor())==[
        {'alpha':1,'beta':'x'},
        {'alpha':2,'beta':'y'},
    ]


def test_stores_use_shared_row_owner():
    expected={
        'portal_store.py',
        'monthly_store.py',
        'course_domain_store.py',
        'manual_store.py',
    }
    for name in expected:
        tree=ast.parse((ROOT/name).read_text())
        definitions={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
        assert '_rows' not in definitions
        imports={
            a.name
            for n in tree.body
            if isinstance(n,ast.ImportFrom) and n.module=='store_common'
            for a in n.names
        }
        assert 'fetch_rows' in imports
    manual=(ROOT/'manual_store.py').read_text()
    assert 'from monthly_store import _rows' not in manual
