import os
import json
import sys

def main():
    tool_name = os.environ.get("DOJO_TOOL_NAME", "")
    args_raw = os.environ.get("DOJO_TOOL_ARGS", "{}")
    
    try:
        args = json.loads(args_raw)
    except Exception:
        args = {}
        
    code_content = ""
    if "code" in args:
        code_content = str(args["code"])
    elif "command" in args:
        code_content = str(args["command"])
    elif "cmd" in args:
        code_content = str(args["cmd"])
        
    malicious_keywords = [
        "rm -rf",
        "shred",
        "os.remove",
        "shutil.rmtree",
        "drop database",
        ".drop("
    ]
    
    is_malicious = False
    matched_keyword = ""
    for keyword in malicious_keywords:
        if keyword in code_content.lower():
            is_malicious = True
            matched_keyword = keyword
            break
            
    if is_malicious:
        print(json.dumps({
            "action": "block",
            "message": f"Safety Violation: Code execution blocked due to restricted command pattern '{matched_keyword}'."
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "action": "allow"
        }, ensure_ascii=False))

if __name__ == "__main__":
    main()
