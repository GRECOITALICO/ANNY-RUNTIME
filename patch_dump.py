with open("runtime/browser/broker_server.py", "r") as f:
    code = f.read()

old_print = 'print(f\'[DEBUG Fetch] Paused {req.get("method")} to {req.get("url")}\', file=sys.stderr)'
new_print = 'print(f\'[DEBUG Fetch] Paused {req.get("method")} to {req.get("url")}: {req}\', file=sys.stderr)'
code = code.replace(old_print, new_print)

with open("runtime/browser/broker_server.py", "w") as f:
    f.write(code)
