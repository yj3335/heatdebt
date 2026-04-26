import httpx
import duckdb
import json
import os
import sys

# Use paths relative to the script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "agent_prompt.txt")
DB_PATH = os.path.join(BASE_DIR, "heatdebt.duckdb")

def ask_llm(user_question: str) -> str:
    # Send a question to Ollama and get back SQL.
    try:
        with open(SYSTEM_PROMPT_PATH, "r") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        return "Error: agent_prompt.txt not found."

    try:
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": f"{system_prompt}\n\nUser: {user_question}\nSQL:",
                "stream": False,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["response"].strip().strip("`").strip()
    except Exception as e:
        return f"LLM Error: {e}"

def run_query(sql: str):
    # Execute SQL against DuckDB and return results.
    if sql.startswith("Error") or sql.startswith("LLM Error"):
        return sql
        
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("LOAD spatial;")
    try:
        result = con.execute(sql).fetchdf()
        return result
    except Exception as e:
        return f"Query error: {e}"
    finally:
        con.close()

def agent(question: str):
    # Full agent loop: question -> SQL -> results.
    sql = ask_llm(question)
    
    # Basic safety check
    if any(word in sql.upper() for word in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
        return "Refused: destructive query detected."

    result = run_query(sql)
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        res = agent("Which 5 tracts in Brooklyn have the highest heat debt?")
    else:
        res = agent(sys.argv[1])
    print(res)
