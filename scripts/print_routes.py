from server import app
print('\n'.join(sorted([str(r) for r in app.url_map.iter_rules()])))
