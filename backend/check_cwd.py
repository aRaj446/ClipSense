import subprocess, os
result = subprocess.run(
    ['wmic', 'process', 'where', 'ProcessId=32616', 'get', 'ExecutablePath,ProcessId'],
    capture_output=True, text=True
)
print(result.stdout)

# Also check what DB path resolves to from backend dir
db_path = os.path.abspath('app/clipsense.db')
print(f'DB absolute path: {db_path}')
print(f'DB exists: {os.path.exists(db_path)}')
