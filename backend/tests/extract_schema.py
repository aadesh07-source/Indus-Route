import re, sys
c = open('backend/app/db.py').read()
m = re.search(r'SCHEMA_PART2 = """(.*?)"""', c, re.DOTALL)
print(m.group(1))
