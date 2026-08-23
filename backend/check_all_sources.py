import sqlite3, os, json

conn = sqlite3.connect('app/clipsense.db')
cur = conn.cursor()

print('=== ALL PROJECTS IN DB ===')
rows = cur.execute('SELECT id, name, raw_footage_name, status, created_at, updated_at FROM projects').fetchall()
for r in rows:
    print(f'  id={r[0]}')
    print(f'  name={r[1]}')
    print(f'  raw_footage_name={r[2]}')
    print(f'  status={r[3]}')
    print(f'  created_at={r[4]}')
    print(f'  updated_at={r[5]}')
    print()

print('=== UPLOADS/PROJECTS DIR ===')
proj_dir = 'app/uploads/projects'
if os.path.isdir(proj_dir):
    for entry in os.listdir(proj_dir):
        full = os.path.join(proj_dir, entry)
        if os.path.isdir(full):
            files = os.listdir(full)
            print(f'  {entry}/  -> {files}')
else:
    print('  does not exist')

print('\n=== METADATA DIR ===')
meta_dir = 'app/metadata'
if os.path.isdir(meta_dir):
    files = os.listdir(meta_dir)
    print(f'  files: {files}')
    for f in files:
        if f.endswith('.json'):
            with open(os.path.join(meta_dir, f)) as fh:
                d = json.load(fh)
            print(f'  {f}: id={d.get("id")} filename={d.get("filename")} upload_time={d.get("upload_time")}')
else:
    print('  does not exist')

print('\n=== UPLOADS DIR (flat) ===')
upload_dir = 'app/uploads'
if os.path.isdir(upload_dir):
    flat = [f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))]
    print(f'  flat files: {flat}')
else:
    print('  does not exist')

conn.close()
