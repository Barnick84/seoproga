from utils.db import get_db_cursor
import json

with get_db_cursor(dictionary=True) as (conn, cur):
    cur.execute("SELECT structure_json FROM site_structure WHERE site_url = %s", ("русский-кавказ.рф",))
    row = cur.fetchone()
    if row:
        tree = json.loads(row["structure_json"])
        
        def validate_node(node, path="root"):
            if not isinstance(node, dict):
                print(f"ERROR: Node at {path} is not dict: {type(node)}: {node}")
                return
            for key in ["id", "title", "url", "is_folder", "page_type"]:
                val = node.get(key)
                if val is not None and not isinstance(val, (str, bool, int, float)):
                    print(f"WARNING: Node {path} field {key} has unusual type: {type(val)} = {val}")
            
            children = node.get("children")
            if children is not None:
                if not isinstance(children, list):
                    print(f"ERROR: Node {path} 'children' is not list: {type(children)} = {children}")
                else:
                    for i, child in enumerate(children):
                        validate_node(child, f"{path} -> {child.get('title', i)}")

        print(f"Validating tree with {len(tree)} top-level nodes...")
        for i, top in enumerate(tree):
            validate_node(top, f"top_{i}")
        print("Validation complete!")
