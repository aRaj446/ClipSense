import sqlite3, os, json
conn = sqlite3.connect('app/clipsense.db')
cur = conn.cursor()
rows = cur.execute('SELECT id, name, raw_footage_name, status, created_at FROM projects').fetchall()
print('=== DB projects ===')
for r in rows:
    print(r)

print('\n=== Metadata JSON files ===')
meta_dir = 'app/uploads/metadata'
if os.path.isdir(meta_dir):
    for f in os.listdir(meta_dir):
        if f.endswith('.json'):
            try:
                with open(os.path.join(meta_dir, f)) as fh:
                    d = json.load(fh)
                print(f"  {f}: id={d.get('id')} filename={d.get('filename')} upload_time={d.get('upload_time')}")
            except Exception as e:
                print(f"  {f}: ERROR {e}")
else:
    print(f'  {meta_dir} does not exist')
conn.close()
