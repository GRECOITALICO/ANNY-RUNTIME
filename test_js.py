import json

text = "hello\n"
script = f'''function() {{
    const txt = {json.dumps(text)};
    if (this.tagName !== 'textarea' && (txt.includes('\\n') || txt.includes('\\r'))) {{
        return "blocked";
    }}
    return "ok";
}}'''
print(script)
