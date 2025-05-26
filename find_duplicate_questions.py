import sys
from models import get_db_session, QARecord
from collections import defaultdict

# 获取数据库会话
session = get_db_session()

# 统计重复题目（question+type+options）
record_map = defaultdict(list)

for record in session.query(QARecord).all():
    key = (record.question.strip(), (record.type or '').strip(), (record.options or '').strip())
    record_map[key].append(record)

duplicates = [recs for recs in record_map.values() if len(recs) > 1]

deleted_ids = []
if not duplicates:
    print('没有发现重复题目。')
    sys.exit(0)

print(f'共发现 {len(duplicates)} 组重复题目，将自动去重...')
for i, recs in enumerate(duplicates, 1):
    # 按ID排序，保留ID最小的，删除其余
    recs_sorted = sorted(recs, key=lambda r: r.id)
    to_delete = recs_sorted[1:]
    for rec in to_delete:
        session.delete(rec)
        deleted_ids.append(rec.id)
    print(f'第{i}组，保留ID: {recs_sorted[0].id}，删除ID: {[r.id for r in to_delete]}')

session.commit()
print(f'已删除 {len(deleted_ids)} 条重复记录。') 