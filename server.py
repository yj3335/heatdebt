from flask import Flask, request, jsonify, send_from_directory
from llm_agent import agent
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Serve the frontend
@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('frontend', path)

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question')
    if not question:
        return jsonify({"type": "error", "data": "No question provided"}), 400
    
    try:
        result = agent(question)
        if hasattr(result, 'to_dict'):
            return jsonify({
                "type": "table",
                "data": result.to_dict(orient='records')
            })
        else:
            return jsonify({
                "type": "text",
                "data": str(result)
            })
    except Exception as e:
        print(f"Error in /ask: {e}")
        return jsonify({"type": "error", "data": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
