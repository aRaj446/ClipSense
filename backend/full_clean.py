import sqlite3, os, shutil

conn = sqlite3.connect('app/clipsense.db')
cur = conn.cursor()

# Clear all tables
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for (t,) in tables:
    cur.execute(f"DELETE FROM {t}")
conn.commit()

# Verify
print('=== DB after wipe ===')
for (t,) in tables:
    count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f'  {t}: {count} rows')
conn.close()

# Clean uploads/projects
proj_dir = 'app/uploads/projects'
if os.path.isdir(proj_dir):
    for entry in os.listdir(proj_dir):
        full = os.path.join(proj_dir, entry)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
            print(f'  removed project dir: {entry}')

# Clean flat uploads (legacy mp4s)
upload_dir = 'app/uploads'
for f in os.listdir(upload_dir):
    if f.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        os.remove(os.path.join(upload_dir, f))
        print(f'  removed flat upload: {f}')

# Clean smart uploads
smart_dir = 'app/uploads/smart'
if os.path.isdir(smart_dir):
    for entry in os.listdir(smart_dir):
        full = os.path.join(smart_dir, entry)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
            print(f'  removed smart dir: {entry}')

# Clean metadata JSONs
meta_dir = 'app/metadata'
if os.path.isdir(meta_dir):
    for f in os.listdir(meta_dir):
        if f.endswith('.json'):
            os.remove(os.path.join(meta_dir, f))
            print(f'  removed metadata: {f}')

# Clean trailers
trailers_dir = 'app/trailers'
if os.path.isdir(trailers_dir):
    for f in os.listdir(trailers_dir):
        if f.endswith('.mp4'):
            os.remove(os.path.join(trailers_dir, f))
            print(f'  removed trailer: {f}')

print('\n=== Final disk state ===')
for d in [upload_dir, proj_dir, smart_dir, meta_dir, trailers_dir]:
    if os.path.isdir(d):
        contents = [f for f in os.listdir(d) if not f.startswith('.')]
        print(f'  {d}: {contents}')
