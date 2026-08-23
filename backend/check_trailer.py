import sqlite3, os

conn = sqlite3.connect('app/clipsense.db')
cur = conn.cursor()

print('=== smart_trailer_jobs ===')
rows = cur.execute('SELECT id, status, output_path, project_id, created_at FROM smart_trailer_jobs').fetchall()
for r in rows:
    print(f'  id={r[0]}')
    print(f'  status={r[1]}')
    print(f'  output_path={r[2]}')
    print(f'  project_id={r[3]}')
    print(f'  created_at={r[4]}')
    if r[2]:
        print(f'  file_exists={os.path.exists(r[2])}')
        if os.path.exists(r[2]):
            print(f'  file_size={os.path.getsize(r[2])}')
    print()

print('=== trailers dir ===')
for f in os.listdir('app/trailers'):
    if not f.startswith('.'):
        print(f'  {f}')

print('\n=== uploads/projects (generations) ===')
proj_dir = 'app/uploads/projects'
for pid in os.listdir(proj_dir):
    gen_dir = os.path.join(proj_dir, pid, 'generations')
    if os.path.isdir(gen_dir):
        for f in os.listdir(gen_dir):
            full = os.path.join(gen_dir, f)
            print(f'  {pid}/generations/{f}  size={os.path.getsize(full)}')

conn.close()
