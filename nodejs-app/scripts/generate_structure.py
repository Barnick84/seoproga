import sys
import os
import json

# Force UTF-8 for Windows
if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add root to sys.path to import services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from services.seo_agent import SEOAgent

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing input data"}))
        return

    try:
        # Input is passed as a JSON string in the first argument
        input_data = json.loads(sys.argv[1])
        competitors_headers = input_data.get("competitors_headers", [])
        
        agent = SEOAgent()
        result_json = agent.generate_ideal_structure(competitors_headers)
        
        # Result is already a JSON string from LLM
        print(result_json)
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
