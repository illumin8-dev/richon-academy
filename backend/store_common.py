"""Small DB-row helpers shared by store modules."""


def fetch_rows(cur):
    names=[column.name for column in cur.description]
    return [dict(zip(names,row,strict=True)) for row in cur.fetchall()]
