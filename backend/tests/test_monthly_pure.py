"""Execute the actual pure month functions without importing application/DB dependencies."""
import ast
from datetime import date
from pathlib import Path
import re
import pytest

source=Path(__file__).parents[1]/'monthly_store.py'
tree=ast.parse(source.read_text())
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'month_start','add_months'}]
namespace={'date':date,'re':re}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),namespace)
month_start=namespace['month_start'];add_months=namespace['add_months']

@pytest.mark.parametrize('start,n,end',[
 ('2026-10',1,'2026-10'),('2026-10',3,'2026-12'),('2026-10',12,'2027-09'),
 ('2026-10',4,'2027-01'),('2024-01',2,'2024-02'),('2024-02',12,'2025-01'),
 ('2026-12',3,'2027-02'),('2026-11',2,'2026-12'),('2026-12',2,'2027-01'),
 ('2023-02',1,'2023-02'),('2024-02',1,'2024-02'),('2025-01',12,'2025-12'),
])
def test_inclusive_calendar_month_range(start,n,end):
    assert add_months(month_start(start),n-1)==month_start(end)

@pytest.mark.parametrize('value',['2026-00','2026-13','0000-01','2026-1','2026-10-01','10',' 2026-10','2026-10 ',"2026-10' OR TRUE",None,202610,'2026/10'])
def test_invalid_month(value):
    with pytest.raises((ValueError,TypeError)):month_start(value)

@pytest.mark.parametrize('n',[True,'3',1.5,None])
def test_month_count_is_an_integer(n):
    with pytest.raises(ValueError):add_months(date(2026,10,1),n)

def test_not_a_day_based_expiry():
    with pytest.raises(ValueError):add_months(date(2026,10,7),1)

def test_extending_preserves_original_month_anchor():
    start=month_start('2026-10')
    assert add_months(add_months(start,3),1)==add_months(start,4)==month_start('2027-02')
